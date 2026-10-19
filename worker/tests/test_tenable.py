"""Tenable: cliente de exportación, inventario de equipos y reglas de fuente Tenable."""

import datetime as dt

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from aisec_worker.alertas.tenable_inventario import debe_sincronizar, evaluar_reglas, normalizar_host, sincronizar
from app.alertas.models import (
    Alerta,
    EquipoTenable,
    EstadoAlerta,
    FuenteRegla,
    ReglaAlerta,
    SeveridadAlerta,
    TipoReglaTenable,
)
from app.alertas.tenable import PLUGINS_PUERTOS, PLUGINS_SOFTWARE, TenableClient, TenableError
from app.core.config import get_settings

AHORA = dt.datetime(2026, 10, 19, 12, tzinfo=dt.UTC)


def _registro(uuid: str, hostname: str, output: str = "", puerto: int = 0, source: str = "NESSUS", netbios: str = "") -> dict:
    return {
        "asset": {"uuid": uuid, "hostname": hostname, "netbios_name": netbios, "operating_system": ["Microsoft Windows 11"], "agent_uuid": "x"},
        "output": output,
        "port": {"port": puerto},
        "source": source,
        "last_found": "2026-10-18T05:43:40.062Z",
    }


class FakeTenable:
    def __init__(self, software: list[dict], puertos: list[dict]) -> None:
        self.por_plugins = {tuple(PLUGINS_SOFTWARE): software, tuple(PLUGINS_PUERTOS): puertos}

    def exportar(self, plugin_ids: list[int]):
        yield from self.por_plugins[tuple(plugin_ids)]


SOFTWARE = [
    _registro("a1", "BMN1234.macro.local", "Ollama  [version 0.12.3]  [installed on 2026/09/30]\nPython 3.12.1 (64-bit)", source="AGENT"),
    _registro("a2", "srv-ia", "Anaconda3 2024.10-1\nJupyter Notebook 7.2"),
    # "Jan 12" es una fecha de instalación, no la app Jan: no debe contar.
    _registro("a3", "pc-normal", "Microsoft Office  [installed on Jan 12, 2025]"),
    _registro("a5", "", "Python 3.11.4", netbios="LEGACY01"),
]
PUERTOS = [
    _registro("a2", "srv-ia", puerto=11434),
    _registro("a2", "srv-ia", puerto=443),
    _registro("a4", "sin-credenciales", puerto=8888),  # escaneado pero sin inventario de software
]


def _regla(db: Session, tipo: TipoReglaTenable, severidad=SeveridadAlerta.ALTA) -> ReglaAlerta:
    regla = ReglaAlerta(nombre=f"Tenable {tipo.value}", consulta=tipo.value, severidad=severidad, fuente=FuenteRegla.TENABLE)
    db.add(regla)
    db.commit()
    return regla


def _equipos(db: Session) -> dict[str, EquipoTenable]:
    db.expire_all()
    return {e.asset_uuid: e for e in db.scalars(select(EquipoTenable))}


# --- cliente ---


def _cliente(respuestas: dict[str, list]) -> TenableClient:
    def responder(request: httpx.Request) -> httpx.Response:
        for ruta, cola in respuestas.items():
            if request.url.path.endswith(ruta):
                return httpx.Response(200, json=cola.pop(0) if len(cola) > 1 else cola[0])
        return httpx.Response(404)

    settings = get_settings().model_copy(update={"tenable_access_key": "ak", "tenable_secret_key": "sk"})
    client = TenableClient(settings, transport=httpx.MockTransport(responder))
    client._esperar = lambda segundos: None
    return client


def test_cliente_espera_la_exportacion_y_recorre_los_chunks() -> None:
    client = _cliente({
        "/vulns/export": [{"export_uuid": "u1"}],
        "/vulns/export/u1/status": [{"status": "PROCESSING"}, {"status": "FINISHED", "chunks_available": [1, 2]}],
        "/chunks/1": [[{"id": 1}, {"id": 2}]],
        "/chunks/2": [[{"id": 3}]],
    })

    assert [r["id"] for r in client.exportar([20811])] == [1, 2, 3]


def test_cliente_exportacion_fallida_o_sin_claves() -> None:
    client = _cliente({"/vulns/export": [{"export_uuid": "u1"}], "/vulns/export/u1/status": [{"status": "ERROR"}]})
    with pytest.raises(TenableError, match="error"):
        list(client.exportar([20811]))
    with pytest.raises(TenableError, match="ACCESS_KEY"):
        TenableClient(get_settings().model_copy(update={"tenable_access_key": None}))


# --- inventario ---


