"""Revisión periódica de herramientas (tasks/herramientas-radar.md, sección 7).

1. Distribuciones: lee los índices de Kali, Parrot y BlackArch y actualiza
   sus fichas (versión, categorías, cantidad de herramientas).
2. Catálogo: actualiza cada herramienta con GitHub, PyPI/npm y las
   distribuciones, recalcula sus señales y pasa a observación (o vuelve) las
   que dejaron de cumplir los criterios.
3. Radar: descubre herramientas de seguridad de IA (temas de GitHub y el
   grupo blackarch-ai) que cumplen los criterios y no están ni fueron
   descartadas, y las suma como candidatas con los vínculos sugeridos por IA.

Si una fuente falla, se anota el error y la revisión sigue con el resto.
"""

import datetime as dt
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.pentesting.models import (
    Distribucion,
    EstadoHerramienta,
    EstadoRevision,
    HerramientaPentest,
    RevisionHerramientas,
    TipoHerramienta,
)

from aisec_worker.herramientas import evaluacion
from aisec_worker.herramientas.fuentes import Distribuciones, FuenteError, GitHub, Paquete, Registros, RepoGitHub
from aisec_worker.herramientas.vinculos import sugerir_vinculos

logger = logging.getLogger(__name__)

TEMAS_IA = ["llm-security", "ai-red-teaming", "prompt-injection", "adversarial-machine-learning", "ai-security"]
GRUPO_BLACKARCH_IA = "blackarch-ai"
MAX_CANDIDATAS_POR_REVISION = 25  # acota el costo de las sugerencias con LLM
MAX_DESTACADAS = 50

# Prefijo de los metapaquetes / grupos de categoría de cada distribución.
_PREFIJO_CATEGORIA = {"kali": "kali-tools-", "parrot": "parrot-tools-", "blackarch": "blackarch-"}
# Metapaquetes que agrupan otros metapaquetes, no herramientas.
_NO_SON_CATEGORIAS = {"parrot-tools-full", "kali-tools-all"}
_RE_GITHUB = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?/?$", re.IGNORECASE)


@dataclass
class Fuentes:
    github: GitHub
    registros: Registros
    distribuciones: Distribuciones


@dataclass
class ResultadoRevision:
    resumen: dict[str, int] = field(default_factory=dict)
    errores: list[str] = field(default_factory=list)

    def contar(self, clave: str, n: int = 1) -> None:
        self.resumen[clave] = self.resumen.get(clave, 0) + n


# --- distribuciones ---


@dataclass
class IndiceDistro:
    paquetes: dict[str, Paquete]
    categorias_de: dict[str, list[str]]  # paquete -> categorías ("web", "vuln", ...)
    por_nombre: dict[str, Paquete] = field(default_factory=dict)  # nombre en minúsculas
    por_url: dict[str, Paquete] = field(default_factory=dict)  # web declarada, en minúsculas y sin "/" final

    def __post_init__(self) -> None:
        for p in self.paquetes.values():
            self.por_nombre.setdefault(p.nombre.lower(), p)
            if p.url:
                self.por_url.setdefault(p.url.lower().rstrip("/"), p)


def _nombre_categoria(codigo: str, prefijo: str) -> str:
    return codigo.removeprefix(prefijo).replace("-", " ").capitalize()


def _version_base_files(paquetes: dict[str, Paquete]) -> str | None:
    """"1:2026.3.1" / "2:7.4+parrot1" -> "2026.3" / "7.4"."""
    base = paquetes.get("base-files")
    if base is None:
        return None
    numeros = re.findall(r"\d+", base.version.split(":")[-1].split("+")[0].split("-")[0])
    return ".".join(numeros[:2]) or None


