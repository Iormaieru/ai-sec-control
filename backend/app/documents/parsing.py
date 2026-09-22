"""Extrae texto plano de los documentos que un caso puede adjuntar (PDF o
Word) para pasárselo al LLM en threat_model/../llm. Nada de esto persiste
el archivo original — sólo el texto extraído (ver documents/models.py)."""

import io

from docx import Document
from pypdf import PdfReader

PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

SUPPORTED_CONTENT_TYPES = {PDF_CONTENT_TYPE, DOCX_CONTENT_TYPE}


class UnsupportedDocumentType(Exception):
    pass


def extract_text(contenido: bytes, content_type: str) -> str:
    if content_type == PDF_CONTENT_TYPE:
        return _extract_pdf_text(contenido)
    if content_type == DOCX_CONTENT_TYPE:
        return _extract_docx_text(contenido)
    raise UnsupportedDocumentType(
        f"Tipo de documento no soportado: {content_type!r}. Se acepta PDF o Word (.docx)."
    )


def _extract_pdf_text(contenido: bytes) -> str:
    reader = PdfReader(io.BytesIO(contenido))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_docx_text(contenido: bytes) -> str:
    document = Document(io.BytesIO(contenido))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()
