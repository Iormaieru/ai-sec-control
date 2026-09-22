import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casos.models import Caso
from app.catalog.models import Dominio, Pregunta
from app.threat_model.models import CasoPregunta, CasoRespuesta
from app.threat_model.schemas import CasoPreguntaOut
from app.threat_model.scoring import (
    compute_estado,
    compute_maximo_aplicable,
    compute_pts_obtenidos,
    compute_riesgo_residual,
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


def _rows_query(caso_id: uuid.UUID):
    return (
        select(CasoPregunta, CasoRespuesta, Pregunta, Dominio)
        .join(CasoRespuesta, CasoRespuesta.caso_pregunta_id == CasoPregunta.id)
        .join(Pregunta, CasoPregunta.pregunta_id == Pregunta.id)
        .join(Dominio, Pregunta.dominio_id == Dominio.id)
        .where(CasoPregunta.caso_id == caso_id)
        .order_by(Dominio.codigo, Pregunta.numero)
    )


def _to_out(caso_pregunta: CasoPregunta, respuesta: CasoRespuesta, pregunta: Pregunta, dominio: Dominio) -> CasoPreguntaOut:
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
    )


def list_caso_preguntas(db: Session, caso: Caso) -> list[CasoPreguntaOut]:
    rows = db.execute(_rows_query(caso.id)).all()
    return [_to_out(*row) for row in rows]


def get_caso_pregunta(db: Session, caso: Caso, pregunta_id: uuid.UUID) -> CasoPregunta | None:
    return db.scalar(
        select(CasoPregunta).where(CasoPregunta.caso_id == caso.id, CasoPregunta.pregunta_id == pregunta_id)
    )


def upsert_respuesta(db: Session, caso_pregunta: CasoPregunta, payload: dict) -> CasoPreguntaOut:
    respuesta = caso_pregunta.respuesta
    for key, value in payload.items():
        setattr(respuesta, key, value)
    db.commit()

    row = db.execute(_rows_query(caso_pregunta.caso_id).where(Pregunta.id == caso_pregunta.pregunta_id)).one()
    return _to_out(*row)
