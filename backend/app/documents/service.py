import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casos.models import Caso
from app.catalog.models import Dominio, Pregunta
from app.documents.models import CasoDocumento
from app.documents.parsing import extract_text
from app.documents.schemas import DocumentoAnalizadoOut
from app.llm.factory import get_llm_provider
from app.llm.schemas import CatalogQuestionSummary
from app.threat_model.models import CasoPregunta, CasoRespuesta
from app.threat_model.service import get_caso_pregunta_out


def _catalog_summaries(db: Session) -> list[CatalogQuestionSummary]:
    rows = db.execute(select(Pregunta, Dominio).join(Dominio, Pregunta.dominio_id == Dominio.id)).all()
    return [
        CatalogQuestionSummary(
            pregunta_id=str(pregunta.id),
            dominio_codigo=dominio.codigo,
            numero=pregunta.numero,
            texto_es=pregunta.texto_es,
            tier=pregunta.tier.value,
        )
        for pregunta, dominio in rows
    ]


def analyze_document(
    db: Session, caso: Caso, *, filename: str, content: bytes, content_type: str
) -> DocumentoAnalizadoOut:
    """Extrae el texto del documento, se lo pasa al LLMProvider configurado
    junto con el catálogo completo, y con lo que recomienda: crea
    CasoPregunta para las preguntas que todavía no estaban en alcance y
    guarda las instrucciones de respuesta ES/EN en su CasoRespuesta."""
    texto = extract_text(content, content_type)

    resultado = get_llm_provider().analyze_document(texto, _catalog_summaries(db))

    documento = CasoDocumento(
        caso_id=caso.id,
        nombre_archivo=filename,
        content_type=content_type,
        texto_extraido=texto,
        clasificacion=resultado.clasificacion,
    )
    db.add(documento)

    existentes = {
        cp.pregunta_id: cp
        for cp in db.scalars(select(CasoPregunta).where(CasoPregunta.caso_id == caso.id))
    }

    pregunta_ids_recomendadas: list[uuid.UUID] = []
    for recomendada in resultado.preguntas_recomendadas:
        pregunta_id = uuid.UUID(recomendada.pregunta_id)
        pregunta_ids_recomendadas.append(pregunta_id)

        caso_pregunta = existentes.get(pregunta_id)
        if caso_pregunta is None:
            caso_pregunta = CasoPregunta(caso_id=caso.id, pregunta_id=pregunta_id)
            db.add(caso_pregunta)
            db.flush()  # asigna caso_pregunta.id para el FK de la respuesta
            respuesta = CasoRespuesta(caso_pregunta_id=caso_pregunta.id)
            db.add(respuesta)
            existentes[pregunta_id] = caso_pregunta
        else:
            respuesta = caso_pregunta.respuesta

        respuesta.instrucciones_respuesta_es = recomendada.instrucciones_es
        respuesta.instrucciones_respuesta_en = recomendada.instrucciones_en

    db.commit()

    preguntas_out = [get_caso_pregunta_out(db, caso.id, pid) for pid in pregunta_ids_recomendadas]

    return DocumentoAnalizadoOut(
        id=documento.id,
        nombre_archivo=documento.nombre_archivo,
        clasificacion=documento.clasificacion,
        preguntas_recomendadas=preguntas_out,
    )
