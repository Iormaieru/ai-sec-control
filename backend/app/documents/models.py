import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.audit.mixin import AuditMixin
from app.db.base import Base


class CasoDocumento(AuditMixin, Base):
    """Un documento (PDF/Word) subido para que la IA lo analice. Sólo se
    guarda el texto extraído (ver documents/parsing.py), no el archivo
    original — es lo que se le mandó al LLM y lo que sostiene la
    clasificación resultante, para trazabilidad/auditoría."""

    __tablename__ = "caso_documentos"

    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    texto_extraido: Mapped[str] = mapped_column(Text, nullable=False)
    clasificacion: Mapped[str] = mapped_column(Text, nullable=False)

    caso: Mapped["Caso"] = relationship()  # noqa: F821
