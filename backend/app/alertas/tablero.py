"""Tablero "Seguridad de IA": agregaciones sobre alertas, eventos, métricas e
inventario de Tenable.

La "actividad" une las dos fuentes de eventos de Netskope: los eventos de las
reglas de alerta (alerta_eventos, uno por fila) y los totales diarios de las
reglas en modo métrica (metricas_ia). Quedan en la misma forma (día, regla,
app, usuario, actividad, eventos) y todo lo que cuenta eventos o usuarios sale
de ahí. Por regla los conteos son exactos; entre reglas un mismo evento puede
contar dos veces si cumple dos consultas (como pasa en Skope IT).

Los días son en UTC, igual que los guarda el worker en metricas_ia.
"""

import datetime as dt
import enum
import uuid
from dataclasses import dataclass

from sqlalchemy import Date, String, cast, distinct, func, literal_column, or_, select, union_all
from sqlalchemy.orm import Session

from app.alertas.models import (
    Alerta,
    AlertaEvento,
    EquipoTenable,
    EstadoAlerta,
    FuenteRegla,
    MetricaIA,
    ModoRegla,
    ReglaAlerta,
    SeveridadAlerta,
    SincronizacionTenable,
)
from app.alertas.schemas_tablero import (
    CoberturaTenable,
    DiaCantidad,
    DiaPorActividad,
    DiaPorSeveridad,
    IndicadoresIA,
    NombreCantidad,
    PoblacionOut,
    TableroIAOut,
    TopApp,
    TopUsuario,
)

DOMINIO_EXTERNOS = "bmexternos"  # cuentas de terceros: usuario@bmexternos.com.ar
ACTIVIDADES_SENSIBLES = ["Upload", "Post", "CallToolRequest"]
DIAS_POR_DEFECTO = 30
TOP = 10


class Poblacion(str, enum.Enum):
    INTERNOS = "internos"
    EXTERNOS = "externos"


@dataclass
class FiltrosIA:
    desde: dt.date
    hasta: dt.date
    regla_id: uuid.UUID | None = None
    severidad: SeveridadAlerta | None = None
    poblacion: Poblacion | None = None

    @classmethod
    def armar(cls, desde: dt.date | None = None, hasta: dt.date | None = None, **resto) -> "FiltrosIA":
        hasta = hasta or dt.datetime.now(dt.UTC).date()
        desde = desde or hasta - dt.timedelta(days=DIAS_POR_DEFECTO - 1)
        return cls(desde=min(desde, hasta), hasta=hasta, **resto)

    @property
    def inicio(self) -> dt.datetime:
        return dt.datetime.combine(self.desde, dt.time(), dt.UTC)

    @property
    def fin(self) -> dt.datetime:  # exclusivo
        return dt.datetime.combine(self.hasta + dt.timedelta(days=1), dt.time(), dt.UTC)

    def dias(self) -> list[dt.date]:
        return [self.desde + dt.timedelta(days=n) for n in range((self.hasta - self.desde).days + 1)]


def es_externo(usuario):
    # Patrón constante en línea (no como parámetro) para poder agrupar por esta expresión.
    return usuario.ilike(literal_column(f"'%{DOMINIO_EXTERNOS}%'"))


def _poblacion(columna, poblacion: Poblacion | None) -> list:
    if poblacion == Poblacion.EXTERNOS:
        return [es_externo(columna)]
    if poblacion == Poblacion.INTERNOS:
        return [~es_externo(columna)]
    return []


def actividad(f: FiltrosIA):
    """Subconsulta (dia, regla_id, regla, severidad, modo, app, usuario, actividad, eventos) con los filtros."""
    dia_evento = cast(func.timezone("UTC", AlertaEvento.fecha), Date)
    eventos = (
        select(
            dia_evento.label("dia"),
            Alerta.regla_id,
            Alerta.app,
            Alerta.usuario,
            func.coalesce(AlertaEvento.actividad, "").label("actividad"),
            func.count().label("eventos"),
        )
        .join(Alerta, AlertaEvento.alerta_id == Alerta.id)
        .where(AlertaEvento.fecha >= f.inicio, AlertaEvento.fecha < f.fin)
        .group_by(dia_evento, Alerta.regla_id, Alerta.app, Alerta.usuario, AlertaEvento.actividad)
    )
    metricas = select(
        MetricaIA.dia,
        MetricaIA.regla_id,
        MetricaIA.app,
        MetricaIA.usuario,
        cast(MetricaIA.actividad, String).label("actividad"),
        MetricaIA.eventos,
    ).where(MetricaIA.dia >= f.desde, MetricaIA.dia <= f.hasta)
    union = union_all(eventos, metricas).subquery()

    filtros = _poblacion(union.c.usuario, f.poblacion)
    if f.regla_id:
        filtros.append(union.c.regla_id == f.regla_id)
    if f.severidad:
        filtros.append(ReglaAlerta.severidad == f.severidad)
    return (
        select(
            union.c.dia,
            union.c.regla_id,
            ReglaAlerta.nombre.label("regla"),
            ReglaAlerta.severidad,
            ReglaAlerta.modo,
            union.c.app,
            union.c.usuario,
            union.c.actividad,
            union.c.eventos,
        )
        .join(ReglaAlerta, ReglaAlerta.id == union.c.regla_id)
        .where(*filtros)
        .subquery()
    )


