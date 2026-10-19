"""Exportación del tablero "Seguridad de IA" a Excel (.xlsx) y CSV, con los filtros aplicados.

Los datos vienen de Netskope (usuarios, apps, objetos): un valor que empiece
con "=", "+", "-" o "@" se escribe siempre como texto, para que Excel no lo
interprete como fórmula.
"""

import csv
import datetime as dt
import enum
import io
from collections.abc import Iterator

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alertas.models import Alerta, AlertaEvento, ReglaAlerta
from app.alertas.tablero import FiltrosIA, actividad, alertas_filtradas, cobertura, tablero

ARGENTINA = dt.timezone(dt.timedelta(hours=-3), "ART")  # sin horario de verano
MAX_FILAS = 200_000  # por hoja / CSV


class TablaCSV(str, enum.Enum):
    ALERTAS = "alertas"
    EVENTOS = "eventos"
    ACTIVIDAD = "actividad"


def _valor(v: object) -> object:
    if isinstance(v, dt.datetime):
        return v.astimezone(ARGENTINA).replace(tzinfo=None)
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{k}: {n}" for k, n in v.items())
    return v


def _peligroso(v: object) -> bool:
    return isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r")


# --- tablas ---

ENCABEZADOS = {
    TablaCSV.ALERTAS: [
        "Regla", "Severidad", "Estado", "App", "Usuario o equipo", "Equipos", "Eventos", "Actividades",
        "Primera vez", "Última vez", "Atendida", "Cerrada", "Caso", "Nota",
    ],
    TablaCSV.EVENTOS: ["Fecha", "Regla", "Severidad", "App", "Usuario", "Actividad", "Sitio", "Objeto", "Equipo"],
    TablaCSV.ACTIVIDAD: ["Día (UTC)", "Regla", "Modo", "Severidad", "App", "Usuario", "Actividad", "Eventos"],
}


def _alertas(db: Session, f: FiltrosIA) -> Iterator[list]:
    filas = db.scalars(
        select(Alerta)
        .join(ReglaAlerta, Alerta.regla_id == ReglaAlerta.id)
        .where(*alertas_filtradas(f))
        .order_by(Alerta.ultima_vez.desc())
        .limit(MAX_FILAS)
    )
    for a in filas:
        caso = (a.caso.jira_issue_key or a.caso.nombre_proyecto) if a.caso else None
        yield [
            a.regla.nombre, a.severidad, a.estado, a.app, a.usuario, a.equipos, a.cantidad_eventos, a.actividades,
            a.primera_vez, a.ultima_vez, a.atendida_at, a.cerrada_at, caso, a.nota,
        ]


def _eventos(db: Session, f: FiltrosIA) -> Iterator[list]:
    filas = db.execute(
        select(AlertaEvento, Alerta, ReglaAlerta.nombre)
        .join(Alerta, AlertaEvento.alerta_id == Alerta.id)
        .join(ReglaAlerta, Alerta.regla_id == ReglaAlerta.id)
        .where(*alertas_filtradas(f), AlertaEvento.fecha >= f.inicio, AlertaEvento.fecha < f.fin)
        .order_by(AlertaEvento.fecha.desc())
        .limit(MAX_FILAS)
    )
    for evento, alerta, regla in filas:
        yield [
            evento.fecha, regla, alerta.severidad, alerta.app, alerta.usuario, evento.actividad, evento.sitio,
            evento.objeto, evento.datos.get("hostname"),
        ]


def _actividad(db: Session, f: FiltrosIA) -> Iterator[list]:
    act = actividad(f)
    filas = db.execute(
        select(act.c.dia, act.c.regla, act.c.modo, act.c.severidad, act.c.app, act.c.usuario, act.c.actividad, act.c.eventos)
        .order_by(act.c.dia.desc(), act.c.regla, act.c.eventos.desc())
        .limit(MAX_FILAS)
    )
    for fila in filas:
        yield list(fila)


FILAS = {TablaCSV.ALERTAS: _alertas, TablaCSV.EVENTOS: _eventos, TablaCSV.ACTIVIDAD: _actividad}


# --- Excel ---


