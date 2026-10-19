"""Alertas de Netskope en el worker: procesamiento de reglas y aviso por email."""

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from aisec_worker.alertas import aviso
from aisec_worker.alertas.procesamiento import MARGEN, procesar
from app.alertas.models import Alerta, AlertaEvento, DestinatarioAlerta, EstadoAlerta, MetricaIA, ModoRegla, ReglaAlerta, SeveridadAlerta
from app.alertas.netskope import DemasiadosEventos, EventoNetskope, NetskopeError
from app.core.config import get_settings
from app.core.email import EmailNoEnviado

AHORA = dt.datetime(2026, 10, 19, 12, tzinfo=dt.UTC)
SETTINGS = get_settings().model_copy(
    update={"netskope_demora_minutos": 10, "netskope_retrospectiva_dias": 7, "alertas_email_destino": "aisec@macro.com.ar"}
)


def _ev(n: int, usuario: str = "externo@bmexternos.com.ar", app: str = "MCP: katalon", actividad: str = "ListToolsRequest") -> EventoNetskope:
    return EventoNetskope(
        evento_id=f"ev-{n}", fecha=AHORA - dt.timedelta(hours=2, minutes=n), usuario=usuario, app=app,
        actividad=actividad, sitio="katalon", objeto=None, datos={"appcategory": "Generative AI"},
    )


class FakeNetskope:
    def __init__(self, por_consulta: dict[str, list[EventoNetskope]], fallan: set[str] = frozenset()) -> None:
        self.por_consulta = por_consulta
        self.fallan = fallan
        self.pedidos: list[tuple[str, dt.datetime, dt.datetime]] = []

    def eventos(self, consulta: str, desde: dt.datetime, hasta: dt.datetime) -> list[EventoNetskope]:
        self.pedidos.append((consulta, desde, hasta))
        if consulta in self.fallan:
            raise NetskopeError("GET /api/v2/events/data/application -> 429", 429)
        return list(self.por_consulta.get(consulta, []))


def _mcp(db: Session) -> ReglaAlerta:
    return db.scalar(select(ReglaAlerta).where(ReglaAlerta.nombre == "Uso de servidores MCP"))


def _alertas(db: Session) -> dict[tuple[str, str], Alerta]:
    db.expire_all()
    return {(a.app, a.usuario): a for a in db.scalars(select(Alerta))}


# --- procesamiento ---


def test_agrupa_por_regla_app_y_usuario(db: Session) -> None:
    eventos = [_ev(1), _ev(2, actividad="InitializeRequest"), _ev(3), _ev(4, usuario="otro@bmexternos.com.ar")]
    netskope = FakeNetskope({"app like mcp": eventos})

    resultado = procesar(db, netskope, SETTINGS, AHORA)

    assert (resultado.eventos, resultado.nuevas) == (4, 2)
    alertas = _alertas(db)
    katalon = alertas[("MCP: katalon", "externo@bmexternos.com.ar")]
    assert (katalon.estado, katalon.severidad, katalon.cantidad_eventos) == (EstadoAlerta.NUEVA, SeveridadAlerta.ALTA, 3)
    assert katalon.actividades == {"ListToolsRequest": 2, "InitializeRequest": 1}
    assert (katalon.primera_vez, katalon.ultima_vez) == (_ev(3).fecha, _ev(1).fecha)
    assert katalon.por_notificar is True
    # Primera corrida: mira hacia atrás la retrospectiva, hasta "ahora - demora".
    _, desde, hasta = netskope.pedidos[0]
    assert (hasta, desde) == (AHORA - dt.timedelta(minutes=10), AHORA - dt.timedelta(minutes=10, days=7))
    assert _mcp(db).consultada_hasta == hasta


def test_eventos_repetidos_no_cuentan_dos_veces(db: Session) -> None:
    netskope = FakeNetskope({"app like mcp": [_ev(1), _ev(2)]})
    procesar(db, netskope, SETTINGS, AHORA)

    netskope.por_consulta["app like mcp"].append(_ev(5))
    resultado = procesar(db, netskope, SETTINGS, AHORA + dt.timedelta(minutes=5))

    assert (resultado.eventos, resultado.nuevas, resultado.actualizadas) == (1, 0, 1)
    assert _alertas(db)[("MCP: katalon", "externo@bmexternos.com.ar")].cantidad_eventos == 3
    # La segunda consulta re-mira un margen antes del cursor para no perder eventos rezagados.
    _, desde, _ = netskope.pedidos[1]
    assert desde == AHORA - dt.timedelta(minutes=10) - MARGEN


