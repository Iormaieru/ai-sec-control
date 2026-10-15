import datetime as dt

import pytest

from app.casos.models import CasoEstado
from app.integraciones.jira import mapping

BOARD_CONFIG = {
    "columnConfig": {
        "columns": [
            {"name": "Backlog", "statuses": []},
            {"name": "Por hacer", "statuses": [{"id": "10261"}, {"id": "10297"}]},
            {"name": "En curso", "statuses": [{"id": "10005"}]},
            {"name": "ESPERANDO RESPUESTA", "statuses": [{"id": "11802"}]},
            {"name": "Hecho", "statuses": [{"id": "10094"}, {"id": "10190"}]},
        ]
    }
}


def test_estados_por_status_usa_las_columnas_del_tablero() -> None:
    mapa = mapping.estados_por_status(BOARD_CONFIG)

    assert mapa == {
        "10261": CasoEstado.POR_HACER,
        "10297": CasoEstado.POR_HACER,
        "10005": CasoEstado.EN_CURSO,
        "11802": CasoEstado.ESPERANDO_RESPUESTA,
        "10094": CasoEstado.HECHO,
        "10190": CasoEstado.HECHO,
    }


def test_status_fuera_del_tablero_usa_la_categoria() -> None:
    mapa = mapping.estados_por_status(BOARD_CONFIG)

    assert mapping.estado_de_status({"id": "999", "statusCategory": {"key": "done"}}, mapa) == CasoEstado.HECHO
    assert mapping.estado_de_status({"id": "998", "statusCategory": {"key": "indeterminate"}}, mapa) == (
        CasoEstado.EN_CURSO
    )


@pytest.mark.parametrize(
    ("resumen", "nombre"),
    [
        ("[IA-SEC] - GDLD-10967 - MVP Intent Edge", "MVP Intent Edge"),
        ("[IA-SEC] - GDLD 10843  Discovery Asistente Virtual", "Discovery Asistente Virtual"),
        ("[IA-SEC]-Assessment Katalon Studio (QA)", "Assessment Katalon Studio (QA)"),
        ("[IA-SEC] Gobierno Agentes IA - SAP Leanix", "Gobierno Agentes IA - SAP Leanix"),
        ("GDLD-10684_MVP Integración Plataforma Digital", "MVP Integración Plataforma Digital"),
        ("[IA-SEC] - GDLD2594-271 - Helix Bot", "Helix Bot"),
        ("Generar informe de seguridad de Rovo - Jira", "Generar informe de seguridad de Rovo - Jira"),
        ("[IA-SEC]", "[IA-SEC]"),
    ],
)
def test_nombre_desde_resumen(resumen: str, nombre: str) -> None:
    assert mapping.nombre_desde_resumen(resumen) == nombre


def test_formatear_resumen_ida_y_vuelta() -> None:
    resumen = mapping.formatear_resumen("MVP Intent Edge", "10967")

    assert resumen == "[IA-SEC] - GDLD-10967 - MVP Intent Edge"
    assert mapping.nombre_desde_resumen(resumen) == "MVP Intent Edge"
    assert mapping.formatear_resumen("POC RAN", None) == "[IA-SEC] - POC RAN"


def test_gdld_desde_jira_ignora_valores_no_numericos() -> None:
    assert mapping.gdld_desde_jira("GDLD-11724") == "11724"
    assert mapping.gdld_desde_jira("GDLD 2594-271") is None
    assert mapping.gdld_desde_jira(None) is None
    assert mapping.gdld_a_jira("11724") == "GDLD-11724"


def test_fecha_jira() -> None:
    fecha = mapping.fecha_jira("2026-09-25T14:26:35.776-0300")

    assert fecha == dt.datetime(2026, 9, 25, 17, 26, 35, 776000, tzinfo=dt.UTC)


def test_texto_adf_ida_y_vuelta() -> None:
    texto = "Primera línea\n\nTercera"

    assert mapping.adf_a_texto(mapping.texto_a_adf(texto)) == texto


def test_adf_a_texto_aplana_menciones_listas_y_adjuntos() -> None:
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "mention", "attrs": {"text": "@Malena"}},
                    {"type": "text", "text": " revisá esto"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "gracias"},
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "uno"}]}]},
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "dos"}]}]},
                ],
            },
            {"type": "mediaSingle", "content": [{"type": "media", "attrs": {"id": "x"}}]},
        ],
    }

    assert mapping.adf_a_texto(doc) == "@Malena revisá esto\ngracias\n- uno\n- dos\n[adjunto]"