def _indexar(codigo: str, paquetes: dict[str, Paquete]) -> tuple[IndiceDistro, dict]:
    """Índice paquete -> categorías y datos de la ficha de la distribución."""
    prefijo = _PREFIJO_CATEGORIA[codigo]
    categorias: dict[str, list[str]] = {}
    if codigo == "blackarch":
        for p in paquetes.values():
            for grupo in p.grupos:
                if grupo != "blackarch":
                    categorias.setdefault(grupo, []).append(p.nombre)
        herramientas = {p.nombre for p in paquetes.values() if "blackarch" in p.grupos}
        version = "rolling"
    else:
        metas = {n for n in paquetes if n.startswith(prefijo) and n not in _NO_SON_CATEGORIAS}
        for meta in metas:
            categorias[meta] = sorted({d for d in paquetes[meta].depende_de if d not in metas})
        herramientas = {h for lista in categorias.values() for h in lista}
        version = _version_base_files(paquetes)

    categorias_de: dict[str, list[str]] = {}
    for cat, nombres in categorias.items():
        for nombre in nombres:
            categorias_de.setdefault(nombre, []).append(_nombre_categoria(cat, prefijo))
    ficha = {
        "version": version,
        "cantidad_herramientas": len(herramientas),
        "categorias": [
            {
                "codigo": cat,
                "nombre": _nombre_categoria(cat, prefijo),
                "cantidad": len(nombres),
                "destacadas": sorted(nombres)[:MAX_DESTACADAS],
            }
            for cat, nombres in sorted(categorias.items())
        ],
    }
    return IndiceDistro(paquetes=paquetes, categorias_de=categorias_de), ficha


def revisar_distribuciones(db: Session, fuentes: Fuentes, ahora: dt.datetime, resultado: ResultadoRevision) -> dict[str, IndiceDistro]:
    indices: dict[str, IndiceDistro] = {}
    lectores: dict[str, Callable[[], dict[str, Paquete]]] = {
        "kali": fuentes.distribuciones.kali,
        "parrot": fuentes.distribuciones.parrot,
        "blackarch": fuentes.distribuciones.blackarch,
    }
    for codigo, leer in lectores.items():
        try:
            indice, ficha = _indexar(codigo, leer())
        except FuenteError as exc:
            resultado.errores.append(f"Distribución {codigo}: {exc}")
            continue
        indices[codigo] = indice
        distro = db.scalar(select(Distribucion).where(Distribucion.codigo == codigo))
        if distro is not None:
            distro.version = ficha["version"]
            distro.cantidad_herramientas = ficha["cantidad_herramientas"]
            distro.categorias = ficha["categorias"]
            distro.revisada_at = ahora
            resultado.contar("distribuciones_actualizadas")
    db.commit()
    return indices


def _nombres_posibles(nombre: str, repo: str | None, paquete: str | None) -> set[str]:
    nombres = {nombre.lower(), nombre.lower().replace(" ", ""), nombre.lower().replace(" ", "-")}
    if repo:
        nombres.add(repo.split("/")[-1].lower())
    if paquete:
        nombres.add(paquete.partition(":")[2].lower())
    return nombres


def en_distribuciones(indices: dict[str, IndiceDistro], nombre: str, repo: str | None, paquete: str | None) -> list[dict]:
    """Dónde está empaquetada la herramienta: por nombre de paquete o, si el
    paquete declara como web el repo de GitHub, por URL."""
    posibles = _nombres_posibles(nombre, repo, paquete)
    url_repo = f"https://github.com/{repo}".lower() if repo else None
    encontradas = []
    for codigo, indice in indices.items():
        p = next((indice.por_nombre[n] for n in sorted(posibles) if n in indice.por_nombre), None)
        if p is None and url_repo:
            p = indice.por_url.get(url_repo)
        if p is not None:
            encontradas.append(
                {
                    "distribucion": codigo,
                    "paquete": p.nombre,
                    "version": p.version,
                    "categorias": indice.categorias_de.get(p.nombre, []),
                }
            )
    return encontradas


# --- catálogo ---


def _version_publicada(fuentes: Fuentes, paquete: str | None, resultado: ResultadoRevision, nombre: str):
    if not paquete:
        return None
    try:
        return fuentes.registros.version(paquete)
    except FuenteError as exc:
        resultado.errores.append(f"{nombre}: versión en {paquete}: {exc}")
        return None