def alertas_filtradas(f: FiltrosIA):
    """Condiciones de las alertas con actividad dentro del rango (y los demás filtros).

    El filtro de internos/externos es sobre usuarios: deja afuera las alertas
    de reglas de Tenable, que son por equipo."""
    condiciones = [Alerta.ultima_vez >= f.inicio, Alerta.primera_vez < f.fin]
    if f.regla_id:
        condiciones.append(Alerta.regla_id == f.regla_id)
    if f.severidad:
        condiciones.append(Alerta.severidad == f.severidad)
    if f.poblacion:
        condiciones += [ReglaAlerta.fuente == FuenteRegla.NETSKOPE, *_poblacion(Alerta.usuario, f.poblacion)]
    return condiciones


def _alertas(f: FiltrosIA):
    return select(Alerta).join(ReglaAlerta, Alerta.regla_id == ReglaAlerta.id).where(*alertas_filtradas(f))


ABIERTAS = [EstadoAlerta.NUEVA, EstadoAlerta.EN_REVISION]


def _horas_medias(db: Session, f: FiltrosIA, columna) -> float | None:
    segundos = db.scalar(
        select(func.avg(func.extract("epoch", columna - Alerta.created_at)))
        .join(ReglaAlerta, Alerta.regla_id == ReglaAlerta.id)
        .where(*alertas_filtradas(f), columna.is_not(None))
    )
    return round(float(segundos) / 3600, 1) if segundos is not None else None


def cobertura(db: Session, f: FiltrosIA) -> tuple[CoberturaTenable, dict[str, EquipoTenable | None]]:
    """Equipos con actividad de IA (los de las alertas de Netskope en el rango)
    y si Tenable los inventaría, por hostname o nombre NetBIOS."""
    filas = db.scalars(
        _alertas(f).where(ReglaAlerta.fuente == FuenteRegla.NETSKOPE).with_only_columns(Alerta.equipos)
    ).all()
    nombres = sorted({e for equipos in filas for e in equipos})
    encontrados = db.scalars(
        select(EquipoTenable).where(or_(EquipoTenable.hostname.in_(nombres), EquipoTenable.netbios.in_(nombres)))
    ).all() if nombres else []
    por_nombre: dict[str, EquipoTenable] = {}
    for equipo in encontrados:
        for nombre in (equipo.netbios, equipo.hostname):  # el hostname gana si coinciden los dos
            if nombre:
                por_nombre[nombre] = equipo
    equipos = {n: por_nombre.get(n) for n in nombres}

    resultado = CoberturaTenable()
    for equipo in equipos.values():
        if equipo is None:
            resultado.fuera_de_tenable += 1
        elif not equipo.con_inventario:
            resultado.sin_inventario += 1
        elif equipo.tiene_agente:
            resultado.con_agente += 1
        else:
            resultado.por_escaneo += 1
    return resultado, equipos


def _por_dia(db: Session, f: FiltrosIA, act) -> list[DiaPorSeveridad]:
    filas = db.execute(select(act.c.dia, act.c.severidad, func.sum(act.c.eventos)).group_by(act.c.dia, act.c.severidad))
    tabla: dict[dt.date, dict[str, int]] = {}
    for dia, severidad, eventos in filas:
        tabla.setdefault(dia, {})[severidad.value] = int(eventos)
    return [DiaPorSeveridad(dia=d, **tabla.get(d, {})) for d in f.dias()]


def _sensibles(db: Session, f: FiltrosIA, act) -> list[DiaPorActividad]:
    filas = db.execute(
        select(act.c.dia, act.c.actividad, func.sum(act.c.eventos))
        .where(act.c.actividad.in_(ACTIVIDADES_SENSIBLES))
        .group_by(act.c.dia, act.c.actividad)
    )
    tabla: dict[dt.date, dict[str, int]] = {}
    for dia, actividad_, eventos in filas:
        tabla.setdefault(dia, {})[actividad_] = int(eventos)
    return [DiaPorActividad(dia=d, actividades={a: tabla.get(d, {}).get(a, 0) for a in ACTIVIDADES_SENSIBLES}) for d in f.dias()]


