"""Criterios de "herramienta que sirve" (tasks/herramientas-radar.md, sección 5).

Funciones puras: reciben lo que dijeron las fuentes y devuelven señales,
estado y novedades. No tocan la base.
"""

import datetime as dt
import re
from dataclasses import dataclass, field

from app.pentesting.models import EstadoHerramienta

from aisec_worker.herramientas.fuentes import RepoGitHub

VERDE, AMARILLO, ROJO, SIN_DATOS = "verde", "amarillo", "rojo", "sin_datos"

ESTRELLAS_ADOPTADA = 500
ESTRELLAS_MINIMAS = 100
ACTIVIDAD_RECIENTE = dt.timedelta(days=365)
ACTIVIDAD_TOLERABLE = dt.timedelta(days=730)


@dataclass
class DatosFuentes:
    """Lo que se sabe de una herramienta en esta revisión."""

    repo: RepoGitHub | None = None
    repo_esperado: str | None = None  # el "owner/nombre" registrado, para detectar mudanzas
    version_publicada: str | None = None  # PyPI / npm
    fecha_version: dt.datetime | None = None
    distribuciones: list[dict] = field(default_factory=list)  # [{"distribucion": "kali", "version": ...}]
    licencia_registrada: str | None = None  # cargada a mano (ej. comerciales, o GitHub no la reconoce)


@dataclass
class Evaluacion:
    senales: dict[str, str]
    motivo: str | None  # por qué no está "mantenida" (si no lo está)


def evaluar(datos: DatosFuentes, ahora: dt.datetime) -> Evaluacion:
    repo = datos.repo
    en_distros = len({d["distribucion"] for d in datos.distribuciones})
    senales = {
        "mantenida": _mantenida(datos, ahora),
        "adoptada": _adoptada(repo, en_distros),
        "instalable": VERDE if datos.version_publicada or en_distros else (ROJO if repo else SIN_DATOS),
        "licencia": _licencia(repo, datos.licencia_registrada),
    }
    return Evaluacion(senales=senales, motivo=_motivo(datos, ahora) if senales["mantenida"] == ROJO else None)


def _licencia(repo: RepoGitHub | None, registrada: str | None) -> str:
    if (repo and repo.licencia) or registrada:
        return VERDE
    return AMARILLO if repo else SIN_DATOS


def limpiar_version(version: str) -> str:
    """Versión empaquetada -> versión de la herramienta:
    "1:2026.8-0kali1" -> "2026.8", "0.17.0.r8.gbb30a7e-1" -> "0.17.0"."""
    sin_epoca = version.split(":", 1)[-1]
    sin_revision = sin_epoca.rsplit("-", 1)[0] if "-" in sin_epoca else sin_epoca
    return re.split(r"\.r\d+\.g[0-9a-f]+|\+", sin_revision)[0]


def _ultima_actividad(datos: DatosFuentes) -> dt.datetime | None:
    fechas = [f for f in (datos.repo.ultimo_push if datos.repo else None, datos.fecha_version) if f]
    return max(fechas) if fechas else None


def _mantenida(datos: DatosFuentes, ahora: dt.datetime) -> str:
    if datos.repo and datos.repo.archivado:
        return ROJO
    ultima = _ultima_actividad(datos)
    if ultima is None:
        # Sin repo (ej. Burp Suite): si una distribución la sigue empaquetando, se da por mantenida.
        return VERDE if datos.distribuciones else SIN_DATOS
    antiguedad = ahora - ultima
    if antiguedad <= ACTIVIDAD_RECIENTE:
        return VERDE
    return AMARILLO if antiguedad <= ACTIVIDAD_TOLERABLE else ROJO


def _adoptada(repo: RepoGitHub | None, en_distros: int) -> str:
    estrellas = repo.estrellas if repo else 0
    if estrellas >= ESTRELLAS_ADOPTADA or en_distros >= 2:
        return VERDE
    if estrellas >= ESTRELLAS_MINIMAS or en_distros == 1:
        return AMARILLO
    return ROJO if repo else SIN_DATOS


def _motivo(datos: DatosFuentes, ahora: dt.datetime) -> str:
    if datos.repo and datos.repo.archivado:
        return f"El repositorio {datos.repo.nombre} está archivado en GitHub"
    ultima = _ultima_actividad(datos)
    return f"Sin actividad desde {ultima.date().isoformat()}" if ultima else "Sin datos de actividad"


def es_candidata(evaluacion: Evaluacion) -> bool:
    """Al Radar entran sólo las mantenidas y adoptadas."""
    return evaluacion.senales["mantenida"] == VERDE and evaluacion.senales["adoptada"] == VERDE


def repo_mudado(datos: DatosFuentes) -> str | None:
    """El nuevo "owner/nombre" si GitHub redirigió el repo registrado."""
    if datos.repo and datos.repo_esperado and datos.repo.nombre.lower() != datos.repo_esperado.lower():
        return datos.repo.nombre
    return None


def nuevo_estado(actual: EstadoHerramienta, evaluacion: Evaluacion) -> tuple[EstadoHerramienta, str | None]:
    """Transiciones automáticas del Catálogo: activa <-> en observación.
    Candidatas, retiradas y descartadas sólo cambian por decisión de un analista."""
    mantenida = evaluacion.senales["mantenida"]
    if actual == EstadoHerramienta.ACTIVA and mantenida == ROJO:
        return EstadoHerramienta.EN_OBSERVACION, evaluacion.motivo
    if actual == EstadoHerramienta.EN_OBSERVACION and mantenida in (VERDE, AMARILLO):
        return EstadoHerramienta.ACTIVA, None
    return actual, evaluacion.motivo if actual == EstadoHerramienta.EN_OBSERVACION else None


def novedades(
    *,
    version_anterior: str | None,
    version_nueva: str | None,
    estado_anterior: EstadoHerramienta,
    estado_nuevo: EstadoHerramienta,
    motivo: str | None,
    mudado_a: str | None,
) -> list[str]:
    """Qué cambió en esta revisión, para mostrar en el Catálogo."""
    cambios = []
    if version_nueva and version_anterior and version_nueva != version_anterior:
        cambios.append(f"Nueva versión {version_nueva} (antes {version_anterior})")
    if mudado_a:
        cambios.append(f"El repositorio se mudó a {mudado_a}")
    if estado_nuevo != estado_anterior:
        if estado_nuevo == EstadoHerramienta.EN_OBSERVACION:
            cambios.append(f"Pasó a observación: {motivo}")
        elif estado_nuevo == EstadoHerramienta.ACTIVA:
            cambios.append("Volvió a tener actividad")
    return cambios
