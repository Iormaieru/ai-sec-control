from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.catalog.models import Dominio, Pregunta


def _create_caso(client: TestClient, auth_headers: dict[str, str]) -> dict:
    response = client.post(
        "/casos",
        json={
            "empresa_responsable": "Proveedor SA",
            "nombre_proyecto": "Motor de recomendaciones",
            "tipo": "ingresado",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_seleccionar_preguntas_por_ids(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    dominio = db.query(Dominio).filter(Dominio.codigo == "CYB").one()
    preguntas = db.query(Pregunta).filter(Pregunta.dominio_id == dominio.id).limit(3).all()

    response = client.post(
        f"/casos/{caso['id']}/preguntas",
        json={"pregunta_ids": [str(p.id) for p in preguntas]},
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body) == 3
    assert all(item["respuesta"] == "PENDIENTE" for item in body)
    assert all(item["estado"] == "pendiente" for item in body)


def test_seleccionar_preguntas_por_dominio_completo(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)

    response = client.post(
        f"/casos/{caso['id']}/preguntas",
        json={"dominio_codigo": "TAC"},
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    assert len(response.json()) == 7  # Transparency & Accessibility tiene 7 preguntas


def test_seleccionar_preguntas_es_idempotente(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    client.post(f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "TAC"}, headers=auth_headers)

    response = client.post(
        f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "TAC"}, headers=auth_headers
    )

    assert len(response.json()) == 7  # no duplica


def test_dominio_desconocido_devuelve_400(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)

    response = client.post(
        f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "NOPE"}, headers=auth_headers
    )

    assert response.status_code == 400


def test_actualizar_respuesta_refleja_calculo_del_motor_de_scoring(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    # Pregunta Crítico (mult=3), polaridad positiva -> DDG-01 es Crítico, polaridad +1
    dominio = db.query(Dominio).filter(Dominio.codigo == "DDG").one()
    pregunta = db.query(Pregunta).filter(Pregunta.dominio_id == dominio.id, Pregunta.numero == 1).one()
    assert pregunta.tier.value == "critico"
    assert pregunta.polaridad.value == "positiva"

    client.post(
        f"/casos/{caso['id']}/preguntas", json={"pregunta_ids": [str(pregunta.id)]}, headers=auth_headers
    )

    # Respuesta incorrecta (NO cuando polaridad exige SI) en pregunta Crítica -> 0 pts, zero tolerance
    response = client.put(
        f"/casos/{caso['id']}/preguntas/{pregunta.id}/respuesta",
        json={"respuesta": "NO"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["estado"] == "brecha"
    assert body["pts_obtenidos"] == 0
    assert body["riesgo_residual"] == 3


def test_actualizar_respuesta_con_mitigacion_reduce_riesgo_residual(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    dominio = db.query(Dominio).filter(Dominio.codigo == "DDG").one()
    pregunta = db.query(Pregunta).filter(Pregunta.dominio_id == dominio.id, Pregunta.numero == 1).one()
    client.post(
        f"/casos/{caso['id']}/preguntas", json={"pregunta_ids": [str(pregunta.id)]}, headers=auth_headers
    )

    response = client.put(
        f"/casos/{caso['id']}/preguntas/{pregunta.id}/respuesta",
        json={
            "respuesta": "NO",
            "factor_mitigacion_pct": 50,
            "control_compensatorio": "WAF + rate limiting",
            "owner_responsable": "Equipo Plataforma",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["riesgo_residual"] == 1.5  # 3 * (1 - 0.5)
    assert body["control_compensatorio"] == "WAF + rate limiting"
    assert body["owner_responsable"] == "Equipo Plataforma"


def test_respuesta_para_pregunta_fuera_de_alcance_devuelve_404(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    dominio = db.query(Dominio).filter(Dominio.codigo == "DDG").one()
    pregunta = db.query(Pregunta).filter(Pregunta.dominio_id == dominio.id).first()

    response = client.put(
        f"/casos/{caso['id']}/preguntas/{pregunta.id}/respuesta",
        json={"respuesta": "SI"},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_get_preguntas_ordena_por_dominio_y_numero(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    client.post(f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "TAC"}, headers=auth_headers)

    response = client.get(f"/casos/{caso['id']}/preguntas", headers=auth_headers)

    body = response.json()
    assert [item["numero"] for item in body] == list(range(1, 8))