def _nuevas_por_dia(db: Session, f: FiltrosIA) -> list[DiaCantidad]:
    dia = cast(func.timezone("UTC", Alerta.primera_vez), Date)
    filas = dict(
        db.execute(
            select(dia, func.count())
            .join(ReglaAlerta, Alerta.regla_id == ReglaAlerta.id)
            .where(*alertas_filtradas(f), Alerta.primera_vez >= f.inicio)
            .group_by(dia)
        ).all()
    )
    return [DiaCantidad(dia=d, cantidad=filas.get(d, 0)) for d in f.dias()]


def tablero(db: Session, f: FiltrosIA) -> TableroIAOut:
    act = actividad(f)
    alertas = (
        select(Alerta.estado, Alerta.severidad, func.count())
        .join(ReglaAlerta, Alerta.regla_id == ReglaAlerta.id)
        .where(*alertas_filtradas(f))
        .group_by(Alerta.estado, Alerta.severidad)
    )
    por_estado = {e.value: 0 for e in EstadoAlerta}
    abiertas = criticas_altas = 0
    for estado, severidad, cantidad in db.execute(alertas):
        por_estado[estado.value] += cantidad
        if estado in ABIERTAS:
            abiertas += cantidad
            if severidad in (SeveridadAlerta.CRITICA, SeveridadAlerta.ALTA):
                criticas_altas += cantidad

    totales = db.execute(
        select(
            func.count(distinct(act.c.usuario)),
            func.count(distinct(act.c.app)),
            func.count(distinct(act.c.usuario)).filter(es_externo(act.c.usuario)),
            func.coalesce(func.sum(act.c.eventos), 0),
        )
    ).one()

    poblacion = {
        externo: (usuarios, int(eventos))
        for externo, usuarios, eventos in db.execute(
            select(es_externo(act.c.usuario), func.count(distinct(act.c.usuario)), func.sum(act.c.eventos)).group_by(
                es_externo(act.c.usuario)
            )
        )
    }

    top_apps = db.execute(
        select(act.c.app, func.count(distinct(act.c.usuario)).label("usuarios"), func.sum(act.c.eventos))
        .group_by(act.c.app)
        .order_by(func.count(distinct(act.c.usuario)).desc(), act.c.app)
        .limit(TOP)
    ).all()

    # Top de usuarios sólo con las reglas de alerta: las de métrica son uso
    # general de IA y taparían a los usuarios con actividad de riesgo.
    eventos_usuario = func.sum(act.c.eventos)
    top_usuarios = db.execute(
        select(act.c.usuario, eventos_usuario, func.count(distinct(act.c.regla_id)))
        .where(act.c.modo == ModoRegla.ALERTA)
        .group_by(act.c.usuario)
        .order_by(eventos_usuario.desc(), act.c.usuario)
        .limit(TOP)
    ).all()

    cobertura_, equipos = cobertura(db, f)
    software = db.execute(
        select(func.jsonb_array_elements_text(EquipoTenable.software_ia).label("software"), func.count())
        .group_by("software")
        .order_by(func.count().desc())
    ).all()
    tenable_al = db.scalar(
        select(func.max(SincronizacionTenable.finalizada_at)).where(SincronizacionTenable.ok.is_(True))
    )

    return TableroIAOut(
        desde=f.desde,
        hasta=f.hasta,
        indicadores=IndicadoresIA(
            alertas_abiertas=abiertas,
            criticas_altas_abiertas=criticas_altas,
            usuarios_con_actividad=totales[0],
            apps_detectadas=totales[1],
            externos_con_actividad=totales[2],
            eventos=int(totales[3]),
            equipos_con_actividad=len(equipos),
            equipos_fuera_de_tenable=cobertura_.fuera_de_tenable,
            horas_medias_atencion=_horas_medias(db, f, Alerta.atendida_at),
            horas_medias_cierre=_horas_medias(db, f, Alerta.cerrada_at),
        ),
        eventos_por_dia=_por_dia(db, f, act),
        alertas_nuevas_por_dia=_nuevas_por_dia(db, f),
        top_apps=[TopApp(nombre=a, usuarios=u, eventos=int(e)) for a, u, e in top_apps],
        top_usuarios=[TopUsuario(nombre=u, eventos=int(e), reglas=r) for u, e, r in top_usuarios],
        poblacion=[
            PoblacionOut(poblacion=Poblacion.INTERNOS, usuarios=poblacion.get(False, (0, 0))[0], eventos=poblacion.get(False, (0, 0))[1]),
            PoblacionOut(poblacion=Poblacion.EXTERNOS, usuarios=poblacion.get(True, (0, 0))[0], eventos=poblacion.get(True, (0, 0))[1]),
        ],
        alertas_por_estado=por_estado,
        actividades_sensibles=_sensibles(db, f, act),
        cobertura_tenable=cobertura_,
        software_tenable=[NombreCantidad(nombre=s, cantidad=c) for s, c in software],
        tenable_actualizado_at=tenable_al,
    )
