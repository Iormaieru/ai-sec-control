import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casos.models import Caso
from app.catalog.models import Dominio, Pregunta
from app.threat_model.models import CasoPregunta, CasoRespuesta
from app.threat_model.schemas import CasoPreguntaOut, CasoScoreOut, DomainScoreOut, GlobalScoreOut
from app.threat_model.scoring import (
    RespuestaInput,
    compute_estado,
    compute_maximo_aplicable,
    compute_pts_obtenidos,
    compute_riesgo_residual,
    domain_aggregate,
    global_score,
)


class DominioDesconocido(Exception):
    pass


def add_preguntas(
    db: Session,
    caso: Caso,
    *,
    pregunta_ids: list[uuid.UUID] | None = None,
    dominio_codigo: str | None = None,
) -> list[CasoPregunta]:
    """Pone preguntas 'en alcance' para el caso (por id o por dominio
    completo). Idempotente: preguntas ya seleccionadas se ignoran."""
    ids: set[uuid.UUID] = set(pregunta_ids or [])

    if dominio_codigo is not None:
        dominio = db.scalar(select(Dominio).where(Dominio.codigo == dominio_codigo))
        if dominio is None:
            raise DominioDesconocido(f"Dominio desconocido: {dominio_codigo}")
        ids |= {p.id for p in db.scalars(select(Pregunta).where(Pregunta.dominio_id == dominio.id))}

    existentes = {
        cp.pregunta_id for cp in db.scalars(select(CasoPregunta).where(CasoPregunta.caso_id == caso.id))
    }
    nuevas = ids - existentes

    creadas = []
    for pregunta_id in nuevas:
        caso_pregunta = CasoPregunta(caso_id=caso.id, pregunta_id=pregunta_id)
        db.add(caso_pregunta)
        db.flush()  # asigna caso_pregunta.id (UUID client-side) para el FK de abajo
        db.add(CasoRespuesta(caso_pregunta_id=caso_pregunta.id))
        creadas.append(caso_pregunta)

    db.commit()
    return creadas


def remove_preguntas_by_dominio(db: Session, caso: Caso, dominio_codigo: str) -> int:
    """Saca del alcance del caso todas las preguntas de un dominio —
    contraparte de add_preguntas(dominio_codigo=...). Borra también sus
    CasoRespuesta (cascade de la relación) — se pierden las respuestas ya
    cargadas para esas preguntas, la confirmación queda del lado del
    frontend antes de llamar a esto."""
    dominio = db.scalar(select(Dominio).where(Dominio.codigo == dominio_codigo))
    if dominio is None:
        raise DominioDesconocido(f"Dominio desconocido: {dominio_codigo}")

    caso_preguntas = list(
        db.scalars(
            select(CasoPregunta)
            .join(Pregunta, CasoPregunta.pregunta_id == Pregunta.id)
            .where(CasoPregunta.caso_id == caso.id, Pregunta.dominio_id == dominio.id)
        )
    )
    for caso_pregunta in caso_preguntas:
        db.delete(caso_pregunta)

    db.commit()
    return len(caso_preguntas)


def _rows_query(caso_id: uuid.UUID):
    return (
        select(CasoPregunta, CasoRespuesta, Pregunta, Dominio)
        .join(CasoRespuesta, CasoRespuesta.caso_pregunta_id == CasoPregunta.id)
        .join(Pregunta, CasoPregunta.pregunta_id == Pregunta.id)
        .join(Dominio, Pregunta.dominio_id == Dominio.id)
        .where(CasoPregunta.caso_id == caso_id)
        .order_by(Dominio.codigo, Pregunta.numero)
    )


def to_caso_pregunta_out(
    caso_pregunta: CasoPregunta, respuesta: CasoRespuesta, pregunta: Pregunta, dominio: Dominio
) -> CasoPreguntaOut:
    pts = compute_pts_obtenidos(respuesta.respuesta, pregunta.polaridad, pregunta.multiplicador)
    maxapl = compute_maximo_aplicable(respuesta.respuesta, pregunta.multiplicador)
    residual = compute_riesgo_residual(
        respuesta.respuesta, pregunta.polaridad, pregunta.multiplicador, respuesta.factor_mitigacion_pct
    )
    return CasoPreguntaOut(
        caso_pregunta_id=caso_pregunta.id,
        pregunta_id=pregunta.id,
        dominio_codigo=dominio.codigo,
        numero=pregunta.numero,
        texto_es=pregunta.texto_es,
        texto_en=pregunta.texto_en,
        tier=pregunta.tier,
        multiplicador=pregunta.multiplicador,
        respuesta=respuesta.respuesta,
        estado=compute_estado(respuesta.respuesta, pregunta.polaridad),
        pts_obtenidos=float(pts) if pts is not None else None,
        maximo_aplicable=float(maxapl),
        riesgo_residual=float(residual) if residual is not None else None,
        control_compensatorio=respuesta.control_compensatorio,
        factor_mitigacion_pct=respuesta.factor_mitigacion_pct,
        owner_responsable=respuesta.owner_responsable,
        accion_remediacion=respuesta.accion_remediacion,
        fecha_objetivo=respuesta.fecha_objetivo,
        evidencia_esperada=respuesta.evidencia_esperada,
        observaciones=respuesta.observaciones,
        instrucciones_respuesta_es=respuesta.instrucciones_respuesta_es,
        instrucciones_respuesta_en=respuesta.instrucciones_respuesta_en,
    )


