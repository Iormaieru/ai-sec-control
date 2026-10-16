"""H2: clientes de fuentes con respuestas grabadas (sin red)."""

import datetime as dt
import gzip
import io
import tarfile

import httpx
import pytest

from aisec_worker.herramientas import fuentes
from aisec_worker.herramientas.fuentes import Distribuciones, FuenteError, GitHub, Registros

REPO_GARAK = {
    "full_name": "NVIDIA/garak",
    "description": "the LLM vulnerability scanner",
    "html_url": "https://github.com/NVIDIA/garak",
    "homepage": "",
    "stargazers_count": 9584,
    "archived": False,
    "pushed_at": "2026-10-15T10:00:00Z",
    "license": {"spdx_id": "Apache-2.0"},
    "topics": ["llm-security", "red-teaming"],
}

PACKAGES_KALI = """\
Package: kali-tools-top10
Version: 2026.3.9
Depends: aircrack-ng, burpsuite, hydra (>= 9.0),
 sqlmap, wireshark | tshark
Description: Kali Linux's top 10 tools

Package: sqlmap
Version: 1.10.9-1
Homepage: https://sqlmap.org/
Description: automatic SQL injection tool
 Continuación de la descripción que no se usa.

Package: parrot-tools-ai
Version: 7.1.2
Recommends: hexstrike-ai
Description: Pentest tools for AI
"""


def _transporte(rutas: dict[str, httpx.Response]) -> httpx.MockTransport:
    def responder(request: httpx.Request) -> httpx.Response:
        for prefijo, respuesta in rutas.items():
            if str(request.url).startswith(prefijo):
                return respuesta
        return httpx.Response(404)

    return httpx.MockTransport(responder)


def _db_blackarch(paquetes: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for carpeta, desc in paquetes.items():
            datos = desc.encode()
            info = tarfile.TarInfo(f"{carpeta}/desc")
            info.size = len(datos)
            tar.addfile(info, io.BytesIO(datos))
    return buffer.getvalue()


# --- GitHub ---


def test_github_repo_trae_datos_de_mantenimiento() -> None:
    gh = GitHub(transport=_transporte({"https://api.github.com/repos/NVIDIA/garak": httpx.Response(200, json=REPO_GARAK)}))

    repo = gh.repo("NVIDIA/garak")

    assert (repo.nombre, repo.estrellas, repo.archivado, repo.licencia) == ("NVIDIA/garak", 9584, False, "Apache-2.0")
    assert repo.ultimo_push == dt.datetime(2026, 10, 15, 10, tzinfo=dt.UTC)
    assert repo.temas == ["llm-security", "red-teaming"]
    assert repo.homepage is None  # "" -> None


def test_github_repo_mudado_devuelve_el_nombre_vigente() -> None:
    # GitHub responde 301 al repo viejo; el cliente sigue la redirección.
    rutas = {
        "https://api.github.com/repos/Azure/PyRIT": httpx.Response(
            301, headers={"Location": "https://api.github.com/repositories/123"}
        ),
        "https://api.github.com/repositories/123": httpx.Response(
            200, json={**REPO_GARAK, "full_name": "microsoft/PyRIT", "license": {"spdx_id": "NOASSERTION"}}
        ),
    }
    repo = GitHub(transport=_transporte(rutas)).repo("Azure/PyRIT")

    assert repo.nombre == "microsoft/PyRIT"
    assert repo.licencia is None  # NOASSERTION no es una licencia reconocida


def test_github_busqueda_por_tema_arma_la_consulta() -> None:
    pedidos: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return httpx.Response(200, json={"items": [REPO_GARAK]})

    gh = GitHub(token="tkn", transport=httpx.MockTransport(responder))
    repos = gh.buscar_por_tema("llm-security", min_estrellas=500, activos_desde=dt.date(2025, 10, 16))

    assert [r.nombre for r in repos] == ["NVIDIA/garak"]
    assert pedidos[0].url.params["q"] == "topic:llm-security stars:>=500 pushed:>=2025-10-16 archived:false"
    assert pedidos[0].headers["Authorization"] == "Bearer tkn"


def test_github_error_es_fuente_error() -> None:
    gh = GitHub(transport=_transporte({"https://api.github.com/repos/": httpx.Response(403)}))

    with pytest.raises(FuenteError, match="403"):
        gh.repo("NVIDIA/garak")


# --- PyPI / npm ---


def test_version_en_pypi_y_npm() -> None:
    registros = Registros(
        transport=_transporte(
            {
                "https://pypi.org/pypi/garak/json": httpx.Response(
                    200,
                    json={"info": {"version": "0.17.0"}, "urls": [{"upload_time_iso_8601": "2026-09-09T12:00:00.000000Z"}]},
                ),
                "https://registry.npmjs.org/promptfoo": httpx.Response(
                    200, json={"dist-tags": {"latest": "0.120.20"}, "time": {"0.120.20": "2026-10-01T00:00:00.000Z"}}
                ),
            }
        )
    )

    assert registros.version("pypi:garak").version == "0.17.0"
    npm = registros.version("npm:promptfoo")
    assert (npm.version, npm.fecha.date()) == ("0.120.20", dt.date(2026, 10, 1))
    with pytest.raises(FuenteError):
        registros.version("cargo:algo")


# --- Distribuciones ---


def test_packages_debian_paquetes_y_metapaquetes() -> None:
    paquetes = fuentes.leer_packages_debian(iter(PACKAGES_KALI.splitlines(keepends=True)))

    assert paquetes["kali-tools-top10"].depende_de == ["aircrack-ng", "burpsuite", "hydra", "sqlmap", "wireshark", "tshark"]
    sqlmap = paquetes["sqlmap"]
    assert (sqlmap.version, sqlmap.url, sqlmap.descripcion) == ("1.10.9-1", "https://sqlmap.org/", "automatic SQL injection tool")
    assert paquetes["parrot-tools-ai"].depende_de == ["hexstrike-ai"]  # Recommends también cuenta


def test_distribuciones_descarga_kali_comprimido() -> None:
    contenido = gzip.compress(PACKAGES_KALI.encode())
    distros = Distribuciones(transport=_transporte({fuentes.KALI_PACKAGES: httpx.Response(200, content=contenido)}))

    assert "sqlmap" in distros.kali()


def test_db_blackarch_con_grupos() -> None:
    db = _db_blackarch(
        {
            "garak-0.17.0-1": "%NAME%\ngarak\n\n%VERSION%\n0.17.0-1\n\n%DESC%\nLLM vulnerability scanner\n\n"
            "%URL%\nhttps://github.com/NVIDIA/garak\n\n%GROUPS%\nblackarch\nblackarch-ai\n\n",
            "otro-1.0-1": "%NAME%\notro\n\n%VERSION%\n1.0-1\n\n",
        }
    )
    distros = Distribuciones(transport=_transporte({fuentes.BLACKARCH_DB: httpx.Response(200, content=db)}))

    paquetes = distros.blackarch()

    assert paquetes["garak"].grupos == ["blackarch", "blackarch-ai"]
    assert paquetes["garak"].url == "https://github.com/NVIDIA/garak"
    assert paquetes["otro"].grupos == []


def test_indice_corrupto_o_caido_es_fuente_error() -> None:
    caido = Distribuciones(transport=_transporte({}))
    with pytest.raises(FuenteError, match="404"):
        caido.parrot()

    corrupto = Distribuciones(transport=_transporte({fuentes.KALI_PACKAGES: httpx.Response(200, content=b"no es gzip")}))
    with pytest.raises(FuenteError, match="ilegible"):
        corrupto.kali()