def revisar_catalogo(
    db: Session, fuentes: Fuentes, indices: dict[str, IndiceDistro], ahora: dt.datetime, resultado: ResultadoRevision,
    detener: Callable[[], bool],
) -> None:
    herramientas = db.scalars(
        select(HerramientaPentest).where(
            HerramientaPentest.estado.in_(
                [EstadoHerramienta.ACTIVA, EstadoHerramienta.EN_OBSERVACION, EstadoHerramienta.CANDIDATA]
            )
        )
    ).all()
    for h in herramientas:
        if detener():
            return
        repo: RepoGitHub | None = None
        if h.repo_github:
            try:
                repo = fuentes.github.repo(h.repo_github)
            except FuenteError as exc:
                resultado.errores.append(f"{h.nombre}: GitHub: {exc}")
                continue  # sin datos de mantenimiento no se reevalúa: queda como estaba
        publicada = _version_publicada(fuentes, h.paquete, resultado, h.nombre)
        # Si un índice no se pudo leer, se conservan los datos anteriores de esa distribución.
        distros = en_distribuciones(indices, h.nombre, h.repo_github, h.paquete) + [
            d for d in h.distribuciones if d["distribucion"] not in indices
        ]
        datos = evaluacion.DatosFuentes(
            repo=repo,
            repo_esperado=h.repo_github,
            version_publicada=publicada.version if publicada else None,
            fecha_version=publicada.fecha if publicada else None,
            distribuciones=distros,
            licencia_registrada=h.licencia if not (repo and repo.licencia) else None,
        )
        ev = evaluacion.evaluar(datos, ahora)
        mudado_a = evaluacion.repo_mudado(datos)
        estado, motivo = evaluacion.nuevo_estado(h.estado, ev)
        version = datos.version_publicada or (
            evaluacion.limpiar_version(distros[0]["version"]) if distros else h.version
        )

        cambios = evaluacion.novedades(
            version_anterior=h.version,
            version_nueva=version,
            estado_anterior=h.estado,
            estado_nuevo=estado,
            motivo=motivo,
            mudado_a=mudado_a,
        )
        if mudado_a and not _repo_registrado(db, mudado_a, excepto=h.id):
            h.repo_github = mudado_a
        if repo:
            h.estrellas = repo.estrellas
            h.ultima_actividad = repo.ultimo_push
            h.archivada = repo.archivado
            h.temas = repo.temas
            h.licencia = repo.licencia or h.licencia
            h.descripcion = h.descripcion or repo.descripcion
        if estado != h.estado:
            resultado.contar("a_observacion" if estado == EstadoHerramienta.EN_OBSERVACION else "reactivadas")
        h.estado, h.motivo_estado = estado, motivo
        h.version = version
        h.distribuciones = distros
        h.senales = ev.senales
        h.revisada_at = ahora
        h.novedad = "; ".join(cambios) or None
        resultado.contar("catalogo_actualizadas")
        db.commit()


def _repo_registrado(db: Session, repo: str, excepto=None) -> bool:
    stmt = select(HerramientaPentest.id).where(func.lower(HerramientaPentest.repo_github) == repo.lower())
    if excepto is not None:
        stmt = stmt.where(HerramientaPentest.id != excepto)
    return db.scalar(stmt) is not None


# --- radar ---


def _candidatos(fuentes: Fuentes, indices: dict[str, IndiceDistro], ahora: dt.datetime, resultado: ResultadoRevision) -> dict[str, tuple[RepoGitHub, str]]:
    """repo (en minúsculas) -> (datos del repo, origen)."""
    encontrados: dict[str, tuple[RepoGitHub, str]] = {}
    desde = (ahora - evaluacion.ACTIVIDAD_RECIENTE).date()
    for tema in TEMAS_IA:
        try:
            repos = fuentes.github.buscar_por_tema(tema, min_estrellas=evaluacion.ESTRELLAS_ADOPTADA, activos_desde=desde)
        except FuenteError as exc:
            resultado.errores.append(f"GitHub, tema {tema}: {exc}")
            continue
        for repo in repos:
            encontrados.setdefault(repo.nombre.lower(), (repo, f"github:{tema}"))

    blackarch = indices.get("blackarch")
    for p in (blackarch.paquetes.values() if blackarch else []):
        if GRUPO_BLACKARCH_IA not in p.grupos or not (m := _RE_GITHUB.match(p.url or "")):
            continue
        if m.group(1).lower() in encontrados:
            continue
        try:
            repo = fuentes.github.repo(m.group(1))
        except FuenteError as exc:
            resultado.errores.append(f"GitHub, {m.group(1)}: {exc}")
            continue
        encontrados.setdefault(repo.nombre.lower(), (repo, GRUPO_BLACKARCH_IA))
    return encontrados


def _nombre_libre(db: Session, repo: RepoGitHub) -> str:
    corto = repo.nombre.split("/")[-1]
    existe = db.scalar(select(HerramientaPentest.id).where(func.lower(HerramientaPentest.nombre) == corto.lower()))
    return repo.nombre if existe else corto


