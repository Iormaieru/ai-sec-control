import io

import pymupdf
import pytest
from docx import Document
from fpdf import FPDF

from app.documents.parsing import (
    DOCX_CONTENT_TYPE,
    PDF_CONTENT_TYPE,
    UnsupportedDocumentType,
    extract_document,
    extract_text,
)


def _make_pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    return bytes(pdf.output())


def _make_docx_bytes(paragraphs: list[str], tables: list[list[list[str]]] | None = None) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    for table_rows in tables or []:
        table = document.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        for r, row in enumerate(table_rows):
            for c, cell_text in enumerate(row):
                table.cell(r, c).text = cell_text
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _make_png_bytes(size: int = 20) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, size, size))
    return pixmap.tobytes("png")


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


def test_extract_text_from_docx_incluye_tablas() -> None:
    docx_bytes = _make_docx_bytes(
        ["Componentes del sistema"], tables=[[["Componente", "Descripción"], ["API Gateway", "Autenticación JWT"]]]
    )

    text = extract_text(docx_bytes, DOCX_CONTENT_TYPE)

    assert "API Gateway" in text
    assert "Autenticación JWT" in text


def test_unsupported_content_type_raises() -> None:
    with pytest.raises(UnsupportedDocumentType):
        extract_text(b"whatever", "image/png")


def test_extract_document_from_pdf_incluye_una_imagen_por_pagina() -> None:
    pdf_bytes = _make_pdf_bytes("Diagrama de arquitectura en la página 1.")

    extracted = extract_document(pdf_bytes, PDF_CONTENT_TYPE)

    assert len(extracted.images) == 1  # el PDF de prueba tiene 1 página
    assert extracted.images[0].media_type == "image/png"
    assert extracted.images[0].content.startswith(b"\x89PNG")


def test_extract_document_from_docx_incluye_imagenes_embebidas() -> None:
    document = Document()
    document.add_paragraph("Diagrama de arquitectura:")
    document.add_picture(io.BytesIO(_make_png_bytes()))
    buffer = io.BytesIO()
    document.save(buffer)

    extracted = extract_document(buffer.getvalue(), DOCX_CONTENT_TYPE)

    assert len(extracted.images) == 1
    assert extracted.images[0].media_type == "image/png"


def test_extract_document_from_docx_sin_imagenes() -> None:
    docx_bytes = _make_docx_bytes(["Sin diagramas acá."])

    extracted = extract_document(docx_bytes, DOCX_CONTENT_TYPE)

    assert extracted.images == []
