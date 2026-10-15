"""Integración con Jira del lado del backend: eventos que genera la
plataforma, acciones en vivo (transiciones, asignación) y webhook. El envío
de eventos y el pull periódico son del worker (worker/tests)."""

import datetime as dt
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.casos.models import Caso, CasoEstado, JiraSyncEstado
from app.core.config import get_settings
from app.integraciones.jira.models import JiraOutbox, OperacionJira
from app.integraciones.jira.outbox import CANAL
from tests.integration.fake_jira import FakeJira, crear_caso, recargar, vincular

# --- eventos que genera la plataforma ---


def test_tipo_solicitud_desconocido_devuelve_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/casos", json={"nombre_proyecto": "X", "tipo_solicitud_id": "1"}, headers=auth_headers)

    assert response.status_code == 422


def test_alta_en_la_plataforma_genera_evento_y_avisa_al_worker(
    client: TestClient, auth_headers: dict[str, str], db: Session
) -> None:
    """El backend no llama a Jira: deja el evento en la outbox y emite un
    NOTIFY que despierta al worker (se entrega al confirmar la transacción)."""
    escucha = psycopg.connect(
        make_url(get_settings().database_url).set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True,
    )
    try:
        escucha.execute(f"LISTEN {CANAL}")
        caso = crear_caso(client, auth_headers, tipo_solicitud_id="544")

        avisos = list(escucha.notifies(timeout=2, stop_after=1))
    finally:
        escucha.close()

    assert [a.payload for a in avisos] == [caso["id"]]
    assert caso["jira_sync_estado"] == "pendiente"
    assert caso["tipo"] is None and caso["empresa_responsable"] is None
    [evento] = db.scalars(select(JiraOutbox).where(JiraOutbox.caso_id == uuid.UUID(caso["id"]))).all()
    assert evento.operacion == OperacionJira.CREAR_ISSUE
    assert recargar(db, caso["id"]).jira_tipo_solicitud_id == "544"


