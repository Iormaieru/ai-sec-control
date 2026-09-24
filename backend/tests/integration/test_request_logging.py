"""Los logs son lo que consume Dynatrace: se verifica la salida real por
stdout (líneas JSON) y, sobre todo, lo que NO debe aparecer en ella."""

import json
import logging
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.main import app


@pytest.fixture(autouse=True)
def _json_logging_to_captured_stdout(capsys: pytest.CaptureFixture[str]) -> Generator[None, None, None]:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    configure_logging(Settings(_env_file=None, log_format="json", log_level="INFO"))
    yield
    root.handlers[:], root.level = saved_handlers, saved_level


def _lines(capsys: pytest.CaptureFixture[str]) -> list[dict]:
    out = capsys.readouterr().out
    return [json.loads(line) for line in out.splitlines() if line.startswith("{")]


def test_cada_request_deja_una_linea_de_acceso_con_metodo_ruta_status_y_duracion(
    client: TestClient, auth_headers: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    client.get("/catalogo/dominios", headers=auth_headers)

    acceso = [entry for entry in _lines(capsys) if entry["message"] == "request"]
    assert len(acceso) == 1
    entry = acceso[0]
    assert entry["severity"] == "INFO"
    assert entry["http_method"] == "GET"
    assert entry["http_path"] == "/catalogo/dominios"
    assert entry["http_route"] == "/catalogo/dominios"
    assert entry["http_status"] == 200
    assert entry["duration_ms"] >= 0
    assert entry["request_id"]


def test_el_log_de_acceso_lleva_el_usuario_autenticado(
    client: TestClient, auth_headers: dict[str, str], capsys: pytest.CaptureFixture[str], db
) -> None:
    from app.auth.models import User

    capsys.readouterr()
    client.get("/catalogo/dominios", headers=auth_headers)

    user = db.query(User).filter(User.username == "test-user").one()
    entry = next(e for e in _lines(capsys) if e["message"] == "request")
    assert entry["user_id"] == str(user.id)


def test_x_request_id_se_devuelve_y_se_respeta_el_entrante(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    generado = client.get("/auth/me")
    respetado = client.get("/auth/me", headers={"X-Request-ID": "req-de-prueba-1"})

    assert generado.headers["x-request-id"]
    assert respetado.headers["x-request-id"] == "req-de-prueba-1"
    assert any(e.get("request_id") == "req-de-prueba-1" for e in _lines(capsys))


def test_la_traza_de_cloud_run_llega_al_log(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()

    client.get("/auth/me", headers={"X-Cloud-Trace-Context": "105445aa7843bc8bf206b12000100000/77;o=1"})

    entry = next(e for e in _lines(capsys) if e["message"] == "request")
    assert entry["trace_id"] == "105445aa7843bc8bf206b12000100000"
    assert entry["span_id"] == "77"
    assert entry["http_status"] == 401


def test_health_no_inunda_los_logs(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()

    client.get("/health")

    assert [e for e in _lines(capsys) if e.get("http_path") == "/health"] == []


def test_no_se_loguean_query_string_ni_token(
    client: TestClient, auth_headers: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    token = auth_headers["Authorization"].split()[1]

    client.get("/casos", params={"empresa_responsable": "EMPRESA-SECRETA"}, headers=auth_headers)

    out = capsys.readouterr().out
    assert "EMPRESA-SECRETA" not in out
    assert token not in out


def test_login_fallido_se_loguea_con_el_usuario_pero_nunca_con_la_contrasena(
    client: TestClient, auth_headers: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    client.post("/auth/login", data={"username": "test-user", "password": "hunter2-clave-erronea"})

    out = capsys.readouterr().out
    fallido = next(
        json.loads(line) for line in out.splitlines() if line.startswith("{") and "login_failed" in line
    )
    assert fallido["severity"] == "WARNING"
    assert fallido["username"] == "test-user"
    assert "hunter2-clave-erronea" not in out


def test_login_correcto_se_loguea(
    client: TestClient, auth_headers: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    client.post("/auth/login", data={"username": "test-user", "password": "test-user-pass"})

    ok = next(e for e in _lines(capsys) if e["message"] == "login_ok")
    assert ok["username"] == "test-user"


def test_una_excepcion_no_manejada_se_loguea_como_error_con_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    boom_app = FastAPI()
    boom_app.add_middleware(RequestLoggingMiddleware)

    @boom_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("fallo inesperado")

    capsys.readouterr()
    response = TestClient(boom_app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    entry = next(e for e in _lines(capsys) if e["message"] == "request_failed")
    assert entry["severity"] == "ERROR"
    assert entry["http_status"] == 500
    assert "RuntimeError: fallo inesperado" in entry["exception"]
