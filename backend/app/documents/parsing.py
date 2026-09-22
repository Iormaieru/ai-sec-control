"""Extrae texto e imágenes de los documentos que un caso puede adjuntar
(PDF o Word) para pasárselos al LLM (ver app/llm). Nada de esto persiste
el archivo original — sólo el texto extraído y, si el proveedor soporta
visión, las imágenes (ver documents/models.py — sólo el texto se guarda
en CasoDocumento, las imágenes son efímeras, se usan sólo para la llamada
al LLM de este análisis puntual)."""

import io
from dataclasses import dataclass, field

import pymupdf
from docx import Document
from pypdf import PdfReader

PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

SUPPORTED_CONTENT_TYPES = {PDF_CONTENT_TYPE, DOCX_CONTENT_TYPE}

# Cota de páginas/imágenes que se rasterizan y mandan al LLM: un documento
# de arquitectura no debería necesitar más, y cada imagen suma tokens
# (costo) y tiempo de respuesta a la llamada.
MAX_IMAGES = 10

# Formatos que la API de visión de OpenAI acepta — un diagrama pegado como
# EMF/WMF (típico al copiar desde Visio/PowerPoint a Word) se descarta en
# vez de mandarse mal etiquetado.
SUPPORTED_IMAGE_MEDIA_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


@dataclass
class ExtractedImage:
    content: bytes
    media_type: str  # "image/png", "image/jpeg", etc.


@dataclass
class ExtractedDocument:
    text: str
    images: list[ExtractedImage] = field(default_factory=list)  # como mucho MAX_IMAGES


class UnsupportedDocumentType(Exception):
    pass


def extract_document(contenido: bytes, content_type: str) -> ExtractedDocument:
    if content_type == PDF_CONTENT_TYPE:
        return _extract_pdf(contenido)
    if content_type == DOCX_CONTENT_TYPE:
        return _extract_docx(contenido)
    raise UnsupportedDocumentType(
        f"Tipo de documento no soportado: {content_type!r}. Se acepta PDF o Word (.docx)."
    )


def extract_text(contenido: bytes, content_type: str) -> str:
    """Sólo el texto — conveniencia para quien no necesita las imágenes."""
    return extract_document(contenido, content_type).text


def _extract_pdf(contenido: bytes) -> ExtractedDocument:
    reader = PdfReader(io.BytesIO(contenido))
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()

    images: list[ExtractedImage] = []
    with pymupdf.open(stream=contenido, filetype="pdf") as pdf:
        for page in pdf:
            if len(images) >= MAX_IMAGES:
                break
            pixmap = page.get_pixmap(dpi=150)
            images.append(ExtractedImage(content=pixmap.tobytes("png"), media_type="image/png"))

    return ExtractedDocument(text=text, images=images)


def _extract_docx(contenido: bytes) -> ExtractedDocument:
    document = Document(io.BytesIO(contenido))

    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    tables_text = [
        cell.text for table in document.tables for row in table.rows for cell in row.cells if cell.text.strip()
    ]
    text = "\n".join(paragraphs + tables_text).strip()

    images: list[ExtractedImage] = []
    for rel in document.part.rels.values():
        if len(images) >= MAX_IMAGES:
            break
        if "image" not in rel.reltype:
            continue
        media_type = rel.target_part.content_type
        if media_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
            continue  # ej. EMF/WMF pegado desde Visio/PowerPoint — la API de visión no lo lee
        images.append(ExtractedImage(content=rel.target_part.blob, media_type=media_type))

    return ExtractedDocument(text=text, images=images)
