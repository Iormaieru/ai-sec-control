import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.catalog.models import Dominio, Pregunta


def _create_caso(client: TestClient, auth_headers: dict[str, str]) -> dict:
    response = client.post(
        "/casos",
        json={"empresa_responsable": "Proveedor SA", "nombre_proyecto": "Scoring test", "tipo": "ingresado"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_score_de_caso_sin_preguntas_es_cero_en_todos_los_dominios(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)

    response = client.get(f"/casos/{caso['id']}/score", headers=auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["dominios"]) == 8
    assert all(d["compliance_pct"] == 0 for d in body["dominios"])
    assert all(d["semaforo"] == "critico" for d in body["dominios"])
    assert body["global_score"]["compliance_pct"] == 0
    assert body["global_score"]["semaforo"] == "critico"


def test_score_reproduce_fila_real_del_excel_para_un_dominio(
    client: TestClient, auth_headers: dict[str, str], db: Session, catalog_loaded: None
) -> None:
    """Replica las 7 respuestas reales de la hoja 'Transparency & Accessibility'
    (mismas usadas en tests/unit/test_scoring_aggregation.py) end-to-end vía la
    API, y compara contra la fila ya calculada por el propio Excel en
    ⚙️ Cálculos (75% cumplimiento, 59.375% riesgo residual)."""
    caso = _create_caso(client, auth_headers)
    dominio = db.query(Dominio).filter(Dominio.codigo == "TAC").one()
    preguntas = {
        p.numero: p
        for p in db.query(Pregunta).filter(Pregunta.dominio_id == dominio.id).all()
    }

    client.post(f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "TAC"}, headers=auth_headers)

    respuestas_por_numero = {
        1: "SI",
        2: "NO",
        3: "PENDIENTE",
        4: "PENDIENTE",
        5: "SI",
        6: "PENDIENTE",
        7: "PENDIENTE",
    }
    for numero, respuesta in respuestas_por_numero.items():
        r = client.put(
            f"/casos/{caso['id']}/preguntas/{preguntas[numero].id}/respuesta",
            json={"respuesta": respuesta},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text

    response = client.get(f"/casos/{caso['id']}/score", headers=auth_headers)
    body = response.json()
    tac = next(d for d in body["dominios"] if d["dominio_codigo"] == "TAC")

    assert tac["total_preguntas"] == 7
    assert tac["respondidas"] == 3
    assert tac["pendientes"] == 4
    assert tac["cumple"] == 2
    assert tac["brechas_criticas"] == 0
    assert tac["compliance_pct"] == pytest.approx(0.75, abs=1e-9)
    assert tac["residual_pct"] == pytest.approx(0.59375, abs=1e-9)
    assert tac["semaforo"] == "moderado"

    # los otros 7 dominios no fueron tocados -> 0%, arrastran el global hacia abajo
    otros = [d for d in body["dominios"] if d["dominio_codigo"] != "TAC"]
    assert all(d["compliance_pct"] == 0 for d in otros)
    assert body["global_score"]["compliance_pct"] == pytest.approx(0.75 * 0.06, abs=1e-9)


@pytest.mark.parametrize("todas_correctas,expected_semaforo", [(True, "solido"), (False, "critico")])
def test_score_semaforo_global_en_los_extremos(
    client: TestClient,
    auth_headers: dict[str, str],
    db: Session,
    catalog_loaded: None,
    todas_correctas: bool,
    expected_semaforo: str,
) -> None:
    """Responder correctamente las 138 preguntas -> 100% exacto -> Sólido.
    Responder todas incorrectamente -> igual cae en Crítico (<40%), aunque
    no sea exactamente 0%, porque Alto/Estándar dan 25% de crédito parcial
    incluso incorrectas (sólo Crítico es zero-tolerance). Los umbrales
    intermedios (60%/40%) ya están cubiertos, sin depender de la API, por
    test_semaforo_thresholds en tests/unit/test_scoring_aggregation.py."""
    caso = _create_caso(client, auth_headers)
    for dominio in db.query(Dominio).all():
        client.post(
            f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": dominio.codigo}, headers=auth_headers
        )

    for pregunta in db.query(Pregunta).all():
        correcta = "SI" if pregunta.polaridad.value == "positiva" else "NO"
        incorrecta = "NO" if pregunta.polaridad.value == "positiva" else "SI"
        r = client.put(
            f"/casos/{caso['id']}/preguntas/{pregunta.id}/respuesta",
            json={"respuesta": correcta if todas_correctas else incorrecta},
            headers=auth_headers,
        )
        assert r.status_code == 200

    response = client.get(f"/casos/{caso['id']}/score", headers=auth_headers)
    body = response.json()

    if todas_correctas:
        assert body["global_score"]["compliance_pct"] == pytest.approx(1.0, abs=1e-9)
    assert body["global_score"]["semaforo"] == expected_semaforo
