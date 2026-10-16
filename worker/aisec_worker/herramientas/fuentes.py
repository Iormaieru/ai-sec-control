"""Fuentes públicas para la revisión de herramientas (sin estado, sin base).

- GitHub: datos de mantenimiento de un repo y descubrimiento por temas.
- PyPI / npm: versión publicada de un paquete.
- Índices de paquetes de Kali y Parrot (formato Debian `Packages.gz`) y de
  BlackArch (base de pacman `*.db.tar.gz`): qué herramientas empaqueta cada
  distribución, con versión y categoría.

Cualquier falla (red, HTTP, formato) se informa como FuenteError, para que la
revisión siga con las demás fuentes.
"""

import datetime as dt
import gzip
import io
import re
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx

KALI_PACKAGES = "https://http.kali.org/kali/dists/kali-rolling/main/binary-amd64/Packages.gz"
# "parrot" es el alias estable de la versión vigente (hoy "echo").
PARROT_PACKAGES = "https://deb.parrot.sh/parrot/dists/parrot/main/binary-amd64/Packages.gz"
BLACKARCH_DB = "https://blackarch.org/blackarch/blackarch/os/x86_64/blackarch.db.tar.gz"

_TIMEOUT = httpx.Timeout(60, connect=15)
_USER_AGENT = "ai-sec-control/1.0 (revision de herramientas de pentesting)"


class FuenteError(Exception):
    """Una fuente no respondió o respondió algo inesperado."""


def _cliente(transport: httpx.BaseTransport | None = None, headers: dict | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT, **(headers or {})},
        transport=transport,
    )


def _get(http: httpx.Client, url: str, **kwargs) -> httpx.Response:
    try:
        resp = http.get(url, **kwargs)
    except httpx.HTTPError as exc:
        raise FuenteError(f"GET {url}: {type(exc).__name__}") from exc
    if resp.is_error:
        raise FuenteError(f"GET {url} -> {resp.status_code}")
    return resp