def test_reincidencia(db: Session) -> None:
    netskope = FakeNetskope({"app like mcp": [_ev(1), _ev(2, usuario="otro@bmexternos.com.ar")]})
    procesar(db, netskope, SETTINGS, AHORA)
    alertas = _alertas(db)
    resuelta = alertas[("MCP: katalon", "externo@bmexternos.com.ar")]
    descartada = alertas[("MCP: katalon", "otro@bmexternos.com.ar")]
    resuelta.estado, resuelta.por_notificar = EstadoAlerta.RESUELTA, False
    descartada.estado, descartada.por_notificar = EstadoAlerta.DESCARTADA, False
    db.commit()

    netskope.por_consulta["app like mcp"] += [_ev(7), _ev(8, usuario="otro@bmexternos.com.ar")]
    resultado = procesar(db, netskope, SETTINGS, AHORA + dt.timedelta(minutes=5))

    alertas = _alertas(db)
    vuelve = alertas[("MCP: katalon", "externo@bmexternos.com.ar")]
    sigue = alertas[("MCP: katalon", "otro@bmexternos.com.ar")]
    assert (vuelve.estado, vuelve.por_notificar) == (EstadoAlerta.NUEVA, True)  # resuelta + eventos nuevos: se reabre
    assert (sigue.estado, sigue.por_notificar, sigue.cantidad_eventos) == (EstadoAlerta.DESCARTADA, False, 2)
    assert resultado.reincidentes == 1


def test_regla_que_falla_no_avanza_y_las_demas_siguen(db: Session) -> None:
    db.add(ReglaAlerta(nombre="Asistentes de código", consulta="app like copilot", severidad=SeveridadAlerta.MEDIA))
    db.add(ReglaAlerta(nombre="Inactiva", consulta="app like nada", severidad=SeveridadAlerta.BAJA, activa=False))
    db.commit()
    netskope = FakeNetskope({"app like copilot": [_ev(1, app="GitHub Copilot")]}, fallan={"app like mcp"})

    resultado = procesar(db, netskope, SETTINGS, AHORA)

    assert [p[0] for p in netskope.pedidos] == ["app like copilot", "app like mcp"]  # la inactiva no se consulta
    assert resultado.nuevas == 1 and len(resultado.errores) == 1
    db.expire_all()
    mcp = _mcp(db)
    assert mcp.consultada_hasta is None and "429" in mcp.ultimo_error


def test_un_evento_puede_disparar_dos_reglas(db: Session) -> None:
    db.add(ReglaAlerta(nombre="Katalon", consulta="app like katalon", severidad=SeveridadAlerta.MEDIA))
    db.commit()
    netskope = FakeNetskope({"app like mcp": [_ev(1)], "app like katalon": [_ev(1)]})

    resultado = procesar(db, netskope, SETTINGS, AHORA)

    assert resultado.nuevas == 2
    assert db.query(AlertaEvento).filter_by(evento_id="ev-1").count() == 2


def test_se_borran_los_eventos_viejos(db: Session) -> None:
    viejo = _ev(1)
    viejo.fecha = AHORA - dt.timedelta(days=120)
    procesar(db, FakeNetskope({"app like mcp": [viejo, _ev(2)]}), SETTINGS, AHORA)

    assert [e.evento_id for e in db.scalars(select(AlertaEvento))] == ["ev-2"]


# --- aviso por email ---


