"""Regresión: el usuario autenticado debe quedar registrado como actor de
las mutaciones hechas por la API. Antes get_current_user asignaba el
ContextVar dentro de un threadpool (copia del contexto) y el valor se perdía
antes de llegar al endpoint: todas las filas de audit_log quedaban con
actor_id NULL. Los tests de tests/integration/test_audit.py no lo detectaban
porque setean el ContextVar a mano."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.auth.models import User
from app.casos.models import Caso


def test_crear_un_caso_por_la_api_registra_al_usuario_como_actor(
    client: TestClient, auth_headers: dict[str, str], db: Session
) -> None:
    user = db.query(User).filter(User.username == "test-user").one()

    response = client.post(
        "/casos",
        json={"empresa_responsable": "ACME", "nombre_proyecto": "Auditado", "tipo": "candidato"},
        headers=auth_headers,
    )
    assert response.status_code == 201

    caso = db.query(Caso).filter(Caso.nombre_proyecto == "Auditado").one()
    assert caso.created_by_id == user.id
    assert caso.updated_by_id == user.id

    log = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "Caso", AuditLog.entity_id == caso.id, AuditLog.action == "CREATE")
        .one()
    )
    assert log.actor_id == user.id


def test_el_actor_de_un_update_es_quien_lo_hace_y_no_quien_creo(
    client: TestClient, auth_headers: dict[str, str], db: Session
) -> None:
    user = db.query(User).filter(User.username == "test-user").one()
    caso = client.post(
        "/casos",
        json={"empresa_responsable": "ACME", "nombre_proyecto": "Editado", "tipo": "candidato"},
        headers=auth_headers,
    ).json()

    client.patch(f"/casos/{caso['id']}", json={"estado": "en_analisis"}, headers=auth_headers)

    db.expire_all()
    update = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == caso["id"], AuditLog.action == "UPDATE")
        .one()
    )
    assert update.actor_id == user.id
