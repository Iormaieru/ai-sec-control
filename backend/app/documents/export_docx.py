"""Genera el informe Word de un caso: preguntas seleccionadas + sus
instrucciones de respuesta y explicación del control, en español e
inglés — lo que hoy se arma a mano para mandarle al proveedor/usuario."""

import io

from docx import Document
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casos.models import Caso
from app.documents.models import CasoDocumento
from app.threat_model.service import list_caso_preguntas

TIPO_LABELS = {
    "candidato": "Candidato",
    "ingresado": "Ingresado",
    "herramienta_tercero": "Herramienta de tercero",
}


def _latest_classification(db: Session, caso_id) -> str | None:
    return db.scalar(
        select(CasoDocumento.clasificacion)
        .where(CasoDocumento.caso_id == caso_id)
        .order_by(CasoDocumento.created_at.desc())
        .limit(1)
    )


def build_caso_report(db: Session, caso: Caso) -> bytes:
    preguntas = list_caso_preguntas(db, caso)  # ya ordenadas por dominio, número
    clasificacion = _latest_classification(db, caso.id)

    document = Document()
    document.add_heading("AI-SEC Control — Informe de modelado de amenazas", level=0)

    document.add_paragraph(f"Proyecto / Project: {caso.nombre_proyecto}")
    document.add_paragraph(f"Empresa responsable / Responsible company: {caso.empresa_responsable}")
    document.add_paragraph(f"Tipo / Type: {TIPO_LABELS.get(caso.tipo.value, caso.tipo.value)}")
    if caso.gdld:
        document.add_paragraph(f"GDLD {caso.gdld}")
    if clasificacion:
        document.add_paragraph(f"Clasificación de la solución (IA) / AI solution classification: {clasificacion}")

    dominio_actual: str | None = None
    for pregunta in preguntas:
        if pregunta.dominio_codigo != dominio_actual:
            dominio_actual = pregunta.dominio_codigo
            document.add_heading(dominio_actual, level=1)

        document.add_heading(f"{pregunta.numero}. {pregunta.texto_es}", level=2)
        document.add_paragraph(pregunta.texto_en)

        if pregunta.instrucciones_respuesta_es:
            document.add_paragraph(f"Cómo responder: {pregunta.instrucciones_respuesta_es}")
        if pregunta.instrucciones_respuesta_en:
            document.add_paragraph(f"How to answer: {pregunta.instrucciones_respuesta_en}")

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
