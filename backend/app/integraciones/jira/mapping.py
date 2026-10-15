"""Traducción entre el modelo de la plataforma y el de Jira. Sin I/O."""

import datetime as dt
import re
import unicodedata

from app.casos.models import CasoEstado
from app.casos.schemas import normalizar_gdld

PREFIJO_RESUMEN = "[IA-SEC]"

# Columnas del tablero IA-SEC (por nombre normalizado). "Backlog" no tiene
# estados asignados y no es un estado del caso.
_COLUMNAS = {
    "por hacer": CasoEstado.POR_HACER,
    "en curso": CasoEstado.EN_CURSO,
    "esperando respuesta": CasoEstado.ESPERANDO_RESPUESTA,
    "hecho": CasoEstado.HECHO,
}
# Para un status que no está en ninguna columna del tablero.
_POR_CATEGORIA = {
    "new": CasoEstado.POR_HACER,
    "indeterminate": CasoEstado.EN_CURSO,
    "done": CasoEstado.HECHO,
}


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


def estados_por_status(board_config: dict) -> dict[str, CasoEstado]:
    """status id de Jira -> columna, según la configuración del tablero."""
    mapa: dict[str, CasoEstado] = {}
    for columna in board_config.get("columnConfig", {}).get("columns", []):
        estado = _COLUMNAS.get(_normalizar(columna["name"]))
        if estado is None:
            continue
        for status in columna.get("statuses", []):
            mapa[str(status["id"])] = estado
    return mapa


def estado_de_status(status: dict, mapa: dict[str, CasoEstado]) -> CasoEstado:
    estado = mapa.get(str(status.get("id")))
    if estado is not None:
        return estado
    categoria = (status.get("statusCategory") or {}).get("key", "")
    return _POR_CATEGORIA.get(categoria, CasoEstado.POR_HACER)


# --- resumen <-> nombre del proyecto + GDLD ---

_RE_PREFIJO = re.compile(r"^\s*\[\s*IA-SEC\s*\]\s*[-–—:_]*\s*", re.IGNORECASE)
_RE_GDLD = re.compile(r"^GDLD[\s\-_]*\d+(?:-\d+)?\s*[-–—:_]*\s*", re.IGNORECASE)


def formatear_resumen(nombre_proyecto: str, gdld: str | None) -> str:
    partes = [PREFIJO_RESUMEN]
    if gdld:
        partes.append(f"GDLD-{gdld}")
    partes.append(nombre_proyecto)
    return " - ".join(partes)[:255]


def nombre_desde_resumen(resumen: str) -> str:
    """"[IA-SEC] - GDLD-10967 - MVP Intent Edge" -> "MVP Intent Edge". Los
    resúmenes cargados a mano no siguen un único formato: se saca lo que se
    reconoce y, si no queda nada, se usa el resumen tal cual."""
    nombre = _RE_GDLD.sub("", _RE_PREFIJO.sub("", resumen)).strip()
    return nombre or resumen.strip()


def gdld_desde_jira(valor: str | None) -> str | None:
    """El campo "Número de Tarjeta GDLD" viene como "GDLD-10967". Si trae
    algo que no es un número, se ignora en vez de romper la importación."""
    try:
        return normalizar_gdld(valor)
    except ValueError:
        return None


def gdld_a_jira(gdld: str | None) -> str | None:
    return f"GDLD-{gdld}" if gdld else None


def fecha_jira(valor: str) -> dt.datetime:
    """"2026-09-25T14:26:35.776-0300" -> datetime con zona."""
    return dt.datetime.strptime(valor, "%Y-%m-%dT%H:%M:%S.%f%z")


# --- texto plano <-> Atlassian Document Format ---


def texto_a_adf(texto: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": linea}] if linea else []}
            for linea in texto.split("\n")
        ],
    }


_BLOQUES = {"paragraph", "heading", "codeBlock", "blockquote", "listItem", "panel", "tableRow", "rule"}


def adf_a_texto(nodo: dict | None) -> str:
    """Aplana un documento ADF a texto: un bloque por línea; menciones, emojis
    y links quedan como texto, y los adjuntos como "[adjunto]"."""
    if not nodo:
        return ""
    partes: list[str] = []
    _aplanar(nodo, partes)
    texto = "".join(partes)
    return "\n".join(linea.rstrip() for linea in texto.strip("\n").split("\n"))


def _aplanar(nodo: dict, partes: list[str]) -> None:
    tipo = nodo.get("type")
    attrs = nodo.get("attrs") or {}
    if tipo == "text":
        partes.append(nodo.get("text", ""))
        return
    if tipo == "hardBreak":
        partes.append("\n")
        return
    if tipo == "mention":
        partes.append(attrs.get("text") or "@usuario")
        return
    if tipo == "emoji":
        partes.append(attrs.get("text") or attrs.get("shortName", ""))
        return
    if tipo in ("inlineCard", "blockCard"):
        partes.append(attrs.get("url", ""))
        return
    if tipo in ("media", "mediaInline"):
        partes.append("[adjunto]")
        return
    if tipo == "listItem":
        partes.append("- ")
    antes = len(partes)
    for hijo in nodo.get("content") or []:
        _aplanar(hijo, partes)
    # Un bloque vacío (párrafo en blanco) también es una línea.
    if tipo in _BLOQUES and (len(partes) == antes or not partes[-1].endswith("\n")):
        partes.append("\n")
