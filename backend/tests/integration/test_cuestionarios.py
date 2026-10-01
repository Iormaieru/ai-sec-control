import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.core.email import EmailNoEnviado
from app.cuestionarios import service
from app.cuestionarios.models import CuestionarioInvitacion


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    enviados: list[dict] = []
    monkeypatch.setattr(service, "send_email", lambda **kwargs: enviados.append(kwargs))
    return enviados


def _setup_caso(client: TestClient, auth_headers: dict[str, str], *, email: str | None = "ana@proveedor.com") -> dict:
    caso = client.post(
        "/casos",
        json={"empresa_responsable": "Proveedor SA", "nombre_proyecto": "Chatbot", "tipo": "ingresado"},
        headers=auth_headers,
    ).json()
    contacto = client.post(
        f"/casos/{caso['id']}/contactos", json={"nombre": "Ana", "email": email}, headers=auth_headers
    ).json()
    preguntas = client.post(
        f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "TAC"}, headers=auth_headers
    ).json()
    return {"caso": caso, "contacto": contacto, "preguntas": preguntas}


def _enviar(client: TestClient, auth_headers: dict[str, str], setup: dict) -> dict:
    response = client.post(
        f"/casos/{setup['caso']['id']}/cuestionarios",
        json={"contacto_ids": [setup["contacto"]["id"]]},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


def _token(invitacion: dict) -> dict[str, str]:
    return {"X-Cuestionario-Token": invitacion["enlace"].rsplit("/", 1)[1]}


def test_enviar_cuestionario_manda_email_con_enlace(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None, outbox: list[dict]
) -> None:
    setup = _setup_caso(client, auth_headers)

    invitacion = _enviar(client, auth_headers, setup)

    assert invitacion["estado"] == "enviada"
    assert invitacion["email"] == "ana@proveedor.com"
    assert invitacion["enlace"].startswith("http://localhost:5173/cuestionario/")
    assert len(outbox) == 1
    assert outbox[0]["to"] == "ana@proveedor.com"
    assert invitacion["enlace"] in outbox[0]["text"]

    listado = client.get(f"/casos/{setup['caso']['id']}/cuestionarios", headers=auth_headers).json()
    assert [i["id"] for i in listado] == [invitacion["id"]]
    assert listado[0]["enlace"] is None  # el enlace no se puede volver a obtener


def test_token_se_guarda_hasheado(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None, outbox: list[dict]
) -> None:
    invitacion = _enviar(client, auth_headers, _setup_caso(client, auth_headers))
    token = _token(invitacion)["X-Cuestionario-Token"]

    guardada = db.get(CuestionarioInvitacion, uuid.UUID(invitacion["id"]))
    assert guardada.token_hash != token
    assert guardada.token_hash == service.hash_token(token)


def test_contacto_sin_email_devuelve_400(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None, outbox: list[dict]
) -> None:
    setup = _setup_caso(client, auth_headers, email=None)

    response = client.post(
        f"/casos/{setup['caso']['id']}/cuestionarios",
        json={"contacto_ids": [setup["contacto"]["id"]]},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert outbox == []


def test_contacto_de_otro_caso_devuelve_400(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None, outbox: list[dict]
) -> None:
    setup = _setup_caso(client, auth_headers)
    otro = _setup_caso(client, auth_headers)

    response = client.post(
        f"/casos/{setup['caso']['id']}/cuestionarios",
        json={"contacto_ids": [otro["contacto"]["id"]]},
        headers=auth_headers,
    )

    assert response.status_code == 400


def test_caso_sin_preguntas_devuelve_400(
    client: TestClient, auth_headers: dict[str, str], outbox: list[dict]
) -> None:
    caso = client.post(
        "/casos",
        json={"empresa_responsable": "Proveedor SA", "nombre_proyecto": "Vacío", "tipo": "ingresado"},
        headers=auth_headers,
    ).json()
    contacto = client.post(
        f"/casos/{caso['id']}/contactos", json={"nombre": "Ana", "email": "ana@x.com"}, headers=auth_headers
    ).json()

    response = client.post(
        f"/casos/{caso['id']}/cuestionarios", json={"contacto_ids": [contacto["id"]]}, headers=auth_headers
    )

    assert response.status_code == 400


def test_enviar_requiere_autenticacion(client: TestClient, auth_headers: dict[str, str], catalog_loaded: None) -> None:
    setup = _setup_caso(client, auth_headers)

    response = client.post(
        f"/casos/{setup['caso']['id']}/cuestionarios", json={"contacto_ids": [setup["contacto"]["id"]]}
    )

    assert response.status_code == 401


def test_falla_del_email_devuelve_502_y_no_deja_invitacion(
    client: TestClient,
    auth_headers: dict[str, str],
    db: Session,
    catalog_loaded: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup_caso(client, auth_headers)

    def _falla(**_kwargs: object) -> None:
        raise EmailNoEnviado("No se pudo enviar el email a ana@proveedor.com")

    monkeypatch.setattr(service, "send_email", _falla)

    response = client.post(
        f"/casos/{setup['caso']['id']}/cuestionarios",
        json={"contacto_ids": [setup["contacto"]["id"]]},
        headers=auth_headers,
    )

    assert response.status_code == 502
    assert db.query(CuestionarioInvitacion).count() == 0


def test_formulario_muestra_solo_preguntas_pendientes_y_marca_abierta(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None, outbox: list[dict]
) -> None:
    setup = _setup_caso(client, auth_headers)
    caso_id = setup["caso"]["id"]
    respondida = setup["preguntas"][0]["pregunta_id"]
    client.put(f"/casos/{caso_id}/preguntas/{respondida}/respuesta", json={"respuesta": "SI"}, headers=auth_headers)
    invitacion = _enviar(client, auth_headers, setup)

    response = client.get("/cuestionario", headers=_token(invitacion))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["nombre_proyecto"] == "Chatbot"
    assert body["contacto_nombre"] == "Ana"
    ids = {p["pregunta_id"] for p in body["preguntas"]}
    assert len(ids) == 6  # 7 de TAC menos la que ya respondió el analista
    assert respondida not in ids
    estado = client.get(f"/casos/{caso_id}/cuestionarios", headers=auth_headers).json()[0]
    assert estado["estado"] == "abierta"
    assert estado["abierta_at"] is not None


def test_token_invalido_devuelve_404(client: TestClient) -> None:
    response = client.get("/cuestionario", headers={"X-Cuestionario-Token": "no-existe"})

    assert response.status_code == 404


def test_borrador_se_guarda_y_no_toca_el_caso(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None, outbox: list[dict]
) -> None:
    setup = _setup_caso(client, auth_headers)
    invitacion = _enviar(client, auth_headers, setup)
    pregunta_id = setup["preguntas"][0]["pregunta_id"]

    response = client.put(
        "/cuestionario/borrador",
        json={"respuestas": [{"pregunta_id": pregunta_id, "respuesta": "NO", "comentario": "Falta revisar"}]},
        headers=_token(invitacion),
    )

    assert response.status_code == 204, response.text
    formulario = client.get("/cuestionario", headers=_token(invitacion)).json()
    guardada = next(p for p in formulario["preguntas"] if p["pregunta_id"] == pregunta_id)
    assert guardada["respuesta"] == "NO"
    assert guardada["comentario"] == "Falta revisar"
    preguntas_caso = client.get(f"/casos/{setup['caso']['id']}/preguntas", headers=auth_headers).json()
    assert all(p["respuesta"] == "PENDIENTE" for p in preguntas_caso)


def test_enviar_aplica_respuestas_al_caso_sin_pisar_las_del_analista(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None, outbox: list[dict]
) -> None:
    setup = _setup_caso(client, auth_headers)
    caso_id = setup["caso"]["id"]
    p1, p2, p3 = (p["pregunta_id"] for p in setup["preguntas"][:3])
    client.put(
        f"/casos/{caso_id}/preguntas/{p1}/respuesta",
        json={"respuesta": "PENDIENTE", "observaciones": "Nota del analista"},
        headers=auth_headers,
    )
    invitacion = _enviar(client, auth_headers, setup)
    # El analista responde p3 mientras el contacto completa el formulario.
    client.put(f"/casos/{caso_id}/preguntas/{p3}/respuesta", json={"respuesta": "NO"}, headers=auth_headers)

    response = client.post(
        "/cuestionario/enviar",
        json={
            "respuestas": [
                {"pregunta_id": p1, "respuesta": "SI", "comentario": "Hay doc de arquitectura"},
                {"pregunta_id": p2, "respuesta": "NA_ARQ"},
                {"pregunta_id": p3, "respuesta": "SI"},
            ]
        },
        headers=_token(invitacion),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"aplicadas": 2, "omitidas": 1}
    preguntas = {p["pregunta_id"]: p for p in client.get(f"/casos/{caso_id}/preguntas", headers=auth_headers).json()}
    assert preguntas[p1]["respuesta"] == "SI"
    assert preguntas[p1]["observaciones"].startswith("Nota del analista\n\n[Ana, cuestionario ")
    assert preguntas[p1]["observaciones"].endswith("] Hay doc de arquitectura")
    assert preguntas[p2]["respuesta"] == "NA_ARQ"
    assert preguntas[p3]["respuesta"] == "NO"  # gana el analista
    estado = client.get(f"/casos/{caso_id}/cuestionarios", headers=auth_headers).json()[0]
    assert estado["estado"] == "respondida"


def test_enlace_queda_cerrado_despues_de_enviar(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None, outbox: list[dict]
) -> None:
    setup = _setup_caso(client, auth_headers)
    invitacion = _enviar(client, auth_headers, setup)
    client.post("/cuestionario/enviar", json={"respuestas": []}, headers=_token(invitacion))

    assert client.get("/cuestionario", headers=_token(invitacion)).status_code == 410
    assert client.post("/cuestionario/enviar", json={"respuestas": []}, headers=_token(invitacion)).status_code == 410


def test_reenvio_anula_el_enlace_anterior(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None, outbox: list[dict]
) -> None:
    setup = _setup_caso(client, auth_headers)
    primera = _enviar(client, auth_headers, setup)
    segunda = _enviar(client, auth_headers, setup)

    assert client.get("/cuestionario", headers=_token(primera)).status_code == 410
    assert client.get("/cuestionario", headers=_token(segunda)).status_code == 200
    estados = [i["estado"] for i in client.get(f"/casos/{setup['caso']['id']}/cuestionarios", headers=auth_headers).json()]
    assert sorted(estados) == ["abierta", "anulada"]


def test_enlace_vencido_devuelve_410(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None, outbox: list[dict]
) -> None:
    invitacion = _enviar(client, auth_headers, _setup_caso(client, auth_headers))
    guardada = db.get(CuestionarioInvitacion, uuid.UUID(invitacion["id"]))
    guardada.expira_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    response = client.get("/cuestionario", headers=_token(invitacion))

    assert response.status_code == 410
    assert "venció" in response.json()["detail"]


def test_pregunta_fuera_de_alcance_devuelve_400(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None, outbox: list[dict]
) -> None:
    setup = _setup_caso(client, auth_headers)
    otro = _setup_caso(client, auth_headers)
    client.post(f"/casos/{otro['caso']['id']}/preguntas", json={"dominio_codigo": "CYB"}, headers=auth_headers)
    ajena = client.get(f"/casos/{otro['caso']['id']}/preguntas", headers=auth_headers).json()
    ajena_id = next(p["pregunta_id"] for p in ajena if p["dominio_codigo"] == "CYB")
    invitacion = _enviar(client, auth_headers, setup)

    response = client.post(
        "/cuestionario/enviar",
        json={"respuestas": [{"pregunta_id": ajena_id, "respuesta": "SI"}]},
        headers=_token(invitacion),
    )

    assert response.status_code == 400


def test_respuesta_del_contacto_queda_auditada_a_su_nombre(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None, outbox: list[dict]
) -> None:
    setup = _setup_caso(client, auth_headers)
    invitacion = _enviar(client, auth_headers, setup)
    pregunta = setup["preguntas"][0]

    client.post(
        "/cuestionario/enviar",
        json={"respuestas": [{"pregunta_id": pregunta["pregunta_id"], "respuesta": "SI"}]},
        headers=_token(invitacion),
    )

    logs = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "CasoRespuesta", AuditLog.action == "UPDATE")
        .all()
    )
    assert [str(log.actor_id) for log in logs] == [setup["contacto"]["id"]]
