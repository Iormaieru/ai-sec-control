import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.documents.parsing import DOCX_CONTENT_TYPE


def _docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _use_mock_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.llm.providers.mock_provider import MockProvider

    monkeypatch.setattr("app.documents.service.get_llm_provider", lambda: MockProvider())


def _create_caso(client: TestClient, auth_headers: dict[str, str]) -> dict:
    response = client.post(
        "/casos",
        json={"empresa_responsable": "ACME", "nombre_proyecto": "Análisis IA", "tipo": "candidato"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_analizar_documento_recomienda_preguntas_criticas_con_instrucciones(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    contenido = _docx_bytes("Sistema de scoring crediticio basado en un modelo de ML.")

    response = client.post(
        f"/casos/{caso['id']}/documentos",
        files={"file": ("arquitectura.docx", contenido, DOCX_CONTENT_TYPE)},
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["clasificacion"]
    assert len(body["preguntas_recomendadas"]) > 0
    assert all(p["tier"] == "critico" for p in body["preguntas_recomendadas"])
    assert all(p["instrucciones_respuesta_es"] for p in body["preguntas_recomendadas"])
    assert all(p["instrucciones_respuesta_en"] for p in body["preguntas_recomendadas"])


def test_preguntas_recomendadas_aparecen_en_la_grilla_del_caso(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)
    contenido = _docx_bytes("Herramienta de terceros que usa un LLM para clasificar tickets.")

    analisis = client.post(
        f"/casos/{caso['id']}/documentos",
        files={"file": ("doc.docx", contenido, DOCX_CONTENT_TYPE)},
        headers=auth_headers,
    ).json()

    grilla = client.get(f"/casos/{caso['id']}/preguntas", headers=auth_headers).json()

    ids_recomendadas = {p["pregunta_id"] for p in analisis["preguntas_recomendadas"]}
    ids_en_grilla = {p["pregunta_id"] for p in grilla}
    assert ids_recomendadas.issubset(ids_en_grilla)

    alguna = next(p for p in grilla if p["pregunta_id"] in ids_recomendadas)
    assert alguna["instrucciones_respuesta_es"]


def test_analizar_documento_reutiliza_pregunta_ya_en_alcance(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None
) -> None:
    """Si una pregunta recomendada ya estaba seleccionada (ej. por
    'agregar dominio completo'), no debe duplicarse — sólo se le agregan
    las instrucciones. El MockProvider recomienda TODAS las preguntas
    Crítico del catálogo completo (no sólo de DDG), así que el total
    crece con las de otros dominios — lo que no debe pasar es que las 10
    de DDG se dupliquen."""
    caso = _create_caso(client, auth_headers)
    client.post(f"/casos/{caso['id']}/preguntas", json={"dominio_codigo": "DDG"}, headers=auth_headers)
    antes = client.get(f"/casos/{caso['id']}/preguntas", headers=auth_headers).json()
    ddg_antes = [p for p in antes if p["dominio_codigo"] == "DDG"]

    contenido = _docx_bytes("Sistema que procesa datos personales de clientes.")
    client.post(
        f"/casos/{caso['id']}/documentos",
        files={"file": ("doc.docx", contenido, DOCX_CONTENT_TYPE)},
        headers=auth_headers,
    )

    despues = client.get(f"/casos/{caso['id']}/preguntas", headers=auth_headers).json()
    ddg_despues = [p for p in despues if p["dominio_codigo"] == "DDG"]

    assert len(ddg_despues) == len(ddg_antes)  # no se duplicaron filas de DDG
    assert {p["pregunta_id"] for p in ddg_despues} == {p["pregunta_id"] for p in ddg_antes}
    assert len(despues) > len(antes)  # sí se sumaron críticas de otros dominios


def test_documento_con_tipo_no_soportado_devuelve_400(
    client: TestClient, auth_headers: dict[str, str], catalog_loaded: None
) -> None:
    caso = _create_caso(client, auth_headers)

    response = client.post(
        f"/casos/{caso['id']}/documentos",
        files={"file": ("imagen.png", b"fake-bytes", "image/png")},
        headers=auth_headers,
    )

    assert response.status_code == 400


def test_analizar_documento_requiere_auth(client: TestClient, catalog_loaded: None) -> None:
    response = client.post(
        "/casos/00000000-0000-0000-0000-000000000000/documentos",
        files={"file": ("doc.docx", b"x", DOCX_CONTENT_TYPE)},
    )
    assert response.status_code == 401
