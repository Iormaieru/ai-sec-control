import datetime as dt
import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.audit.mixin import AuditMixin
from app.db.base import Base


class InvitacionEstado(str, enum.Enum):
    ENVIADA = "enviada"
    ABIERTA = "abierta"  # el contacto abrió el enlace o guardó un borrador
    RESPONDIDA = "respondida"
    ANULADA = "anulada"  # reemplazada por un reenvío al mismo contacto


class CuestionarioInvitacion(AuditMixin, Base):
    """Un envío del cuestionario de un caso a un contacto por email.

    El enlace lleva un token aleatorio; acá sólo se guarda su SHA-256, así que
    una copia de la base no alcanza para responder en nombre del contacto.
    Mientras el contacto no envía, sus respuestas viven en `borrador` y no
    tocan CasoRespuesta: recién al enviar se aplican al caso.
    """

    __tablename__ = "cuestionario_invitaciones"

    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), nullable=False, index=True)
    contacto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contactos.id", ondelete="CASCADE"), nullable=False
    )
    # Copia del email al momento del envío: el contacto se puede editar después.
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    estado: Mapped[InvitacionEstado] = mapped_column(
        Enum(InvitacionEstado, name="invitacion_estado"), nullable=False, default=InvitacionEstado.ENVIADA
    )
    expira_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    abierta_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    respondida_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # {pregunta_id: {"respuesta": ..., "comentario": ...}}
    borrador: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    caso: Mapped["Caso"] = relationship()  # noqa: F821
    contacto: Mapped["Contacto"] = relationship()  # noqa: F821
