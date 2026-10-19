"""Sector Alertas: API de alertas y reglas, y el cliente de Netskope."""

import datetime as dt
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alertas import netskope
from app.alertas.models import Alerta, AlertaEvento, FuenteRegla, ReglaAlerta, SeveridadAlerta, TipoReglaTenable
from app.casos.models import Caso
from app.core.config import get_settings

AHORA = dt.datetime(2026, 10, 19, 12, tzinfo=dt.UTC)


def _evento(n: int, **cambios) -> dict:
    base = {
        "_id": f"ev-{n}",
        "timestamp": int((AHORA - dt.timedelta(hours=1, minutes=n)).timestamp()),
        "user": "externo@bmexternos.com.ar",
        "app": "MCP: katalon",
        "activity": "ListToolsRequest",
        "site": "katalon",
        "category": "Generative AI",
        "mcp_client_name": "claude-code",
        "JWT_email": "no se guarda",
        "campo_irrelevante": "no se guarda",
    }
    return {**base, **cambios}


def _cliente(eventos: list[dict], pedidos: list[httpx.Request] | None = None, status: int = 200) -> netskope.NetskopeClient:
    def responder(request: httpx.Request) -> httpx.Response:
        if pedidos is not None:
            pedidos.append(request)
        offset = int(request.url.params.get("offset", 0))
        limite = int(request.url.params.get("limit", 1000))
        return httpx.Response(status, json={"ok": 1, "result": eventos[offset : offset + limite]})

    settings = get_settings().model_copy(update={"netskope_api_token": "token-de-prueba"})
    return netskope.NetskopeClient(settings, transport=httpx.MockTransport(responder))


def _regla(db: Session) -> ReglaAlerta:
    return db.scalar(select(ReglaAlerta).where(ReglaAlerta.nombre == "Uso de servidores MCP"))


def _alerta(db: Session, **cambios) -> Alerta:
    alerta = Alerta(
        regla_id=_regla(db).id,
        app="MCP: katalon",
        usuario="externo@bmexternos.com.ar",
        severidad=SeveridadAlerta.ALTA,
        primera_vez=AHORA - dt.timedelta(days=2),
        ultima_vez=AHORA - dt.timedelta(hours=1),
        cantidad_eventos=4,
        actividades={"ListToolsRequest": 2, "InitializeRequest": 2},
        **cambios,
    )
    db.add(alerta)
    db.flush()
    db.add(AlertaEvento(alerta_id=alerta.id, evento_id="ev-1", fecha=AHORA, actividad="ListToolsRequest", datos={}))
    db.commit()
    return alerta


# --- cliente de Netskope ---


def test_cliente_arma_la_consulta_y_normaliza_eventos() -> None:
    pedidos: list[httpx.Request] = []
    client = _cliente([_evento(1), _evento(2, activity=None), {"_id": "sin-app", "timestamp": 1}], pedidos)

    eventos = client.eventos("app like mcp", AHORA - dt.timedelta(hours=2), AHORA)

    pedido = pedidos[0]
    assert pedido.url.path == "/api/v2/events/data/application"
    assert pedido.headers["Netskope-Api-Token"] == "token-de-prueba"
    assert pedido.url.params["query"] == "app like mcp"
    assert int(pedido.url.params["endtime"]) == int(AHORA.timestamp())
    assert [e.evento_id for e in eventos] == ["ev-1", "ev-2"]  # el evento sin app se ignora
    primero = eventos[0]
    assert (primero.app, primero.usuario, primero.actividad) == ("MCP: katalon", "externo@bmexternos.com.ar", "ListToolsRequest")
    assert primero.datos["category"] == "Generative AI" and primero.datos["mcp_client_name"] == "claude-code"
    assert "campo_irrelevante" not in primero.datos and "JWT_email" not in primero.datos


def test_cliente_pagina(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netskope, "TAMANIO_PAGINA", 2)
    pedidos: list[httpx.Request] = []

    eventos = _cliente([_evento(n) for n in range(5)], pedidos).eventos("app like mcp", AHORA - dt.timedelta(days=1), AHORA)

    assert len(eventos) == 5
    assert [int(p.url.params["offset"]) for p in pedidos] == [0, 2, 4]


