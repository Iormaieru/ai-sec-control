from fastapi.testclient import TestClient


def _create_caso(client: TestClient, auth_headers: dict[str, str], **overrides) -> dict:
    payload = {
        "gdld": "GDLD-123",
        "empresa_responsable": "Proveedor SA",
        "nombre_proyecto": "Chatbot de atención",
        "tipo": "candidato",
        **overrides,
    }
    response = client.post("/casos", json=payload, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_get_caso(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = _create_caso(client, auth_headers)

    assert created["estado"] == "abierto"
    assert created["gdld"] == "123"  # se guarda sólo el número

    response = client.get(f"/casos/{created['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["nombre_proyecto"] == "Chatbot de atención"


def test_create_caso_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/casos",
        json={
            "empresa_responsable": "X",
            "nombre_proyecto": "Y",
            "tipo": "candidato",
        },
    )
    assert response.status_code == 401


def test_list_casos_filters_by_estado_and_tipo(client: TestClient, auth_headers: dict[str, str]) -> None:
    _create_caso(client, auth_headers, tipo="candidato", empresa_responsable="Empresa A")
    _create_caso(client, auth_headers, tipo="ingresado", empresa_responsable="Empresa B")

    response = client.get("/casos", params={"tipo": "ingresado"}, headers=auth_headers)

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["empresa_responsable"] == "Empresa B"


def test_update_caso_valid_transition(client: TestClient, auth_headers: dict[str, str]) -> None:
    caso = _create_caso(client, auth_headers)

    response = client.patch(f"/casos/{caso['id']}", json={"estado": "en_analisis"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["estado"] == "en_analisis"


def test_update_caso_invalid_transition_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    caso = _create_caso(client, auth_headers)  # estado inicial: abierto

    # abierto -> cerrado_aprobado no está permitido (debe pasar por en_analisis)
    response = client.patch(
        f"/casos/{caso['id']}", json={"estado": "cerrado_aprobado"}, headers=auth_headers
    )

    assert response.status_code == 400


def test_terminal_state_has_no_further_transitions(client: TestClient, auth_headers: dict[str, str]) -> None:
    caso = _create_caso(client, auth_headers)
    client.patch(f"/casos/{caso['id']}", json={"estado": "en_analisis"}, headers=auth_headers)
    client.patch(f"/casos/{caso['id']}", json={"estado": "rechazado"}, headers=auth_headers)

    response = client.patch(f"/casos/{caso['id']}", json={"estado": "en_analisis"}, headers=auth_headers)

    assert response.status_code == 400


def test_add_and_remove_contacto(client: TestClient, auth_headers: dict[str, str]) -> None:
    caso = _create_caso(client, auth_headers)

    response = client.post(
        f"/casos/{caso['id']}/contactos",
        json={"nombre": "Juan Pérez", "email": "juan@proveedor.com", "rol": "PM"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    contacto = response.json()

    get_response = client.get(f"/casos/{caso['id']}", headers=auth_headers)
    assert len(get_response.json()["contactos"]) == 1

    delete_response = client.delete(
        f"/casos/{caso['id']}/contactos/{contacto['id']}", headers=auth_headers
    )
    assert delete_response.status_code == 204

    get_response_2 = client.get(f"/casos/{caso['id']}", headers=auth_headers)
    assert len(get_response_2.json()["contactos"]) == 0


def test_get_unknown_caso_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/casos/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert response.status_code == 404


def test_unauthenticated_request_for_unknown_caso_returns_401_not_404(client: TestClient) -> None:
    """Regresión: get_caso_from_path solía resolverse antes que la
    autenticación, así que una request sin token contra un caso
    inexistente devolvía 404 (filtrando si el caso existe) en vez de 401.
    Ver app/casos/deps.py."""
    response = client.get("/casos/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401


def test_gdld_se_normaliza_a_solo_el_numero(client: TestClient, auth_headers: dict[str, str]) -> None:
    for valor in ("12190", " GDLD 12190 ", "gdld-12190", "GDLD N° 12190"):
        assert _create_caso(client, auth_headers, gdld=valor)["gdld"] == "12190", valor
    assert _create_caso(client, auth_headers, gdld="")["gdld"] is None


def test_gdld_no_numerico_devuelve_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/casos",
        json={"gdld": "12A90", "empresa_responsable": "X", "nombre_proyecto": "Y", "tipo": "candidato"},
        headers=auth_headers,
    )

    assert response.status_code == 422
