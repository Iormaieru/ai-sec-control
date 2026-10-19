"""Netskope -> alertas.

Para cada regla activa se consultan los eventos de la ventana
[consultada_hasta - margen, ahora - demora] y se agrupan en alertas por
regla + app + usuario. La demora cubre la ingesta de Netskope (los eventos
aparecen minutos después) y el margen re-consulta un tramo para no perder
eventos rezagados; los repetidos no se cuentan dos veces.

- Alerta nueva: estado "nueva", pendiente de aviso.
- Alerta resuelta que recibe eventos: vuelve a "nueva" y se vuelve a avisar.
- Alerta descartada (falso positivo): sólo acumula eventos.
"""

import datetime as dt
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.alertas.models import Alerta, AlertaEvento, EstadoAlerta, FuenteRegla, MetricaIA, ModoRegla, ReglaAlerta
from app.alertas.netskope import DemasiadosEventos, EventoNetskope, NetskopeClient, NetskopeError
from app.core.config import Settings

logger = logging.getLogger(__name__)

MARGEN = dt.timedelta(minutes=30)
VENTANA_MINIMA = dt.timedelta(minutes=5)
RETENCION_EVENTOS = dt.timedelta(days=90)
RETENCION_METRICAS = dt.timedelta(days=400)


@dataclass
class ResultadoAlertas:
    eventos: int = 0
    nuevas: int = 0
    reincidentes: int = 0
    actualizadas: int = 0
    eventos_metricas: int = 0
    errores: list[str] = field(default_factory=list)


def _host(nombre: object) -> str | None:
    """"BMN1234.macro.local" -> "bmn1234" (igual que en el inventario de Tenable)."""
    if not nombre:
        return None
    return str(nombre).strip().lower().split(".")[0] or None


def ventana(regla: ReglaAlerta, ahora: dt.datetime, settings: Settings) -> tuple[dt.datetime, dt.datetime]:
    hasta = ahora - dt.timedelta(minutes=settings.netskope_demora_minutos)
    if regla.consultada_hasta is None:
        desde = hasta - dt.timedelta(days=settings.netskope_retrospectiva_dias)
    elif regla.modo == ModoRegla.METRICA:
        # Sin margen: las métricas sólo guardan totales y no podrían descartar repetidos.
        desde = regla.consultada_hasta
    else:
        desde = regla.consultada_hasta - MARGEN
    return desde, hasta


def _agregar_metricas(db: Session, regla: ReglaAlerta, eventos: list[EventoNetskope], resultado: ResultadoAlertas) -> None:
    """Suma los eventos a los totales diarios por app, usuario y actividad."""
    totales = Counter((e.fecha.date(), e.app, e.usuario, e.actividad or "") for e in eventos)
    for (dia, app, usuario, actividad), cantidad in totales.items():
        stmt = insert(MetricaIA).values(
            id=uuid.uuid4(), regla_id=regla.id, dia=dia, app=app, usuario=usuario, actividad=actividad, eventos=cantidad
        )
        db.execute(
            stmt.on_conflict_do_update(
                constraint="uq_metrica_ia", set_={"eventos": MetricaIA.eventos + stmt.excluded.eventos}
            )
        )
    resultado.eventos_metricas += len(eventos)


def consultar(client: NetskopeClient, consulta: str, desde: dt.datetime, hasta: dt.datetime) -> list[EventoNetskope]:
    """Eventos de la ventana completa: si supera el tope por consulta, se
    parte en mitades (recursivamente) hasta que cada parte entre entera."""
    try:
        return client.eventos(consulta, desde, hasta)
    except DemasiadosEventos:
        if hasta - desde <= VENTANA_MINIMA:
            raise  # demasiado volumen incluso en 5 minutos: la regla es muy amplia
        medio = desde + (hasta - desde) / 2
        return consultar(client, consulta, desde, medio) + consultar(client, consulta, medio, hasta)


