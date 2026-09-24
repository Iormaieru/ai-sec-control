import json
import logging

import pytest

from app.core.config import Settings
from app.core.logging import JsonFormatter, TextFormatter, _parse_cloud_trace


def _record(msg="hola", level=logging.INFO, exc_info=None, **extra) -> logging.LogRecord:
    record = logging.LogRecord("app.test", level, __file__, 10, msg, (), exc_info)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emite_una_linea_json_con_los_campos_de_cloud_logging() -> None:
    line = JsonFormatter().format(_record("algo pasó", logging.WARNING))

    data = json.loads(line)
    assert "\n" not in line
    assert data["severity"] == "WARNING"
    assert data["message"] == "algo pasó"
    assert data["logger"] == "app.test"
    assert data["timestamp"].endswith("+00:00")


def test_json_formatter_incluye_los_extra_y_omite_los_nulos() -> None:
    data = json.loads(JsonFormatter().format(_record(caso_id="abc", duration_ms=12.5, user_id=None)))

    assert data["caso_id"] == "abc"
    assert data["duration_ms"] == 12.5
    assert "user_id" not in data


def test_json_formatter_serializa_la_excepcion_en_un_solo_campo() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        line = JsonFormatter().format(_record("falló", logging.ERROR, exc_info=sys.exc_info()))

    data = json.loads(line)
    assert data["severity"] == "ERROR"
    assert "ValueError: boom" in data["exception"]
    assert "\n" not in line  # una excepción multi-línea no debe partir el log en varias entradas


def test_trace_de_cloud_logging_solo_si_hay_proyecto_configurado() -> None:
    record = _record(trace_id="abc123", span_id="42")

    con_proyecto = json.loads(JsonFormatter("mi-proyecto").format(record))
    sin_proyecto = json.loads(JsonFormatter().format(record))

    assert con_proyecto["logging.googleapis.com/trace"] == "projects/mi-proyecto/traces/abc123"
    assert con_proyecto["logging.googleapis.com/spanId"] == "42"
    assert "logging.googleapis.com/trace" not in sin_proyecto
    assert sin_proyecto["trace_id"] == "abc123"  # Dynatrace correlaciona por trace_id


def test_text_formatter_es_legible_para_desarrollo() -> None:
    line = TextFormatter().format(_record("hola", request_id="12345678-aaaa", http_status=200))

    assert "INFO" in line and "hola" in line and "[12345678]" in line and '"http_status": 200' in line


@pytest.mark.parametrize(
    "header,esperado",
    [
        ("105445aa7843bc8bf206b12000100000/1;o=1", ("105445aa7843bc8bf206b12000100000", "1")),
        ("abc/99", ("abc", "99")),
        ("abc", ("abc", None)),
        (None, (None, None)),
        ("", (None, None)),
    ],
)
def test_parse_de_x_cloud_trace_context(header, esperado) -> None:
    assert _parse_cloud_trace(header) == esperado


def test_formato_por_defecto_segun_el_entorno() -> None:
    assert Settings(_env_file=None, environment="development").effective_log_format == "text"
    prod = Settings(_env_file=None, environment="production", jwt_secret="x" * 40)
    assert prod.effective_log_format == "json"
    forzado = Settings(_env_file=None, environment="development", log_format="json")
    assert forzado.effective_log_format == "json"


def test_color_message_de_uvicorn_no_ensucia_el_json() -> None:
    data = json.loads(JsonFormatter().format(_record("Started", color_message="\x1b[36mStarted\x1b[0m")))

    assert "color_message" not in data
    assert "\x1b" not in json.dumps(data)