@pytest.fixture
def enviados(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    salida: list[dict] = []
    monkeypatch.setattr(aviso, "send_email", lambda **kwargs: salida.append(kwargs))
    return salida


def test_un_solo_email_resumen_por_vuelta(db: Session, enviados: list[dict]) -> None:
    procesar(db, FakeNetskope({"app like mcp": [_ev(1), _ev(2, usuario="otro@bmexternos.com.ar")]}), SETTINGS, AHORA)

    assert aviso.notificar(db, SETTINGS, AHORA) == 2

    [email] = enviados
    assert email["to"] == "aisec@macro.com.ar"
    assert email["subject"] == "[AI-SEC] 2 alertas nuevas de Netskope"
    assert "MCP: katalon" in email["text"] and "/alertas?alerta=" in email["text"]
    assert all(not a.por_notificar and a.notificada_at == AHORA for a in _alertas(db).values())
    assert aviso.notificar(db, SETTINGS, AHORA) == 0 and len(enviados) == 1  # no se repite


def test_sin_destino_o_con_error_quedan_pendientes(db: Session, enviados: list[dict], monkeypatch: pytest.MonkeyPatch) -> None:
    procesar(db, FakeNetskope({"app like mcp": [_ev(1)]}), SETTINGS, AHORA)

    assert aviso.notificar(db, SETTINGS.model_copy(update={"alertas_email_destino": None}), AHORA) == 0

    def falla(**kwargs):
        raise EmailNoEnviado("relay caído")

    monkeypatch.setattr(aviso, "send_email", falla)
    assert aviso.notificar(db, SETTINGS, AHORA) == 0
    assert all(a.por_notificar for a in _alertas(db).values())  # se reintenta en la próxima vuelta


def test_reglas_sin_email_no_avisan(db: Session, enviados: list[dict]) -> None:
    regla = _mcp(db)
    regla.notificar_email = False
    db.commit()
    procesar(db, FakeNetskope({"app like mcp": [_ev(1)]}), SETTINGS, AHORA)

    assert aviso.notificar(db, SETTINGS, AHORA) == 0
    assert enviados == [] and not any(a.por_notificar for a in _alertas(db).values())


def test_ventana_con_demasiados_eventos_se_parte(db: Session) -> None:
    """Si Netskope tiene más eventos que el tope, la ventana se divide en
    mitades hasta que cada parte entra completa: no se pierde nada."""
    eventos = [_ev(n) for n in range(40)]

    class Tope(FakeNetskope):
        def eventos(self, consulta, desde, hasta):
            self.pedidos.append((consulta, desde, hasta))
            dentro = [e for e in eventos if desde <= e.fecha < hasta]
            if len(dentro) > 15:
                raise DemasiadosEventos("tope")
            return dentro

    netskope = Tope({})
    resultado = procesar(db, netskope, SETTINGS, AHORA)

    assert resultado.eventos == 40 and not resultado.errores
    assert len(netskope.pedidos) > 1


def test_reglas_en_modo_metrica_suman_totales_sin_alertas(db: Session, enviados: list[dict]) -> None:
    regla = ReglaAlerta(
        nombre="Subida a IA generativa", consulta="category eq 'Generative AI' and activity eq 'Upload'",
        severidad=SeveridadAlerta.ALTA, modo=ModoRegla.METRICA, notificar_email=False,
    )
    _mcp(db).activa = False
    db.add(regla)
    db.commit()
    netskope = FakeNetskope({regla.consulta: [_ev(1, actividad="Upload"), _ev(2, actividad="Upload"), _ev(3, usuario="otro", actividad="Upload")]})

    procesar(db, netskope, SETTINGS, AHORA)
    procesar(db, netskope, SETTINGS, AHORA + dt.timedelta(minutes=5))  # la segunda ventana arranca donde terminó la primera

    assert db.query(Alerta).count() == 0 and aviso.notificar(db, SETTINGS, AHORA) == 0
    totales = {(m.usuario, m.actividad): m.eventos for m in db.scalars(select(MetricaIA))}
    # El Fake devuelve los mismos eventos en la segunda vuelta: en métricas se suman
    # (por eso la ventana de las métricas no se superpone con la anterior).
    assert totales == {("externo@bmexternos.com.ar", "Upload"): 4, ("otro", "Upload"): 2}
    _, desde_2, _ = netskope.pedidos[1]
    _, _, hasta_1 = netskope.pedidos[0]
    assert desde_2 == hasta_1  # sin margen


def test_los_destinatarios_de_la_plataforma_reemplazan_a_la_variable(db: Session, enviados: list[dict]) -> None:
    db.add_all([
        DestinatarioAlerta(email="soc@macro.com.ar"),
        DestinatarioAlerta(email="jefe@macro.com.ar"),
        DestinatarioAlerta(email="de-licencia@macro.com.ar", activo=False),
    ])
    db.commit()
    procesar(db, FakeNetskope({"app like mcp": [_ev(1)]}), SETTINGS, AHORA)

    assert aviso.notificar(db, SETTINGS, AHORA) == 1

    # SETTINGS tiene aisec@macro.com.ar en la variable: no se usa porque hay destinatarios cargados.
    assert sorted(e["to"] for e in enviados) == ["jefe@macro.com.ar", "soc@macro.com.ar"]