def _aplicar(db: Session, regla: ReglaAlerta, eventos: list[EventoNetskope], resultado: ResultadoAlertas) -> None:
    ya_vistos = set(
        db.scalars(
            select(AlertaEvento.evento_id)
            .join(Alerta, AlertaEvento.alerta_id == Alerta.id)
            .where(Alerta.regla_id == regla.id, AlertaEvento.evento_id.in_([e.evento_id for e in eventos]))
        )
    ) if eventos else set()
    alertas: dict[tuple[str, str], Alerta] = {}
    tocadas: set[tuple[str, str]] = set()

    for evento in sorted(eventos, key=lambda e: e.fecha):
        if evento.evento_id in ya_vistos:
            continue
        ya_vistos.add(evento.evento_id)
        clave = (evento.app, evento.usuario)
        alerta = alertas.get(clave) or db.scalar(
            select(Alerta).where(Alerta.regla_id == regla.id, Alerta.app == evento.app, Alerta.usuario == evento.usuario)
        )
        if alerta is None:
            alerta = Alerta(
                regla_id=regla.id,
                app=evento.app,
                usuario=evento.usuario,
                estado=EstadoAlerta.NUEVA,
                severidad=regla.severidad,
                primera_vez=evento.fecha,
                ultima_vez=evento.fecha,
                cantidad_eventos=0,
                actividades={},
                equipos=[],
                por_notificar=True,
            )
            db.add(alerta)
            db.flush()
            resultado.nuevas += 1
        elif clave not in tocadas:
            if alerta.estado == EstadoAlerta.RESUELTA:
                alerta.estado = EstadoAlerta.NUEVA
                alerta.por_notificar = True
                alerta.cerrada_at = None
                resultado.reincidentes += 1
            else:
                resultado.actualizadas += 1
        alertas[clave] = alerta
        tocadas.add(clave)

        alerta.cantidad_eventos += 1
        alerta.primera_vez = min(alerta.primera_vez, evento.fecha)
        alerta.ultima_vez = max(alerta.ultima_vez, evento.fecha)
        equipo = _host(evento.datos.get("hostname"))
        if equipo and equipo not in alerta.equipos:
            alerta.equipos = [*alerta.equipos, equipo]  # JSONB: se reasigna
        if evento.actividad:
            # JSONB: se reasigna para que SQLAlchemy detecte el cambio.
            alerta.actividades = {**alerta.actividades, evento.actividad: alerta.actividades.get(evento.actividad, 0) + 1}
        db.add(
            AlertaEvento(
                alerta_id=alerta.id,
                evento_id=evento.evento_id,
                fecha=evento.fecha,
                actividad=evento.actividad,
                sitio=evento.sitio,
                objeto=evento.objeto,
                datos=evento.datos,
            )
        )
        resultado.eventos += 1


def procesar(db: Session, client: NetskopeClient, settings: Settings, ahora: dt.datetime | None = None) -> ResultadoAlertas:
    ahora = ahora or dt.datetime.now(dt.UTC)
    resultado = ResultadoAlertas()
    reglas = db.scalars(
        select(ReglaAlerta)
        .where(ReglaAlerta.activa.is_(True), ReglaAlerta.fuente == FuenteRegla.NETSKOPE)
        .order_by(ReglaAlerta.nombre)
    ).all()
    for regla in reglas:
        desde, hasta = ventana(regla, ahora, settings)
        if desde >= hasta:
            continue
        try:
            eventos = consultar(client, regla.consulta, desde, hasta)
        except NetskopeError as exc:
            # El cursor no avanza: la próxima vuelta vuelve a consultar esta ventana.
            regla.ultimo_error = str(exc)[:1000]
            resultado.errores.append(f"Regla «{regla.nombre}»: {exc}")
            db.commit()
            continue
        if regla.modo == ModoRegla.METRICA:
            _agregar_metricas(db, regla, eventos, resultado)
        else:
            _aplicar(db, regla, eventos, resultado)
        regla.consultada_hasta = hasta
        regla.ultimo_error = None
        db.commit()

    db.execute(delete(AlertaEvento).where(AlertaEvento.fecha < ahora - RETENCION_EVENTOS))
    db.execute(delete(MetricaIA).where(MetricaIA.dia < (ahora - RETENCION_METRICAS).date()))
    db.commit()
    return resultado