def test_cliente_error_y_token_faltante() -> None:
    with pytest.raises(netskope.NetskopeError, match="403"):
        _cliente([], status=403).eventos("app like mcp", AHORA - dt.timedelta(hours=1), AHORA)
    with pytest.raises(netskope.NetskopeError, match="API_TOKEN"):
        netskope.NetskopeClient(get_settings().model_copy(update={"netskope_api_token": None}))


# --- reglas ---


def test_regla_de_mcp_precargada(client: TestClient, auth_headers: dict[str, str]) -> None:
    reglas = client.get("/alertas/reglas", headers=auth_headers).json()

    mcp = next(r for r in reglas if r["nombre"] == "Uso de servidores MCP")
    assert (mcp["consulta"], mcp["severidad"], mcp["activa"], mcp["notificar_email"]) == ("app like mcp", "alta", True, True)


def test_reglas_las_edita_un_admin(client: TestClient, auth_headers: dict[str, str], admin_headers: dict[str, str]) -> None:
    nueva = {"nombre": "Asistentes de código", "consulta": "appcategory eq 'Generative AI'", "severidad": "media"}

    assert client.post("/alertas/reglas", json=nueva, headers=auth_headers).status_code == 403
    creada = client.post("/alertas/reglas", json=nueva, headers=admin_headers)
    assert creada.status_code == 201
    assert client.post("/alertas/reglas", json=nueva, headers=admin_headers).status_code == 409

    regla_id = creada.json()["id"]
    editada = client.patch(f"/alertas/reglas/{regla_id}", json={"activa": False}, headers=admin_headers)
    assert editada.json()["activa"] is False
    assert client.delete(f"/alertas/reglas/{regla_id}", headers=admin_headers).status_code == 204


def test_cambiar_la_consulta_reinicia_el_cursor(client: TestClient, admin_headers: dict[str, str], db: Session) -> None:
    regla = _regla(db)
    regla.consultada_hasta = AHORA
    db.commit()

    client.patch(f"/alertas/reglas/{regla.id}", json={"consulta": "app like 'mcp'"}, headers=admin_headers)

    db.expire_all()
    assert _regla(db).consultada_hasta is None


