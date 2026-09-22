from fastapi.testclient import TestClient


def test_list_dominios(client: TestClient, auth_headers: dict[str, str], catalog_loaded: None) -> None:
    response = client.get("/catalogo/dominios", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 8
    assert {d["codigo"] for d in body} == {"DDG", "TAC", "PDP", "CYB", "SAF", "BFD", "EHR", "AHO"}


def test_list_preguntas_filtrado_por_dominio(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None
) -> None:
    response = client.get("/catalogo/preguntas", params={"dominio": "TAC"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 7
    assert [p["numero"] for p in body] == list(range(1, 8))


def test_list_preguntas_sin_filtro_devuelve_las_138(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None
) -> None:
    response = client.get("/catalogo/preguntas", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()) == 138


def test_catalogo_requiere_auth(client: TestClient, catalog_loaded: None) -> None:
    response = client.get("/catalogo/dominios")
    assert response.status_code == 401