def test_ediciones_seguidas_dejan_un_solo_evento_de_actualizacion(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = crear_caso(client, auth_headers)
    vincular(db, jira, caso["id"])
    db.query(JiraOutbox).update({"procesado_at": dt.datetime.now(dt.UTC)})  # el worker ya creó el ticket
    db.commit()

    client.patch(f"/casos/{caso['id']}", json={"nombre_proyecto": "Intent Edge v2"}, headers=auth_headers)
    client.patch(f"/casos/{caso['id']}", json={"gdld": "11000"}, headers=auth_headers)

    pendientes = db.scalars(select(JiraOutbox).where(JiraOutbox.procesado_at.is_(None))).all()
    assert [op.operacion for op in pendientes] == [OperacionJira.ACTUALIZAR_ISSUE]


def test_editar_empresa_o_tipo_no_genera_eventos(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = crear_caso(client, auth_headers)
    vincular(db, jira, caso["id"])
    antes = db.query(JiraOutbox).count()

    client.patch(f"/casos/{caso['id']}", json={"empresa_responsable": "ACME", "tipo": "candidato"}, headers=auth_headers)

    assert db.query(JiraOutbox).count() == antes


def test_caso_anterior_a_la_integracion_no_va_a_jira(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = crear_caso(client, auth_headers)
    c = recargar(db, caso["id"])
    db.query(JiraOutbox).delete()
    c.jira_sync_estado = None  # como los casos que ya existían
    db.commit()

    client.post(f"/casos/{caso['id']}/comentarios", json={"cuerpo": "nota"}, headers=auth_headers)
    response = client.patch(f"/casos/{caso['id']}", json={"estado": "hecho"}, headers=auth_headers)

    assert response.status_code == 200 and response.json()["estado"] == "hecho"
    assert db.query(JiraOutbox).count() == 0


def test_reintentar_vuelve_a_encolar_los_eventos_fallidos(
    client: TestClient, auth_headers: dict[str, str], db: Session
) -> None:
    caso = crear_caso(client, auth_headers)
    evento = db.scalar(select(JiraOutbox).where(JiraOutbox.caso_id == uuid.UUID(caso["id"])))
    evento.descartada = True
    evento.ultimo_error = "400: campo inválido"
    c = recargar(db, caso["id"])
    c.jira_sync_estado = JiraSyncEstado.ERROR
    c.jira_sync_error = "No se pudo crear el ticket"
    db.commit()

    response = client.post(f"/casos/{caso['id']}/jira/reintentar", headers=auth_headers)

    assert response.status_code == 200
    assert (response.json()["jira_sync_estado"], response.json()["jira_sync_error"]) == ("pendiente", None)
    db.expire_all()
    assert db.get(JiraOutbox, evento.id).descartada is False


# --- acciones en vivo ---


def test_transiciones_del_workflow_de_jira(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = crear_caso(client, auth_headers)
    vincular(db, jira, caso["id"])

    response = client.get(f"/casos/{caso['id']}/transiciones", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == [
        {"id": "2", "nombre": "En curso", "destino": "En Progreso", "estado": "en_curso"},
        {"id": "4", "nombre": "Consultar al Cliente", "destino": "Esperando por el Cliente", "estado": "esperando_respuesta"},
    ]

    response = client.post(f"/casos/{caso['id']}/transiciones", json={"transition_id": "4"}, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["estado"] == "esperando_respuesta"
    assert response.json()["jira_status_nombre"] == "Esperando por el Cliente"

    response = client.post(f"/casos/{caso['id']}/transiciones", json={"transition_id": "3"}, headers=auth_headers)
    assert response.status_code == 400
    assert recargar(db, caso["id"]).estado == CasoEstado.ESPERANDO_RESPUESTA


def test_estado_de_caso_vinculado_no_se_cambia_por_patch(
    client: TestClient, auth_headers: dict[str, str], jira: FakeJira
) -> None:
    caso = crear_caso(client, auth_headers)

    response = client.patch(f"/casos/{caso['id']}", json={"estado": "hecho"}, headers=auth_headers)

    assert response.status_code == 409


def test_transiciones_sin_ticket_todavia(client: TestClient, auth_headers: dict[str, str], jira: FakeJira) -> None:
    caso = crear_caso(client, auth_headers)

    response = client.get(f"/casos/{caso['id']}/transiciones", headers=auth_headers)

    assert response.status_code == 409


def test_asignar_y_desasignar_desde_la_plataforma(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = crear_caso(client, auth_headers)
    vincular(db, jira, caso["id"])

    response = client.get(f"/casos/{caso['id']}/asignables", params={"query": "male"}, headers=auth_headers)
    assert response.status_code == 200
    assert [p["nombre"] for p in response.json()] == ["Malena Andrea Abugoch Santana"]

    response = client.put(f"/casos/{caso['id']}/asignado", json={"account_id": "712020:malena"}, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["jira_asignado_nombre"] == "Malena Andrea Abugoch Santana"
    assert response.json()["jira_asignado_avatar_url"].startswith("https://")
    key = recargar(db, caso["id"]).jira_issue_key
    assert jira.issues[key]["fields"]["assignee"]["accountId"] == "712020:malena"

    equipo = client.get("/casos/equipo-jira", headers=auth_headers).json()
    assert [p["account_id"] for p in equipo] == ["712020:malena"]

    response = client.put(f"/casos/{caso['id']}/asignado", json={"account_id": None}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["jira_asignado_nombre"] is None
    assert jira.issues[key]["fields"]["assignee"] is None


def test_asignacion_rechazada_por_jira(client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira) -> None:
    caso = crear_caso(client, auth_headers)
    vincular(db, jira, caso["id"])

    response = client.put(f"/casos/{caso['id']}/asignado", json={"account_id": "712020:otro"}, headers=auth_headers)
    assert response.status_code == 400

    response = client.put(f"/casos/{caso['id']}/asignado", json={"account_id": "x OR 1=1"}, headers=auth_headers)
    assert response.status_code == 422


def test_no_se_asigna_un_caso_sin_ticket(client: TestClient, auth_headers: dict[str, str], jira: FakeJira) -> None:
    caso = crear_caso(client, auth_headers)

    response = client.put(f"/casos/{caso['id']}/asignado", json={"account_id": "712020:malena"}, headers=auth_headers)

    assert response.status_code == 409


# --- webhook ---


def test_webhook_exige_secreto(client: TestClient, monkeypatch: pytest.MonkeyPatch, jira: FakeJira) -> None:
    assert client.post("/integraciones/jira/webhook", json={"issueKey": "MDA-1"}).status_code == 404  # sin secreto

    monkeypatch.setattr(get_settings(), "jira_webhook_secret", "s3cret-hook")

    assert client.post("/integraciones/jira/webhook", json={"issueKey": "MDA-1"}).status_code == 401
    otro = {"X-Aisec-Secret": "otro"}
    assert client.post("/integraciones/jira/webhook", json={"issueKey": "MDA-1"}, headers=otro).status_code == 401


def test_ya_no_existe_el_endpoint_de_sync(client: TestClient) -> None:
    """La sincronización periódica es del worker."""
    assert client.post("/integraciones/jira/sync").status_code == 404


def test_webhook_trae_el_ticket(client: TestClient, monkeypatch: pytest.MonkeyPatch, db: Session, jira: FakeJira) -> None:
    monkeypatch.setattr(get_settings(), "jira_webhook_secret", "s3cret-hook")
    jira.agregar_issue("MDA-5", "[IA-SEC] - POC Netskope AI", status="esperando")
    headers = {"X-Aisec-Secret": "s3cret-hook"}

    response = client.post("/integraciones/jira/webhook", json={"issue": {"key": "MDA-5"}}, headers=headers)

    assert response.status_code == 204
    caso = db.scalar(select(Caso).where(Caso.jira_issue_key == "MDA-5"))
    assert caso.estado == CasoEstado.ESPERANDO_RESPUESTA
    bad = client.post("/integraciones/jira/webhook", json={"issueKey": "MDA-5 OR 1=1"}, headers=headers)
    assert bad.status_code == 422