def test_sincronizar_arma_el_inventario(db: Session) -> None:
    resultado = sincronizar(db, FakeTenable(SOFTWARE, PUERTOS), AHORA)

    equipos = _equipos(db)
    assert (resultado.equipos, resultado.con_inventario, resultado.con_puertos_ia) == (5, 4, 2)
    notebook = equipos["a1"]
    assert (notebook.hostname, notebook.software_ia, notebook.tiene_agente) == ("bmn1234", ["Ollama", "Python"], True)
    servidor = equipos["a2"]
    assert servidor.software_ia == ["Anaconda", "Jupyter"]
    assert servidor.puertos_ia == [{"puerto": 11434, "servicio": "Ollama"}] and servidor.tiene_agente is False
    assert equipos["a3"].software_ia == []  # la fecha "Jan 12" no es la app Jan
    assert equipos["a4"].con_inventario is False and equipos["a4"].puertos_ia == [{"puerto": 8888, "servicio": "Jupyter"}]
    assert (equipos["a5"].hostname, equipos["a5"].netbios) == (None, "legacy01")


def test_cada_sincronizacion_reemplaza_el_inventario(db: Session) -> None:
    sincronizar(db, FakeTenable(SOFTWARE, PUERTOS), AHORA)
    sincronizar(db, FakeTenable(SOFTWARE[:1], []), AHORA + dt.timedelta(days=1))

    assert set(_equipos(db)) == {"a1"}


def test_cuando_toca_sincronizar(db: Session) -> None:
    assert debe_sincronizar(db, 24, AHORA) is True
    sincronizar(db, FakeTenable([], []), AHORA)
    assert debe_sincronizar(db, 24, dt.datetime.now(dt.UTC)) is False


def test_normalizar_host() -> None:
    assert [normalizar_host(x) for x in ("BMN1234.macro.local", "", None, "pc")] == ["bmn1234", None, None, "pc"]


# --- reglas de fuente Tenable ---


def test_servicio_de_ia_expuesto(db: Session) -> None:
    regla = _regla(db, TipoReglaTenable.SERVICIO_IA_EXPUESTO)
    sincronizar(db, FakeTenable(SOFTWARE, PUERTOS), AHORA)

    resultado = evaluar_reglas(db, AHORA)

    alertas = {(a.app, a.usuario) for a in db.scalars(select(Alerta).where(Alerta.regla_id == regla.id))}
    assert alertas == {("Ollama (puerto 11434)", "srv-ia"), ("Jupyter (puerto 8888)", "sin-credenciales")}
    assert resultado.nuevas == 2
    assert evaluar_reglas(db, AHORA).nuevas == 0  # no se duplica


def test_equipo_con_actividad_de_ia_fuera_de_cobertura(db: Session) -> None:
    cobertura = _regla(db, TipoReglaTenable.FUERA_DE_COBERTURA, SeveridadAlerta.MEDIA)
    mcp = db.scalar(select(ReglaAlerta).where(ReglaAlerta.nombre == "Uso de servidores MCP"))
    for equipos in (["bmn1234"], ["legacy01"], ["bmn9999"], ["pc-sin-tenable", "bmn9999"]):
        db.add(Alerta(regla_id=mcp.id, app="MCP: x", usuario="+".join(equipos), severidad=SeveridadAlerta.ALTA,
                      primera_vez=AHORA, ultima_vez=AHORA, equipos=equipos))
    # Una cerrada no cuenta.
    db.add(Alerta(regla_id=mcp.id, app="MCP: y", usuario="u", severidad=SeveridadAlerta.ALTA, primera_vez=AHORA,
                  ultima_vez=AHORA, equipos=["cerrado"], estado=EstadoAlerta.RESUELTA))
    db.commit()
    sincronizar(db, FakeTenable(SOFTWARE, PUERTOS), AHORA)

    evaluar_reglas(db, AHORA)

    alertas = {a.usuario: a for a in db.scalars(select(Alerta).where(Alerta.regla_id == cobertura.id))}
    # bmn1234 (hostname) y legacy01 (NetBIOS) están inventariados; los otros no.
    assert set(alertas) == {"bmn9999", "pc-sin-tenable"}
    assert alertas["bmn9999"].cantidad_eventos == 2
    assert alertas["bmn9999"].actividades == {"Uso de servidores MCP": 2}


def test_alerta_de_tenable_resuelta_reincide(db: Session) -> None:
    regla = _regla(db, TipoReglaTenable.SERVICIO_IA_EXPUESTO)
    sincronizar(db, FakeTenable(SOFTWARE, PUERTOS), AHORA)
    evaluar_reglas(db, AHORA)
    alerta = db.scalar(select(Alerta).where(Alerta.regla_id == regla.id, Alerta.usuario == "srv-ia"))
    alerta.estado = EstadoAlerta.RESUELTA
    alerta.por_notificar = False
    db.commit()

    resultado = evaluar_reglas(db, AHORA + dt.timedelta(days=1))  # el puerto sigue abierto

    db.expire_all()
    assert resultado.reincidentes == 1
    assert (alerta.estado, alerta.por_notificar) == (EstadoAlerta.NUEVA, True)