def _hoja(wb: Workbook, titulo: str, encabezados: list[str], filas: Iterator[list], anchos: dict[int, int] | None = None) -> None:
    ws = wb.create_sheet(titulo)
    for i, ancho in (anchos or {}).items():
        ws.column_dimensions[chr(ord("A") + i)].width = ancho
    ws.freeze_panes = "A2"
    negrita = []
    for texto in encabezados:
        celda = WriteOnlyCell(ws, texto)
        celda.font = Font(bold=True)
        negrita.append(celda)
    ws.append(negrita)
    for fila in filas:
        celdas = []
        for v in fila:
            celda = WriteOnlyCell(ws, _valor(v))
            if _peligroso(celda.value):
                celda.data_type = "s"
            elif isinstance(celda.value, dt.datetime):
                celda.number_format = "dd/mm/yyyy hh:mm"
            elif isinstance(celda.value, dt.date):
                celda.number_format = "dd/mm/yyyy"
            celdas.append(celda)
        ws.append(celdas)


def exportar_xlsx(db: Session, f: FiltrosIA) -> bytes:
    datos = tablero(db, f)
    ind = datos.indicadores
    resumen = [
        ["Período", f"{f.desde:%d/%m/%Y} al {f.hasta:%d/%m/%Y}"],
        ["Regla", db.scalar(select(ReglaAlerta.nombre).where(ReglaAlerta.id == f.regla_id)) if f.regla_id else "Todas"],
        ["Severidad", f.severidad.value if f.severidad else "Todas"],
        ["Usuarios", f.poblacion.value if f.poblacion else "Todos"],
        [],
        ["Alertas abiertas", ind.alertas_abiertas],
        ["Críticas y altas abiertas", ind.criticas_altas_abiertas],
        ["Eventos de IA", ind.eventos],
        ["Usuarios con actividad de IA", ind.usuarios_con_actividad],
        ["Externos con actividad de IA", ind.externos_con_actividad],
        ["Apps de IA detectadas", ind.apps_detectadas],
        ["Equipos con actividad de IA", ind.equipos_con_actividad],
        ["Equipos fuera de Tenable", ind.equipos_fuera_de_tenable],
        ["Tiempo medio de atención (horas)", ind.horas_medias_atencion],
        ["Tiempo medio de cierre (horas)", ind.horas_medias_cierre],
        [],
        ["Alertas por estado", ""],
        *[[estado, cantidad] for estado, cantidad in datos.alertas_por_estado.items()],
        [],
        ["Top apps de IA (usuarios)", ""],
        *[[a.nombre, a.usuarios] for a in datos.top_apps],
        [],
        ["Generado", dt.datetime.now(dt.UTC)],
    ]

    _, equipos = cobertura(db, f)
    filas_equipos = []
    for nombre, equipo in equipos.items():
        if equipo is None:
            estado = "Fuera de Tenable"
        elif not equipo.con_inventario:
            estado = "En Tenable sin inventario"
        else:
            estado = "Inventariado con agente" if equipo.tiene_agente else "Inventariado por escaneo"
        filas_equipos.append([
            nombre, estado, equipo.sistema_operativo if equipo else None, equipo.software_ia if equipo else None,
            [f"{p['puerto']} {p['servicio']}" for p in equipo.puertos_ia] if equipo else None,
            equipo.visto_at if equipo else None,
        ])

    wb = Workbook(write_only=True)
    _hoja(wb, "Resumen", ["Indicador", "Valor"], iter(resumen), {0: 36, 1: 28})
    _hoja(wb, "Alertas", ENCABEZADOS[TablaCSV.ALERTAS], _alertas(db, f), {0: 34, 3: 28, 4: 34, 8: 17, 9: 17})
    _hoja(wb, "Eventos", ENCABEZADOS[TablaCSV.EVENTOS], _eventos(db, f), {0: 17, 1: 34, 3: 28, 4: 34})
    _hoja(wb, "Actividad diaria", ENCABEZADOS[TablaCSV.ACTIVIDAD], _actividad(db, f), {1: 34, 4: 28, 5: 34})
    _hoja(
        wb, "Equipos", ["Equipo", "Cobertura de Tenable", "Sistema operativo", "Software de IA", "Puertos de IA", "Visto por Tenable"],
        iter(filas_equipos), {0: 20, 1: 26, 2: 30, 3: 30},
    )
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


# --- CSV ---


def exportar_csv(db: Session, f: FiltrosIA, tabla: TablaCSV) -> bytes:
    """Separado por ";" y con BOM, como lo abre Excel en español."""
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(ENCABEZADOS[tabla])
    for fila in FILAS[tabla](db, f):
        valores = []
        for v in fila:
            v = _valor(v)
            if isinstance(v, dt.datetime):
                v = v.strftime("%d/%m/%Y %H:%M")
            elif isinstance(v, dt.date):
                v = v.strftime("%d/%m/%Y")
            valores.append(f"'{v}" if _peligroso(v) else v)
        escritor.writerow(valores)
    return ("﻿" + salida.getvalue()).encode("utf-8")
