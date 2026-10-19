"""Análisis legible de una alerta de Netskope: quién, desde dónde, qué hizo,
contra qué y qué dice Netskope, con un nivel por aspecto.

Se arma con reglas fijas a partir de la evidencia de los eventos (los campos
que guarda app.alertas.netskope) y del inventario de Tenable: el mismo evento
da siempre la misma lectura y ningún dato sale de la plataforma. La idea es
distinguir, por ejemplo, un agente ejecutando herramientas de un simple
descubrimiento del protocolo MCP, o un tercero de un usuario interno.
"""

import enum
import re
from collections import Counter
from collections.abc import Iterable

from pydantic import BaseModel

from app.alertas.models import Alerta

DOMINIO_EXTERNOS = "bmexternos"
NAVEGADORES = {"chrome.exe", "msedge.exe", "firefox.exe", "iexplore.exe", "brave.exe", "opera.exe", "safari"}
SCRIPTS = {"python.exe", "pythonw.exe", "python", "python3", "node.exe", "node", "curl.exe", "curl", "powershell.exe", "pwsh.exe", "java.exe", "javaw.exe"}
# Herramientas de un servidor MCP que modifican o comparten datos (por nombre).
_HERRAMIENTA_SENSIBLE = re.compile(r"share|trash|delete|remove|write|create|update|send|upload|move|copy", re.IGNORECASE)
_CAPACIDADES = [
    (re.compile(r"read|download|get_file|content", re.IGNORECASE), "leer"),
    (re.compile(r"share|permission", re.IGNORECASE), "compartir"),
    (re.compile(r"trash|delete|remove", re.IGNORECASE), "borrar"),
    (re.compile(r"create|update|write|upload", re.IGNORECASE), "crear o modificar"),
    (re.compile(r"send", re.IGNORECASE), "enviar"),
]
_ACCIONES = {
    "Download": "descargó",
    "Response": "recibió respuestas",
    "AI Response": "recibió respuestas",
    "Login Successful": "inició sesión",
    "Login Attempt": "intentó iniciar sesión",
    "Browse": "navegó",
    "Reload": "recargó la página",
    "Create": "creó contenido",
    "Edit": "editó",
    "Delete": "borró",
    "Share": "compartió",
}
_POR_IP = re.compile(r"^(mcp:\s*)?\d{1,3}(\.\d{1,3}){3}")


class Nivel(str, enum.Enum):
    ALTO = "alto"
    MEDIO = "medio"
    BAJO = "bajo"
    INFO = "info"


class AspectoOut(BaseModel):
    aspecto: str
    texto: str
    nivel: Nivel


def _valores(datos: list[dict], campo: str) -> list[str]:
    """Valores distintos de un campo en los eventos, del más frecuente al menos."""
    conteo = Counter(str(d[campo]) for d in datos if d.get(campo) not in (None, ""))
    return [v for v, _ in conteo.most_common()]


def _lista(valores: Iterable[str], maximo: int = 3) -> str:
    valores = list(valores)
    texto = ", ".join(valores[:maximo])
    return texto + (f" y {len(valores) - maximo} más" if len(valores) > maximo else "")


def _veces(n: int) -> str:
    return "1 vez" if n == 1 else f"{n} veces"


def _quien(alerta: Alerta) -> AspectoOut:
    if DOMINIO_EXTERNOS in alerta.usuario.lower():
        return AspectoOut(aspecto="Quién", texto=f"Un tercero (@{DOMINIO_EXTERNOS}): {alerta.usuario}", nivel=Nivel.ALTO)
    return AspectoOut(aspecto="Quién", texto=f"Usuario interno: {alerta.usuario}", nivel=Nivel.INFO)