def list_caso_preguntas(db: Session, caso: Caso) -> list[CasoPreguntaOut]:
    rows = db.execute(_rows_query(caso.id)).all()
    return [to_caso_pregunta_out(*row) for row in rows]


def get_caso_pregunta(db: Session, caso: Caso, pregunta_id: uuid.UUID) -> CasoPregunta | None:
    return db.scalar(
        select(CasoPregunta).where(CasoPregunta.caso_id == caso.id, CasoPregunta.pregunta_id == pregunta_id)
    )


def remove_pregunta(db: Session, caso_pregunta: CasoPregunta) -> None:
    """Saca una única pregunta del alcance del caso (borra también su
    CasoRespuesta por cascade) — contraparte puntual de
    remove_preguntas_by_dominio, para cuando el humano quiere sacar sólo
    una pregunta que no aplica en vez de todo el dominio."""
    db.delete(caso_pregunta)
    db.commit()


def upsert_respuesta(db: Session, caso_pregunta: CasoPregunta, payload: dict) -> CasoPreguntaOut:
    respuesta = caso_pregunta.respuesta
    for key, value in payload.items():
        setattr(respuesta, key, value)
    db.commit()

    row = db.execute(_rows_query(caso_pregunta.caso_id).where(Pregunta.id == caso_pregunta.pregunta_id)).one()
    return to_caso_pregunta_out(*row)


def get_caso_pregunta_out(db: Session, caso_id: uuid.UUID, pregunta_id: uuid.UUID) -> CasoPreguntaOut:
    row = db.execute(_rows_query(caso_id).where(Pregunta.id == pregunta_id)).one()
    return to_caso_pregunta_out(*row)


def get_caso_score(db: Session, caso: Caso) -> CasoScoreOut:
    """Score completo por dominio + global (GET /casos/{id}/score).

    Recorre los 8 dominios del catálogo siempre, no sólo los que el caso
    tocó: un dominio sin preguntas seleccionadas entra a domain_aggregate
    con una lista vacía y aporta 0% a ese dominio (ver test de
    independencia de subconjunto en T7) — así el global refleja que un
    dominio entero sin evaluar no puede contar como "cumplido".
    """
    dominios = list(db.scalars(select(Dominio).order_by(Dominio.codigo)))

    domain_scores = []
    domain_scores_out = []
    for dominio in dominios:
        rows = db.execute(
            select(CasoRespuesta, Pregunta)
            .join(CasoPregunta, CasoRespuesta.caso_pregunta_id == CasoPregunta.id)
            .join(Pregunta, CasoPregunta.pregunta_id == Pregunta.id)
            .where(CasoPregunta.caso_id == caso.id, Pregunta.dominio_id == dominio.id)
        ).all()

        respuestas = [
            RespuestaInput(cr.respuesta, pregunta.polaridad, pregunta.multiplicador, cr.factor_mitigacion_pct)
            for cr, pregunta in rows
        ]
        score = domain_aggregate(respuestas, dominio.peso)
        domain_scores.append(score)
        domain_scores_out.append(
            DomainScoreOut(
                dominio_codigo=dominio.codigo,
                dominio_nombre=dominio.nombre,
                peso=float(dominio.peso),
                total_preguntas=score.total_preguntas,
                respondidas=score.respondidas,
                na_total=score.na_total,
                pendientes=score.pendientes,
                cumple=score.cumple,
                brechas_criticas=score.brechas_criticas,
                compliance_pct=float(score.compliance_pct),
                residual_pct=float(score.residual_pct),
                contrib_cumplimiento=float(score.contrib_cumplimiento),
                contrib_residual=float(score.contrib_residual),
                gap_ponderado=float(score.gap_ponderado),
                semaforo=score.semaforo,
            )
        )

    total = global_score(domain_scores)
    return CasoScoreOut(
        dominios=domain_scores_out,
        global_score=GlobalScoreOut(
            compliance_pct=float(total.compliance_pct),
            residual_pct=float(total.residual_pct),
            completitud_pct=float(total.completitud_pct),
            brechas_criticas=total.brechas_criticas,
            semaforo=total.semaforo,
        ),
    )
