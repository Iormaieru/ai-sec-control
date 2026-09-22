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


def test_quitar_dominio_completo(client: TestClient, auth_headers: dict[str, str], catalog_loaded: None) -> None:
    caso = _create_caso(client, auth_headers)
    client.post(f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "TAC"}, headers=auth_headers)
    client.post(f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "DDG"}, headers=auth_headers)

    response = client.delete(
        f"/casos/{caso['id']}/preguntas", params={"dominio_codigo": "TAC"}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    restantes = response.json()
    assert len(restantes) == 10  # sólo quedan las 10 de DDG
    assert all(p["dominio_codigo"] == "DDG" for p in restantes)


def test_quitar_dominio_tambien_borra_las_respuestas_cargadas(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    dominio = db.query(Dominio).filter(Dominio.codigo == "TAC").one()
    pregunta = db.query(Pregunta).filter(Pregunta.dominio_id == dominio.id, Pregunta.numero == 1).one()
    client.post(f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "TAC"}, headers=auth_headers)
    client.put(
        f"/casos/{caso['id']}/preguntas/{pregunta.id}/respuesta",
        json={"respuesta": "SI"},
        headers=auth_headers,
    )

    client.delete(f"/casos/{caso['id']}/preguntas", params={"dominio_codigo": "TAC"}, headers=auth_headers)

    # re-agregar el dominio debe volver a Pendiente, no arrastrar la respuesta anterior
    response = client.post(f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "TAC"}, headers=auth_headers)
    body = response.json()
    assert all(p["respuesta"] == "PENDIENTE" for p in body)


def test_quitar_dominio_desconocido_devuelve_400(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)

    response = client.delete(
        f"/casos/{caso['id']}/preguntas", params={"dominio_codigo": "NOPE"}, headers=auth_headers
    )

    assert response.status_code == 400


def test_seleccionar_preguntas_individuales_por_id(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    """Selección manual puntual: el humano suma preguntas de un dominio sin
    agregar el dominio completo (para lo que la IA no haya recomendado)."""
    caso = _create_caso(client, auth_headers)
    dominio = db.query(Dominio).filter(Dominio.codigo == "CYB").one()
    preguntas = db.query(Pregunta).filter(Pregunta.dominio_id == dominio.id).limit(2).all()

    response = client.post(
        f"/casos/{caso['id']}/preguntas",
        json={"pregunta_ids": [str(preguntas[0].id)]},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert len(response.json()) == 1

    # sumar una segunda, individual, sin tocar el resto del dominio
    response2 = client.post(
        f"/casos/{caso['id']}/preguntas",
        json={"pregunta_ids": [str(preguntas[1].id)]},
        headers=auth_headers,
    )
    assert len(response2.json()) == 2


def test_quitar_pregunta_individual(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    client.post(f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "TAC"}, headers=auth_headers)
    preguntas = client.get(f"/casos/{caso['id']}/preguntas", headers=auth_headers).json()
    a_quitar = preguntas[0]

    response = client.delete(
        f"/casos/{caso['id']}/preguntas/{a_quitar['pregunta_id']}", headers=auth_headers
    )
    assert response.status_code == 204

    restantes = client.get(f"/casos/{caso['id']}/preguntas", headers=auth_headers).json()
    assert len(restantes) == len(preguntas) - 1
    assert all(p["pregunta_id"] != a_quitar["pregunta_id"] for p in restantes)


def test_quitar_pregunta_fuera_de_alcance_devuelve_404(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    pregunta = db.query(Pregunta).first()

    response = client.delete(f"/casos/{caso['id']}/preguntas/{pregunta.id}", headers=auth_headers)

    assert response.status_code == 404