def _desde_donde(alerta: Alerta, datos: list[dict], fuera_de_tenable: set[str]) -> AspectoOut:
    equipos = alerta.equipos or [h.lower().split(".")[0] for h in _valores(datos, "hostname")]
    sistema = _valores(datos, "os")
    partes = []
    if any(e.startswith("vdiext") for e in equipos):
        partes.append(f"VDI de externos ({_lista(e.upper() for e in equipos)})")
    elif equipos:
        partes.append(f"Equipo {_lista(e.upper() for e in equipos)}")
    else:
        partes.append("Equipo no informado por Netskope")
    if sistema:
        partes[-1] += f", {sistema[0]}"
    nivel = Nivel.INFO
    fuera = [e for e in equipos if e in fuera_de_tenable]
    if fuera:
        partes.append("fuera de Tenable" if len(fuera) == len(equipos) else f"{_lista(e.upper() for e in fuera)} fuera de Tenable")
        nivel = Nivel.MEDIO
    elif equipos:
        partes.append("inventariado en Tenable")
    ubicacion = _valores(datos, "src_location")
    if ubicacion:
        partes.append(f"desde {ubicacion[0]}")
    return AspectoOut(aspecto="Desde dónde", texto=" · ".join(partes), nivel=nivel)


def _es_descubrimiento(actividad: str) -> bool:
    return actividad.startswith(("Initialize", "List", "Discover")) or actividad.endswith("Notification")


def _que_hizo(alerta: Alerta, datos: list[dict], es_mcp: bool) -> AspectoOut:
    actividades = alerta.actividades or {}
    if es_mcp:
        ejecuciones = actividades.get("CallToolRequest", 0)
        if ejecuciones:
            herramientas = Counter(
                d["mcp_tool_name"] for d in datos if d.get("activity") == "CallToolRequest" and d.get("mcp_tool_name")
            )
            detalle = (
                ": " + _lista(f"{h} ({_veces(n)})" for h, n in herramientas.most_common())
                if herramientas
                else " (los eventos guardados no indican cuáles)"
            )
            return AspectoOut(
                aspecto="Qué hizo", texto=f"Ejecutó herramientas {_veces(ejecuciones)}{detalle}", nivel=Nivel.ALTO
            )
        if all(_es_descubrimiento(a) for a in actividades):
            pasos = _lista(sorted({re.sub(r"(d?Notification|Request|Result)$", "", a) for a in actividades}))
            return AspectoOut(
                aspecto="Qué hizo",
                texto=f"Sólo el saludo del protocolo ({pasos}): no ejecutó ninguna herramienta",
                nivel=Nivel.BAJO,
            )
    acciones = []
    nivel = Nivel.INFO
    for actividad, n in sorted(actividades.items(), key=lambda x: -x[1]):
        if actividad == "Upload":
            acciones.append(f"subió archivos {_veces(n)}")
            nivel = Nivel.ALTO
        elif actividad in ("Post", "AI Post"):
            acciones.append(f"envió prompts {_veces(n)}")
            nivel = Nivel.MEDIO if nivel != Nivel.ALTO else nivel
        elif actividad in _ACCIONES:
            acciones.append(f"{_ACCIONES[actividad]} {_veces(n)}")
        else:
            acciones.append(f"{actividad} ({_veces(n)})")
    texto = _lista(acciones, maximo=4) if acciones else "Sin actividad registrada"
    return AspectoOut(aspecto="Qué hizo", texto=texto[:1].upper() + texto[1:], nivel=nivel)


