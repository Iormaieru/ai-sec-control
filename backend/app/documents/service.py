import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casos.models import Caso
from app.catalog.models import Dominio, Pregunta
from app.documents.models import CasoDocumento
from app.documents.parsing import extract_document
from app.documents.schemas import DocumentoAnalizadoOut
from app.llm.factory import get_llm_provider
from app.llm.schemas import CatalogQuestionSummary, DocumentImage, RecommendedQuestion
from app.threat_model.models import CasoPregunta, CasoRespuesta
from app.threat_model.service import get_caso_pregunta_out

logger = logging.getLogger(__name__)


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


def _validated_recommendations(
    recomendadas: list[RecommendedQuestion], catalogo_ids: set[uuid.UUID]
) -> list[tuple[uuid.UUID, RecommendedQuestion]]:
    """El LLM recibe los pregunta_id como texto y a veces los transcribe mal
    (son UUIDs largos) o directamente inventa uno — pasa incluso con
    proveedores reales, no sólo en teoría. Se descarta silenciosamente
    (con log) cualquier recomendación que no matchee una Pregunta real, en
    vez de dejar que reviente el insert con un IntegrityError."""
    validadas = []
    for recomendada in recomendadas:
        try:
            pregunta_id = uuid.UUID(recomendada.pregunta_id)
        except ValueError:
            logger.warning("LLM devolvió un pregunta_id no-UUID: %r", recomendada.pregunta_id)
            continue
        if pregunta_id not in catalogo_ids:
            logger.warning("LLM recomendó un pregunta_id que no existe en el catálogo: %s", pregunta_id)
            continue
        validadas.append((pregunta_id, recomendada))
    return validadas


def analyze_document(
    db: Session, caso: Caso, *, filename: str, content: bytes, content_type: str
) -> DocumentoAnalizadoOut:
    """Extrae texto + imágenes (diagramas/páginas rasterizadas) del
    documento, se lo pasa al LLMProvider configurado junto con el catálogo
    completo, y con lo que recomienda: crea CasoPregunta para las preguntas
    que todavía no estaban en alcance y guarda las instrucciones de
    respuesta ES/EN en su CasoRespuesta. Sólo el texto se persiste en
    CasoDocumento — las imágenes son efímeras, se usan sólo para esta
    llamada al LLM."""
    extraido = extract_document(content, content_type)
    catalogo = _catalog_summaries(db)
    imagenes = [DocumentImage(content=img.content, media_type=img.media_type) for img in extraido.images]

    provider = get_llm_provider()
    started = time.perf_counter()
    resultado = provider.analyze_document(extraido.text, catalogo, imagenes)
    # Sólo metadatos: el texto del documento puede ser confidencial y no se loguea.
    logger.info(
        "analisis_documento",
        extra={
            "caso_id": str(caso.id),
            "llm_provider": type(provider).__name__,
            "documento_bytes": len(content),
            "imagenes": len(imagenes),
            "preguntas_recomendadas": len(resultado.preguntas_recomendadas),
            "llm_duration_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )

    documento = CasoDocumento(
        caso_id=caso.id,
        nombre_archivo=filename,
        content_type=content_type,
        texto_extraido=extraido.text,
        clasificacion=resultado.clasificacion,
    )
    db.add(documento)

    existentes = {
        cp.pregunta_id: cp
        for cp in db.scalars(select(CasoPregunta).where(CasoPregunta.caso_id == caso.id))
    }

    catalogo_ids = {uuid.UUID(q.pregunta_id) for q in catalogo}
    pregunta_ids_recomendadas: list[uuid.UUID] = []
    for pregunta_id, recomendada in _validated_recommendations(resultado.preguntas_recomendadas, catalogo_ids):
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
