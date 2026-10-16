"""H7: API de herramientas (Catálogo, Radar, vínculos, distribuciones, revisión)."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pentesting.models import (
    Distribucion,
    EstadoHerramienta,
    EstadoRevision,
    EstadoVinculo,
    HerramientaPaso,
    HerramientaPentest,
    OrigenVinculo,
    PentestEstandarPaso,
    RevisionHerramientas,
    TipoHerramienta,
)

URL = "/pentesting/herramientas"


def _paso(db: Session, codigo: str) -> PentestEstandarPaso:
    return db.scalar(select(PentestEstandarPaso).where(PentestEstandarPaso.codigo == codigo))


def _candidata(db: Session, nombre: str = "llm-fuzzer", sugeridos: tuple[str, ...] = ("LLM01", "RT04")) -> HerramientaPentest:
    herramienta = HerramientaPentest(
        nombre=nombre, tipo=TipoHerramienta.IA, estado=EstadoHerramienta.CANDIDATA, origen="github:llm-security",
        repo_github=f"acme/{nombre}", estrellas=800,
    )
    for codigo in sugeridos:
        herramienta.pasos.append(
            HerramientaPaso(paso=_paso(db, codigo), origen=OrigenVinculo.SUGERIDO_IA, estado=EstadoVinculo.SUGERIDO,
                            justificacion=f"sirve para {codigo}")
        )
    db.add(herramienta)
    db.commit()
    return herramienta


def test_secciones(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    _candidata(db)
    client.post(URL, json={"nombre": "Burp Suite"}, headers=auth_headers)

    catalogo = client.get(URL, headers=auth_headers).json()
    radar = client.get(URL, params={"seccion": "radar"}, headers=auth_headers).json()

    assert [h["nombre"] for h in catalogo] == ["Burp Suite"]
    assert [h["nombre"] for h in radar] == ["llm-fuzzer"]
    # Ordenados por estándar (AISEC-RED-TEAM-IA < OWASP-LLM-TOP10-2025) y por orden del paso.
    assert [p["paso_codigo"] for p in radar[0]["pasos"]] == ["RT04", "LLM01"]
    vinculo = next(p for p in radar[0]["pasos"] if p["paso_codigo"] == "LLM01")
    assert vinculo["estandar_codigo"] == "OWASP-LLM-TOP10-2025"
    assert (vinculo["origen"], vinculo["estado"]) == ("sugerido_ia", "sugerido")


def test_alta_manual_con_datos(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        URL,
        json={"nombre": "garak", "tipo": "ia", "repo_github": "NVIDIA/garak", "paquete": "pypi:garak",
              "documentacion_url": "https://reference.garak.ai/en/latest/"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["tipo"], body["estado"], body["origen"]) == ("ia", "activa", "manual")
    assert client.post(URL, json={"nombre": "otra", "repo_github": "NVIDIA/garak"}, headers=auth_headers).status_code == 409
    assert client.post(URL, json={"nombre": "mala", "repo_github": "no es un repo"}, headers=auth_headers).status_code == 422
    assert client.post(URL, json={"nombre": "mala", "paquete": "cargo:algo"}, headers=auth_headers).status_code == 422


def test_aprobar_con_los_pasos_que_confirma_el_analista(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    herramienta = _candidata(db)
    llm01, rt05 = _paso(db, "LLM01"), _paso(db, "RT05")

    response = client.post(
        f"{URL}/{herramienta.id}/aprobar", json={"pasos": [str(llm01.id), str(rt05.id)]}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["estado"] == "activa"
    pasos = {p["paso_codigo"]: (p["origen"], p["estado"]) for p in body["pasos"]}
    # LLM01 sugerido -> confirmado; RT04 sugerido y no elegido -> se quita; RT05 lo agrega el analista.
    assert pasos == {"LLM01": ("sugerido_ia", "confirmado"), "RT05": ("analista", "confirmado")}
    assert client.post(f"{URL}/{herramienta.id}/aprobar", json={}, headers=auth_headers).status_code == 409


def test_aprobar_con_paso_inexistente(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    herramienta = _candidata(db)

    response = client.post(f"{URL}/{herramienta.id}/aprobar", json={"pasos": [str(uuid.uuid4())]}, headers=auth_headers)

    assert response.status_code == 400
    db.expire_all()
    assert db.get(HerramientaPentest, herramienta.id).estado == EstadoHerramienta.CANDIDATA


def test_descartar_requiere_motivo_y_sale_del_radar(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    herramienta = _candidata(db)

    assert client.post(f"{URL}/{herramienta.id}/descartar", json={"motivo": ""}, headers=auth_headers).status_code == 422
    response = client.post(f"{URL}/{herramienta.id}/descartar", json={"motivo": "Es una lista de enlaces"}, headers=auth_headers)

    assert response.json()["estado"] == "descartada"
    assert client.get(URL, params={"seccion": "radar"}, headers=auth_headers).json() == []
    descartadas = client.get(URL, params={"seccion": "descartadas"}, headers=auth_headers).json()
    assert descartadas[0]["motivo_estado"] == "Es una lista de enlaces"


def test_retirar_y_reactivar(client: TestClient, auth_headers: dict[str, str]) -> None:
    herramienta = client.post(URL, json={"nombre": "Counterfit"}, headers=auth_headers).json()

    retirada = client.post(f"{URL}/{herramienta['id']}/retirar", json={"motivo": "Sin mantenimiento"}, headers=auth_headers)
    assert (retirada.json()["estado"], retirada.json()["motivo_estado"]) == ("retirada", "Sin mantenimiento")
    assert client.post(f"{URL}/{herramienta['id']}/descartar", json={"motivo": "xyz"}, headers=auth_headers).status_code == 409

    reactivada = client.post(f"{URL}/{herramienta['id']}/reactivar", headers=auth_headers)
    assert (reactivada.json()["estado"], reactivada.json()["motivo_estado"]) == ("activa", None)


def test_vincular_desvincular_y_recomendadas_por_paso(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    herramienta = client.post(URL, json={"nombre": "garak", "tipo": "ia"}, headers=auth_headers).json()
    _candidata(db, sugeridos=("LLM01",))  # sugerida en el Radar: no se recomienda todavía
    llm01 = _paso(db, "LLM01")
    url_paso = f"/pentesting/estandares/{llm01.estandar_id}/pasos/{llm01.id}/herramientas"

    vinculada = client.put(f"{URL}/{herramienta['id']}/pasos/{llm01.id}", headers=auth_headers)
    assert [(p["paso_codigo"], p["origen"], p["estado"]) for p in vinculada.json()["pasos"]] == [
        ("LLM01", "analista", "confirmado")
    ]
    assert [h["nombre"] for h in client.get(url_paso, headers=auth_headers).json()] == ["garak"]

    client.delete(f"{URL}/{herramienta['id']}/pasos/{llm01.id}", headers=auth_headers)
    assert client.get(url_paso, headers=auth_headers).json() == []
    otro_estandar = f"/pentesting/estandares/{uuid.uuid4()}/pasos/{llm01.id}/herramientas"
    assert client.get(otro_estandar, headers=auth_headers).status_code == 404


def test_distribuciones(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    db.add_all([Distribucion(codigo="blackarch", nombre="BlackArch"), Distribucion(codigo="kali", nombre="Kali Linux")])
    db.commit()

    response = client.get("/pentesting/distribuciones", headers=auth_headers)

    assert [d["codigo"] for d in response.json()] == ["kali", "blackarch"]


def test_revisar_ahora_es_de_admin_y_no_se_duplica(
    client: TestClient, auth_headers: dict[str, str], admin_headers: dict[str, str], db: Session
) -> None:
    _candidata(db)
    estado = client.get(f"{URL}/revision", headers=auth_headers).json()
    assert (estado["ultima"], estado["pendiente"], estado["candidatas"]) == (None, None, 1)

    assert client.post(f"{URL}/revision", headers=auth_headers).status_code == 403
    primera = client.post(f"{URL}/revision", headers=admin_headers)
    segunda = client.post(f"{URL}/revision", headers=admin_headers)

    assert primera.status_code == 202
    assert primera.json()["pendiente"]["estado"] == "solicitada"
    assert segunda.json()["pendiente"]["id"] == primera.json()["pendiente"]["id"]
    assert db.query(RevisionHerramientas).filter_by(estado=EstadoRevision.SOLICITADA).count() == 1