def _contra_que(alerta: Alerta, datos: list[dict], es_mcp: bool) -> AspectoOut:
    urls = _valores(datos, "url")
    dominio = urls[0].split("/")[0] if urls else None
    procesos = _valores(datos, "process_name")
    proceso = procesos[0].lower() if procesos else None
    nivel = Nivel.INFO
    partes = []

    if es_mcp:
        servidor = _valores(datos, "mcp_server_name")
        conector_claude = any(u.startswith("claude.ai/v1/toolbox") for u in urls)
        if conector_claude:
            partes.append(f"Conector de Claude.ai (servicio de Anthropic){': ' + servidor[0] if servidor else ''}")
        elif _POR_IP.match(alerta.app.lower()) or (dominio and _POR_IP.match(dominio)):
            partes.append(f"Servidor MCP sin nombre, por IP ({dominio or alerta.app})")
            nivel = Nivel.ALTO
        else:
            nombre = servidor[0] if servidor else alerta.app
            partes.append(f"Servidor MCP {nombre}" + (f" ({dominio})" if dominio else ""))
        herramientas = [h.strip() for lista in _valores(datos, "mcp_tool_list") for h in lista.split(",") if h.strip()]
        capacidades = [nombre for patron, nombre in _CAPACIDADES if any(patron.search(h) for h in herramientas)]
        if capacidades:
            enumeracion = ", ".join(capacidades[:-1]) + " y " + capacidades[-1] if len(capacidades) > 1 else capacidades[0]
            partes.append(f"puede {enumeracion} datos")
            if any(_HERRAMIENTA_SENSIBLE.search(h) for h in herramientas):
                nivel = max(nivel, Nivel.MEDIO, key=_ORDEN.index)
    else:
        partes.append(f"{alerta.app}" + (f" ({dominio})" if dominio else ""))
        categoria = _valores(datos, "category")
        if categoria:
            partes.append(f"categoría {categoria[0]}")

    if proceso:
        if proceso in NAVEGADORES:
            partes.append(f"desde el navegador ({proceso})")
        elif proceso in SCRIPTS:
            partes.append(f"por código o script ({proceso})")
            nivel = max(nivel, Nivel.MEDIO, key=_ORDEN.index)
        else:
            partes.append(f"desde la app {proceso}")

    riesgo = _valores(datos, "ccl")
    if riesgo:
        ccl = riesgo[0].lower()
        cci = _valores(datos, "cci")
        etiqueta = {"poor": "muy bajo", "low": "bajo", "medium": "medio", "high": "alto", "excellent": "excelente"}.get(ccl, ccl)
        partes.append(f"confianza de la app según Netskope: {etiqueta}" + (f" (CCI {cci[0]})" if cci else ""))
        if ccl in ("poor", "low"):
            nivel = Nivel.ALTO
    return AspectoOut(aspecto="Contra qué", texto=" · ".join(partes), nivel=nivel)


def _netskope(datos: list[dict]) -> AspectoOut:
    politicas = _valores(datos, "policy")
    acciones = {a.lower() for a in _valores(datos, "action")}
    if "block" in acciones:
        return AspectoOut(
            aspecto="Netskope", texto=f"Lo bloqueó{' la política «' + politicas[0] + '»' if politicas else ''}", nivel=Nivel.BAJO
        )
    if politicas:
        accion = f" (acción: {_lista(sorted(acciones))})" if acciones else ""
        return AspectoOut(aspecto="Netskope", texto=f"Ya lo marca su política «{_lista(politicas, 2)}»{accion}", nivel=Nivel.INFO)
    return AspectoOut(
        aspecto="Netskope", texto="Sin política: Netskope no lo alerta ni lo bloquea por su cuenta", nivel=Nivel.MEDIO
    )


_ORDEN = [Nivel.INFO, Nivel.BAJO, Nivel.MEDIO, Nivel.ALTO]


def analizar(alerta: Alerta, datos: list[dict], fuera_de_tenable: set[str]) -> list[AspectoOut]:
    """`datos`: la evidencia de los eventos de la alerta (AlertaEvento.datos).
    `fuera_de_tenable`: los equipos de la alerta que Tenable no inventaría."""
    es_mcp = any(d.get("agentic_protocol") == "MCP" or d.get("mcp_activity") for d in datos) or alerta.app.lower().startswith("mcp")
    return [
        _quien(alerta),
        _desde_donde(alerta, datos, fuera_de_tenable),
        _que_hizo(alerta, datos, es_mcp),
        _contra_que(alerta, datos, es_mcp),
        _netskope(datos),
    ]
