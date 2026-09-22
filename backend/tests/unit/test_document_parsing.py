import io

import pytest
from docx import Document
from fpdf import FPDF

from app.documents.parsing import (
    DOCX_CONTENT_TYPE,
    PDF_CONTENT_TYPE,
    UnsupportedDocumentType,
    extract_text,
)


def _make_pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    return bytes(pdf.output())


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_extract_text_from_pdf() -> None:
    pdf_bytes = _make_pdf_bytes("Arquitectura del sistema de recomendaciones basado en LLM.")

    text = extract_text(pdf_bytes, PDF_CONTENT_TYPE)

    assert "Arquitectura del sistema" in text


def test_extract_text_from_docx() -> None:
    docx_bytes = _make_docx_bytes(
        ["Documento de arquitectura", "Usa un modelo de lenguaje para clasificar tickets."]
    )

    text = extract_text(docx_bytes, DOCX_CONTENT_TYPE)

    assert "Documento de arquitectura" in text
    assert "clasificar tickets" in text


def test_unsupported_content_type_raises() -> None:
    with pytest.raises(UnsupportedDocumentType):
        extract_text(b"whatever", "image/png")
