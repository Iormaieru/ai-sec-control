"""Análisis legible de una alerta de Netskope (quién, desde dónde, qué hizo, contra qué, Netskope)."""

import datetime as dt

from app.alertas.analisis import Nivel, analizar
from app.alertas.models import Alerta, SeveridadAlerta

AHORA = dt.datetime(2026, 10, 19, 12, tzinfo=dt.UTC)


def _alerta(usuario: str, app: str, actividades: dict[str, int], equipos: list[str]) -> Alerta:
    return Alerta(
        usuario=usuario, app=app, actividades=actividades, equipos=equipos, severidad=SeveridadAlerta.ALTA,
        primera_vez=AHORA, ultima_vez=AHORA,
    )


def _por_aspecto(alerta: Alerta, datos: list[dict], fuera: set[str] = frozenset()) -> dict[str, tuple[str, Nivel]]:
    return {a.aspecto: (a.texto, a.nivel) for a in analizar(alerta, datos, set(fuera))}


KATALON = {
    "os": "Windows 11", "url": "mcp.katalon.com/mcp", "action": "allow", "policy": "[WEB] Grupo 2 Alert",
    "hostname": "VDIEXT109", "process_name": "katalon.exe", "mcp_server_name": "Katalon Public MCP Server",
    "agentic_protocol": "MCP",
}


def test_tercero_que_solo_descubre_herramientas() -> None:
    alerta = _alerta(
        "JuanVaccaro@bmexternos.com.ar", "Katalon",
        {"InitializeRequest": 1, "InitializeResult": 1, "InitializedNotification": 1, "ListToolsRequest": 1, "ListToolsResult": 1},
        ["vdiext109"],
    )
    datos = [{**KATALON, "activity": a} for a in alerta.actividades]

    a = _por_aspecto(alerta, datos, {"vdiext109"})

    assert a["Quién"][1] == Nivel.ALTO and "tercero" in a["Quién"][0]
    assert a["Desde dónde"] == ("VDI de externos (VDIEXT109), Windows 11 · fuera de Tenable", Nivel.MEDIO)
    assert a["Qué hizo"] == ("Sólo el saludo del protocolo (Initialize, ListTools): no ejecutó ninguna herramienta", Nivel.BAJO)
    assert a["Contra qué"] == ("Servidor MCP Katalon Public MCP Server (mcp.katalon.com) · desde la app katalon.exe", Nivel.INFO)
    assert a["Netskope"] == ("Ya lo marca su política «[WEB] Grupo 2 Alert» (acción: allow)", Nivel.INFO)


def test_conector_de_claude_que_ejecuta_herramientas() -> None:
    alerta = _alerta("ana@macro.com.ar", "Anthropic Claude", {"CallToolRequest": 2, "ListToolsResult": 1}, ["bmn1"])
    base = {"url": "claude.ai/v1/toolbox/shttp/mcp/x", "process_name": "chrome.exe", "agentic_protocol": "MCP",
            "mcp_server_name": "drivemcp", "ccl": "high", "cci": 81}
    datos = [
        {**base, "activity": "CallToolRequest", "mcp_tool_name": "list_recent_files"},
        {**base, "activity": "CallToolRequest", "mcp_tool_name": "list_recent_files"},
        {**base, "activity": "ListToolsResult", "mcp_tool_list": "read_file_content, share_file, trash_file"},
    ]

    a = _por_aspecto(alerta, datos)

    assert a["Quién"] == ("Usuario interno: ana@macro.com.ar", Nivel.INFO)
    assert a["Desde dónde"][0].endswith("inventariado en Tenable")
    assert a["Qué hizo"] == ("Ejecutó herramientas 2 veces: list_recent_files (2 veces)", Nivel.ALTO)
    texto, nivel = a["Contra qué"]
    assert texto.startswith("Conector de Claude.ai (servicio de Anthropic): drivemcp")
    assert "puede leer, compartir y borrar datos" in texto and "desde el navegador" in texto
    assert nivel == Nivel.MEDIO  # sus herramientas pueden compartir y borrar
    assert a["Netskope"][1] == Nivel.MEDIO  # sin política


def test_subida_a_app_de_baja_confianza_y_uso_por_script() -> None:
    subida = _alerta("ana@macro.com.ar", "DeepSeek", {"Upload": 3, "Post": 1}, [])
    a = _por_aspecto(subida, [{"url": "chat.deepseek.com/", "ccl": "poor", "cci": 12, "process_name": "chrome.exe",
                               "action": "block", "policy": "Bloqueo IA"}])
    assert a["Qué hizo"] == ("Subió archivos 3 veces, envió prompts 1 vez", Nivel.ALTO)
    assert a["Contra qué"][1] == Nivel.ALTO and "muy bajo (CCI 12)" in a["Contra qué"][0]
    assert a["Netskope"] == ("Lo bloqueó la política «Bloqueo IA»", Nivel.BAJO)
    assert a["Desde dónde"][0] == "Equipo no informado por Netskope"

    script = _alerta("ana@macro.com.ar", "DeepSeek", {"Response": 2}, [])
    a = _por_aspecto(script, [{"url": "api.deepseek.com/v1", "process_name": "python.exe", "ccl": "medium"}])
    assert a["Qué hizo"][0] == "Recibió respuestas 2 veces"
    assert "por código o script (python.exe)" in a["Contra qué"][0] and a["Contra qué"][1] == Nivel.MEDIO


def test_servidor_mcp_por_ip() -> None:
    alerta = _alerta("ana@macro.com.ar", "MCP: 130.211.4.15", {"Browse": 1}, [])
    a = _por_aspecto(alerta, [{"url": "130.211.4.15/mcp", "process_name": "postman.exe"}])
    assert a["Contra qué"] == ("Servidor MCP sin nombre, por IP (130.211.4.15) · desde la app postman.exe", Nivel.ALTO)