def descubrir(
    db: Session, fuentes: Fuentes, provider: LLMProvider | None, indices: dict[str, IndiceDistro], ahora: dt.datetime,
    resultado: ResultadoRevision, detener: Callable[[], bool],
) -> None:
    candidatos = sorted(_candidatos(fuentes, indices, ahora, resultado).values(), key=lambda c: -c[0].estrellas)
    nuevas = 0
    for repo, origen in candidatos:
        if detener() or nuevas >= MAX_CANDIDATAS_POR_REVISION:
            return
        conocida = db.scalar(
            select(HerramientaPentest.id).where(
                or_(
                    func.lower(HerramientaPentest.repo_github) == repo.nombre.lower(),
                    func.lower(HerramientaPentest.nombre) == repo.nombre.split("/")[-1].lower(),
                )
            )
        )
        if conocida:
            continue  # ya está en el Catálogo o en el Radar, o fue descartada
        distros = en_distribuciones(indices, repo.nombre.split("/")[-1], repo.nombre, None)
        ev = evaluacion.evaluar(evaluacion.DatosFuentes(repo=repo, distribuciones=distros), ahora)
        if not evaluacion.es_candidata(ev):
            continue

        herramienta = HerramientaPentest(
            nombre=_nombre_libre(db, repo),
            descripcion=repo.descripcion,
            url_referencia=repo.url,
            tipo=TipoHerramienta.IA,
            estado=EstadoHerramienta.CANDIDATA,
            origen=origen,
            repo_github=repo.nombre,
            documentacion_url=repo.homepage,
            notas_version_url=f"{repo.url}/releases",
            licencia=repo.licencia,
            estrellas=repo.estrellas,
            ultima_actividad=repo.ultimo_push,
            archivada=repo.archivado,
            temas=repo.temas,
            distribuciones=distros,
            senales=ev.senales,
            revisada_at=ahora,
            novedad="Nueva en el Radar",
        )
        db.add(herramienta)
        db.flush()
        if provider is not None:
            try:
                readme = fuentes.github.readme(repo.nombre)
            except FuenteError:
                readme = None  # sin README se sugiere igual, con descripción y temas
            try:
                resultado.contar("vinculos_sugeridos", sugerir_vinculos(db, herramienta, provider, readme))
            except Exception as exc:  # el LLM no debe frenar el descubrimiento
                resultado.errores.append(f"{herramienta.nombre}: sugerencia de vínculos: {type(exc).__name__}: {exc}")
        db.commit()
        nuevas += 1
        resultado.contar("nuevas_candidatas")


# --- ejecución ---


def revisar(
    db: Session,
    fuentes: Fuentes,
    provider: LLMProvider | None,
    *,
    ahora: dt.datetime | None = None,
    revision: RevisionHerramientas | None = None,
    detener: Callable[[], bool] = lambda: False,
) -> RevisionHerramientas:
    """Corre la revisión completa y la registra en revision_herramientas."""
    ahora = ahora or dt.datetime.now(dt.UTC)
    if revision is None:
        revision = RevisionHerramientas()
        db.add(revision)
    revision.estado = EstadoRevision.EN_CURSO
    revision.iniciada_at = ahora
    db.commit()

    resultado = ResultadoRevision()
    try:
        indices = revisar_distribuciones(db, fuentes, ahora, resultado)
        revisar_catalogo(db, fuentes, indices, ahora, resultado, detener)
        descubrir(db, fuentes, provider, indices, ahora, resultado, detener)
    except Exception as exc:
        db.rollback()
        resultado.errores.append(f"Revisión interrumpida: {type(exc).__name__}: {exc}")
        logger.exception("Falló la revisión de herramientas")

    revision.resumen = resultado.resumen
    revision.errores = resultado.errores[:200]
    revision.estado = EstadoRevision.CON_ERRORES if resultado.errores else EstadoRevision.OK
    revision.finalizada_at = dt.datetime.now(dt.UTC)
    db.commit()
    return revision


def debe_revisar(db: Session, dias: int, ahora: dt.datetime | None = None) -> RevisionHerramientas | bool:
    """Una revisión solicitada desde la plataforma (se devuelve para usarla),
    o True si pasaron `dias` desde la última que terminó."""
    solicitada = db.scalar(
        select(RevisionHerramientas)
        .where(RevisionHerramientas.estado == EstadoRevision.SOLICITADA)
        .order_by(RevisionHerramientas.iniciada_at)
    )
    if solicitada is not None:
        return solicitada
    ultima = db.scalar(
        select(func.max(RevisionHerramientas.finalizada_at)).where(
            RevisionHerramientas.estado.in_([EstadoRevision.OK, EstadoRevision.CON_ERRORES])
        )
    )
    ahora = ahora or dt.datetime.now(dt.UTC)
    return ultima is None or ahora - ultima >= dt.timedelta(days=dias)