def test_probar_regla(client: TestClient, admin_headers: dict[str, str], db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    eventos = [_evento(1), _evento(2, user="otro@bmexternos.com.ar"), _evento(3, app="MCP: github")]
    monkeypatch.setattr(netskope, "crear_cliente", lambda: _cliente(eventos))

    response = client.post(f"/alertas/reglas/{_regla(db).id}/probar", headers=admin_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["cantidad"], body["usuarios"]) == (3, 2)
    assert body["por_app"] == {"MCP: katalon": 2, "MCP: github": 1}
    assert db.query(Alerta).count() == 0  # probar no crea alertas


def test_probar_con_netskope_deshabilitado(client: TestClient, admin_headers: dict[str, str], db: Session) -> None:
    assert client.post(f"/alertas/reglas/{_regla(db).id}/probar", headers=admin_headers).status_code == 503


# --- alertas ---


def test_listar_detalle_y_resumen(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    alerta = _alerta(db)

    lista = client.get("/alertas", headers=auth_headers).json()
    detalle = client.get(f"/alertas/{alerta.id}", headers=auth_headers).json()
    resumen = client.get("/alertas/resumen", headers=auth_headers).json()

    assert [(a["app"], a["regla_nombre"], a["estado"]) for a in lista] == [("MCP: katalon", "Uso de servidores MCP", "nueva")]
    assert detalle["eventos"][0]["evento_id"] == "ev-1"
    assert resumen == {"nuevas": 1, "en_revision": 0}
    assert client.get("/alertas", params={"estado": "resuelta"}, headers=auth_headers).json() == []
    assert client.get(f"/alertas/{uuid.uuid4()}", headers=auth_headers).status_code == 404


def test_gestionar_estado_y_nota(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    alerta = _alerta(db, por_notificar=True)

    response = client.patch(
        f"/alertas/{alerta.id}", json={"estado": "descartada", "nota": "Uso aprobado por el área"}, headers=auth_headers
    )

    assert (response.json()["estado"], response.json()["nota"]) == ("descartada", "Uso aprobado por el área")
    db.expire_all()
    assert db.get(Alerta, alerta.id).por_notificar is False  # ya la vio alguien: no se avisa por email


def test_vincular_crear_y_desvincular_caso(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    alerta = _alerta(db)
    caso = client.post("/casos", json={"nombre_proyecto": "Assessment Katalon Studio"}, headers=auth_headers).json()

    vinculada = client.post(f"/alertas/{alerta.id}/caso", json={"caso_id": caso["id"]}, headers=auth_headers).json()
    assert vinculada["caso_nombre"] == "Assessment Katalon Studio"
    assert [a["id"] for a in client.get("/alertas", params={"caso_id": caso["id"]}, headers=auth_headers).json()] == [str(alerta.id)]

    creada = client.post(f"/alertas/{alerta.id}/caso", json={"crear": True}, headers=auth_headers).json()
    assert creada["caso_nombre"] == "MCP: katalon"
    nuevo = db.get(Caso, uuid.UUID(creada["caso_id"]))
    assert nuevo.jira_sync_estado.value == "pendiente"  # se crea también en Jira (vía worker)

    sin_caso = client.post(f"/alertas/{alerta.id}/caso", json={}, headers=auth_headers).json()
    assert sin_caso["caso_id"] is None
    assert client.post(f"/alertas/{alerta.id}/caso", json={"caso_id": str(uuid.uuid4())}, headers=auth_headers).status_code == 404


def test_detalle_con_contexto_de_tenable(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    from app.alertas.models import EquipoTenable

    alerta = _alerta(db, equipos=["bmn1234", "pc-sin-tenable"])
    db.add(EquipoTenable(asset_uuid="a1", hostname="bmn1234", con_inventario=True, tiene_agente=True,
                         software_ia=["Ollama", "Python"], puertos_ia=[], actualizado_at=AHORA))
    db.commit()

    contexto = client.get(f"/alertas/{alerta.id}", headers=auth_headers).json()["contexto_equipos"]

    assert contexto[0]["equipo"] == "bmn1234" and contexto[0]["software_ia"] == ["Ollama", "Python"]
    assert contexto[1] == {**contexto[1], "equipo": "pc-sin-tenable", "en_tenable": False}


def test_tiempos_de_atencion(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    alerta = _alerta(db)

    tomada = client.patch(f"/alertas/{alerta.id}", json={"estado": "en_revision"}, headers=auth_headers).json()
    cerrada = client.patch(f"/alertas/{alerta.id}", json={"estado": "resuelta"}, headers=auth_headers).json()
    reabierta = client.patch(f"/alertas/{alerta.id}", json={"estado": "nueva"}, headers=auth_headers).json()

    assert tomada["atendida_at"] and tomada["cerrada_at"] is None
    assert cerrada["cerrada_at"] and cerrada["atendida_at"] == tomada["atendida_at"]  # la primera atención no cambia
    assert reabierta["cerrada_at"] is None


def test_equipo_fuera_de_tenable_muestra_las_alertas_que_lo_originaron(
    client: TestClient, auth_headers: dict[str, str], db: Session
) -> None:
    origen = _alerta(db, equipos=["000gsi54", "bmn1"])
    db.add(Alerta(  # sólo en otro equipo: no aparece
        regla_id=origen.regla_id, app="Otra app", usuario="otro@macro.com.ar", severidad=SeveridadAlerta.ALTA,
        primera_vez=AHORA, ultima_vez=AHORA, equipos=["bmn1"],
    ))
    regla = ReglaAlerta(
        nombre="Equipo fuera de Tenable", consulta=TipoReglaTenable.FUERA_DE_COBERTURA.value,
        severidad=SeveridadAlerta.MEDIA, fuente=FuenteRegla.TENABLE,
    )
    db.add(regla)
    db.flush()
    brecha = Alerta(
        regla_id=regla.id, app="Sin inventario de Tenable", usuario="000gsi54", severidad=SeveridadAlerta.MEDIA,
        primera_vez=AHORA, ultima_vez=AHORA, equipos=["000gsi54"],
    )
    db.add(brecha)
    db.commit()

    detalle = client.get(f"/alertas/{brecha.id}", headers=auth_headers).json()

    assert (detalle["regla_fuente"], detalle["regla_tipo"]) == ("tenable", "fuera_de_cobertura")
    assert [o["id"] for o in detalle["alertas_origen"]] == [str(origen.id)]
    assert detalle["alertas_origen"][0]["usuario"] == "externo@bmexternos.com.ar"
    # Las de Netskope no traen origen.
    netskope_ = client.get(f"/alertas/{origen.id}", headers=auth_headers).json()
    assert (netskope_["regla_tipo"], netskope_["alertas_origen"]) == (None, [])
    # El caso de una alerta de Tenable se nombra con el equipo.
    caso = client.post(f"/alertas/{brecha.id}/caso", json={"crear": True}, headers=auth_headers).json()
    assert caso["caso_nombre"] == "Sin inventario de Tenable – 000gsi54"


def test_filtrar_por_usuario_app_y_fecha(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    katalon = _alerta(db)  # externo@bmexternos, MCP: katalon, actividad hace 2 días -> hace 1 hora
    vieja = Alerta(
        regla_id=katalon.regla_id, app="DeepSeek", usuario="ana_lopez@macro.com.ar", severidad=SeveridadAlerta.ALTA,
        primera_vez=AHORA - dt.timedelta(days=20), ultima_vez=AHORA - dt.timedelta(days=10),
    )
    db.add(vieja)
    db.commit()

    def ids(**params) -> set[str]:
        return {a["id"] for a in client.get("/alertas", params=params, headers=auth_headers).json()}

    assert ids(usuario="BMEXTERNOS") == {str(katalon.id)}  # contiene, sin distinguir mayúsculas
    assert ids(app="deep") == {str(vieja.id)}
    assert ids(usuario="a_l") == {str(vieja.id)}  # "_" es literal, no comodín
    assert ids(usuario="%") == set()
    hoy = AHORA.date()
    assert ids(desde=str(hoy - dt.timedelta(days=3))) == {str(katalon.id)}
    assert ids(hasta=str(hoy - dt.timedelta(days=5))) == {str(vieja.id)}
    assert ids(desde=str(hoy - dt.timedelta(days=15)), hasta=str(hoy - dt.timedelta(days=12))) == {str(vieja.id)}


def test_destinatarios_del_email(client: TestClient, auth_headers: dict[str, str], admin_headers: dict[str, str]) -> None:
    # Sin destinatarios cargados se usa la variable de entorno (en los tests, vacía).
    inicial = client.get("/alertas/destinatarios", headers=auth_headers).json()
    assert (inicial["destinatarios"], inicial["origen"], inicial["en_uso"]) == ([], "ninguno", [])

    nuevo = {"email": "  SOC@Macro.com.ar ", "nombre": "SOC"}
    assert client.post("/alertas/destinatarios", json=nuevo, headers=auth_headers).status_code == 403  # sólo admin
    creado = client.post("/alertas/destinatarios", json=nuevo, headers=admin_headers)
    assert creado.status_code == 201
    assert creado.json()["en_uso"] == ["soc@macro.com.ar"] and creado.json()["origen"] == "plataforma"
    assert client.post("/alertas/destinatarios", json={"email": "soc@macro.com.ar"}, headers=admin_headers).status_code == 409
    assert client.post("/alertas/destinatarios", json={"email": "no-es-email"}, headers=admin_headers).status_code == 422

    destinatario_id = creado.json()["destinatarios"][0]["id"]
    pausado = client.patch(f"/alertas/destinatarios/{destinatario_id}", json={"activo": False}, headers=admin_headers).json()
    assert pausado["destinatarios"][0]["activo"] is False and pausado["origen"] == "ninguno"
    assert client.delete(f"/alertas/destinatarios/{destinatario_id}", headers=auth_headers).status_code == 403
    assert client.delete(f"/alertas/destinatarios/{destinatario_id}", headers=admin_headers).json()["destinatarios"] == []
