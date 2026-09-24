from datetime import date

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.casos.models import Caso, CasoTipo
from app.documents.models import CasoDocumento
from app.metricas.schemas import (
    Analisis,
    MetricasOut,
    Modelados,
    ModeladoCaso,
    NombreCantidad,
    Pentesting,
    PeriodoCantidad,
    ProyectosIngresados,
)
from app.pentesting.models import HerramientaPentest, PentestResultado, Severidad
from app.threat_model.scoring import SEMAFORO_SIN_EVALUAR
from app.threat_model.service import get_caso_score


def _casos_filters(desde: date | None, hasta: date | None, tipo: CasoTipo | None) -> list:
    filters = []
    if desde is not None:
        filters.append(cast(Caso.created_at, Date) >= desde)
    if hasta is not None:
        filters.append(cast(Caso.created_at, Date) <= hasta)
    if tipo is not None:
        filters.append(Caso.tipo == tipo)
    return filters


def _proyectos_ingresados(db: Session, filters: list) -> ProyectosIngresados:
    por_tipo_rows = db.execute(select(Caso.tipo, func.count()).where(*filters).group_by(Caso.tipo)).all()
    por_tipo = {t.value: 0 for t in CasoTipo}
    por_tipo.update({tipo.value: cantidad for tipo, cantidad in por_tipo_rows})

    mes = func.to_char(Caso.created_at, "YYYY-MM")
    por_mes_rows = db.execute(select(mes, func.count()).where(*filters).group_by(mes).order_by(mes)).all()

    return ProyectosIngresados(
        total=sum(por_tipo.values()),
        por_tipo=por_tipo,
        por_mes=[PeriodoCantidad(periodo=p, cantidad=c) for p, c in por_mes_rows],
    )


def _analisis(db: Session, filters: list) -> Analisis:
    base = select(CasoDocumento.caso_id, Caso.tipo).join(Caso, CasoDocumento.caso_id == Caso.id).where(*filters)
    rows = db.execute(base).all()

    casos_por_tipo: dict[str, set] = {t.value: set() for t in CasoTipo}
    for caso_id, tipo in rows:
        casos_por_tipo[tipo.value].add(caso_id)

    return Analisis(
        casos_analizados=sum(len(ids) for ids in casos_por_tipo.values()),
        documentos_analizados=len(rows),
        por_tipo={tipo: len(ids) for tipo, ids in casos_por_tipo.items()},
    )


def _modelados(db: Session, filters: list) -> Modelados:
    casos = db.scalars(select(Caso).where(*filters).order_by(Caso.created_at.desc())).all()

    modelados: list[ModeladoCaso] = []
    for caso in casos:
        g = get_caso_score(db, caso).global_score
        if g.semaforo == SEMAFORO_SIN_EVALUAR:
            continue  # sin ninguna pregunta respondida: el modelado todavía no se realizó
        modelados.append(
            ModeladoCaso(
                caso_id=caso.id,
                nombre_proyecto=caso.nombre_proyecto,
                empresa_responsable=caso.empresa_responsable,
                tipo=caso.tipo.value,
                compliance_pct=g.compliance_pct,
                residual_pct=g.residual_pct,
                completitud_pct=g.completitud_pct,
                brechas_criticas=g.brechas_criticas,
                semaforo=g.semaforo,
            )
        )

    por_semaforo = {s: 0 for s in ("solido", "moderado", "vulnerable", "critico")}
    for m in modelados:
        por_semaforo[m.semaforo] += 1

    n = len(modelados)
    return Modelados(
        cantidad=n,
        promedio_compliance_pct=sum(m.compliance_pct for m in modelados) / n if n else None,
        promedio_residual_pct=sum(m.residual_pct for m in modelados) / n if n else None,
        por_semaforo=por_semaforo,
        casos=modelados,
    )


def _pentesting(
    db: Session, desde: date | None, hasta: date | None, tipo: CasoTipo | None
) -> Pentesting:
    filters = []
    if desde is not None:
        filters.append(PentestResultado.fecha >= desde)
    if hasta is not None:
        filters.append(PentestResultado.fecha <= hasta)
    if tipo is not None:
        filters.append(Caso.tipo == tipo)

    def base(*columns):
        return select(*columns).select_from(PentestResultado).join(
            Caso, PentestResultado.caso_id == Caso.id
        ).where(*filters)

    total = db.scalar(base(func.count(PentestResultado.id))) or 0
    casos_con_pentest = db.scalar(base(func.count(func.distinct(PentestResultado.caso_id)))) or 0

    por_herramienta_rows = db.execute(
        base(HerramientaPentest.nombre, func.count(PentestResultado.id))
        .join(HerramientaPentest, PentestResultado.herramienta_id == HerramientaPentest.id)
        .group_by(HerramientaPentest.nombre)
        .order_by(func.count(PentestResultado.id).desc(), HerramientaPentest.nombre)
    ).all()

    por_severidad = {s.value: 0 for s in Severidad}
    for severidad, cantidad in db.execute(
        base(PentestResultado.severidad, func.count(PentestResultado.id)).group_by(PentestResultado.severidad)
    ):
        por_severidad[severidad.value] = cantidad

    return Pentesting(
        total=total,
        casos_con_pentest=casos_con_pentest,
        por_herramienta=[NombreCantidad(nombre=n, cantidad=c) for n, c in por_herramienta_rows],
        por_severidad=por_severidad,
    )


def get_metricas(
    db: Session, desde: date | None = None, hasta: date | None = None, tipo: CasoTipo | None = None
) -> MetricasOut:
    filters = _casos_filters(desde, hasta, tipo)
    return MetricasOut(
        proyectos_ingresados=_proyectos_ingresados(db, filters),
        analisis=_analisis(db, filters),
        modelados=_modelados(db, filters),
        pentesting=_pentesting(db, desde, hasta, tipo),
    )