def _fecha(valor: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(valor.replace("Z", "+00:00")) if valor else None


# --- GitHub ---


@dataclass
class RepoGitHub:
    nombre: str  # "owner/nombre" vigente (si el repo se mudó, el nuevo)
    descripcion: str | None
    url: str
    homepage: str | None
    estrellas: int
    archivado: bool
    ultimo_push: dt.datetime | None
    licencia: str | None  # identificador SPDX ("MIT", "Apache-2.0"); None si no tiene o no es reconocida
    temas: list[str] = field(default_factory=list)


class GitHub:
    API = "https://api.github.com"

    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = _cliente(transport, headers)

    def close(self) -> None:
        self._http.close()

    def repo(self, nombre: str) -> RepoGitHub:
        """Datos del repo. GitHub redirige los repos mudados o renombrados:
        `nombre` del resultado es el vigente."""
        return self._repo(_get(self._http, f"{self.API}/repos/{nombre}").json())

    def buscar_por_tema(self, tema: str, *, min_estrellas: int, activos_desde: dt.date, limite: int = 50) -> list[RepoGitHub]:
        q = f"topic:{tema} stars:>={min_estrellas} pushed:>={activos_desde.isoformat()} archived:false"
        data = _get(
            self._http,
            f"{self.API}/search/repositories",
            params={"q": q, "sort": "stars", "order": "desc", "per_page": limite},
        ).json()
        return [self._repo(item) for item in data.get("items", [])]

    def readme(self, nombre: str, max_caracteres: int = 6000) -> str:
        resp = _get(self._http, f"{self.API}/repos/{nombre}/readme", headers={"Accept": "application/vnd.github.raw"})
        return resp.text[:max_caracteres]

    @staticmethod
    def _repo(data: dict) -> RepoGitHub:
        licencia = (data.get("license") or {}).get("spdx_id")
        return RepoGitHub(
            nombre=data["full_name"],
            descripcion=data.get("description"),
            url=data["html_url"],
            homepage=data.get("homepage") or None,
            estrellas=data.get("stargazers_count", 0),
            archivado=bool(data.get("archived")),
            ultimo_push=_fecha(data.get("pushed_at")),
            licencia=None if licencia in (None, "NOASSERTION") else licencia,
            temas=list(data.get("topics") or []),
        )


# --- Registros de paquetes ---


@dataclass
class VersionPublicada:
    version: str
    fecha: dt.datetime | None


class Registros:
    """PyPI y npm. `paquete` viene como "pypi:garak" o "npm:promptfoo"."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._http = _cliente(transport)

    def close(self) -> None:
        self._http.close()

    def version(self, paquete: str) -> VersionPublicada:
        registro, _, nombre = paquete.partition(":")
        if registro == "pypi":
            data = _get(self._http, f"https://pypi.org/pypi/{nombre}/json").json()
            archivos = data.get("urls") or []
            return VersionPublicada(
                version=data["info"]["version"],
                fecha=_fecha(archivos[0].get("upload_time_iso_8601")) if archivos else None,
            )
        if registro == "npm":
            data = _get(self._http, f"https://registry.npmjs.org/{nombre}").json()
            ultima = data["dist-tags"]["latest"]
            return VersionPublicada(version=ultima, fecha=_fecha((data.get("time") or {}).get(ultima)))
        raise FuenteError(f"Registro de paquetes desconocido: {paquete!r}")


# --- Distribuciones ---


@dataclass
class Paquete:
    nombre: str
    version: str
    descripcion: str | None = None
    url: str | None = None
    # Debian: dependencias (para leer los metapaquetes de categoría). BlackArch: vacío.
    depende_de: list[str] = field(default_factory=list)
    # BlackArch: grupos ("blackarch-webapp"). Debian: vacío.
    grupos: list[str] = field(default_factory=list)


_RE_NOMBRE_DEP = re.compile(r"^\s*([a-z0-9][a-z0-9+.\-]*)")


def _nombres_dependencias(valor: str) -> list[str]:
    """"a, b (>= 1), c | d" -> ["a", "b", "c", "d"]."""
    nombres = []
    for alternativa in re.split(r"[,|]", valor):
        if m := _RE_NOMBRE_DEP.match(alternativa):
            nombres.append(m.group(1))
    return nombres


def leer_packages_debian(lineas: Iterator[str]) -> dict[str, Paquete]:
    """Parsea un índice `Packages` de Debian (Kali, Parrot) línea por línea."""
    paquetes: dict[str, Paquete] = {}
    campos: dict[str, str] = {}
    ultimo: str | None = None

    def cerrar() -> None:
        if "Package" in campos:
            deps = _nombres_dependencias(campos.get("Depends", "")) + _nombres_dependencias(campos.get("Recommends", ""))
            paquetes[campos["Package"]] = Paquete(
                nombre=campos["Package"],
                version=campos.get("Version", ""),
                descripcion=campos.get("Description"),
                url=campos.get("Homepage"),
                depende_de=deps,
            )

    for linea in lineas:
        linea = linea.rstrip("\n")
        if not linea.strip():
            cerrar()
            campos, ultimo = {}, None
        elif linea[0] in " \t":
            if ultimo in ("Depends", "Recommends"):  # continuación de un campo largo
                campos[ultimo] += " " + linea.strip()
        elif ":" in linea:
            clave, _, valor = linea.partition(":")
            ultimo = clave
            campos[clave] = valor.strip()
    cerrar()
    return paquetes


def leer_db_blackarch(contenido: bytes) -> dict[str, Paquete]:
    """Parsea la base de pacman de BlackArch: un `desc` por paquete con
    secciones %NAME%, %VERSION%, %DESC%, %URL%, %GROUPS%."""
    paquetes: dict[str, Paquete] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(contenido), mode="r:*") as tar:
            for miembro in tar:
                if not miembro.name.endswith("/desc"):
                    continue
                archivo = tar.extractfile(miembro)
                if archivo is None:
                    continue
                secciones = _secciones_pacman(archivo.read().decode("utf-8", "replace"))
                if "NAME" not in secciones:
                    continue
                nombre = secciones["NAME"][0]
                paquetes[nombre] = Paquete(
                    nombre=nombre,
                    version=(secciones.get("VERSION") or [""])[0],
                    descripcion=(secciones.get("DESC") or [None])[0],
                    url=(secciones.get("URL") or [None])[0],
                    grupos=secciones.get("GROUPS", []),
                )
    except tarfile.TarError as exc:
        raise FuenteError(f"Base de BlackArch ilegible: {exc}") from exc
    return paquetes


def _secciones_pacman(texto: str) -> dict[str, list[str]]:
    secciones: dict[str, list[str]] = {}
    actual: str | None = None
    for linea in texto.splitlines():
        if linea.startswith("%") and linea.endswith("%"):
            actual = linea.strip("%")
            secciones[actual] = []
        elif linea and actual:
            secciones[actual].append(linea)
        else:
            actual = None
    return secciones


class Distribuciones:
    """Descarga y parsea los índices. Kali pesa ~20 MB comprimido: se lee en
    streaming, sin descomprimir todo en memoria."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._http = _cliente(transport)

    def close(self) -> None:
        self._http.close()

    def kali(self) -> dict[str, Paquete]:
        return self._debian(KALI_PACKAGES)

    def parrot(self) -> dict[str, Paquete]:
        return self._debian(PARROT_PACKAGES)

    def blackarch(self) -> dict[str, Paquete]:
        return leer_db_blackarch(_get(self._http, BLACKARCH_DB).content)

    def _debian(self, url: str) -> dict[str, Paquete]:
        contenido = _get(self._http, url).content
        try:
            with gzip.open(io.BytesIO(contenido), mode="rt", encoding="utf-8", errors="replace") as lineas:
                return leer_packages_debian(lineas)
        except (OSError, EOFError) as exc:
            raise FuenteError(f"Índice ilegible ({url}): {exc}") from exc
