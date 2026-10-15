import datetime as dt
import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPKMixin


class OperacionJira(str, enum.Enum):
    CREAR_ISSUE = "crear_issue"
    ACTUALIZAR_ISSUE = "actualizar_issue"
    CREAR_COMENTARIO = "crear_comentario"


class JiraOutbox(UUIDPKMixin, Base):
    """Cambios hechos en la plataforma que falta empujar a Jira.

    Se escribe en la misma transacción que el cambio del caso, así que si
    Jira está caído el cambio no se pierde: se reintenta con backoff hasta
    que entra. No lleva AuditMixin: es mecánica interna, el cambio en sí ya
    queda auditado en el caso o el comentario.
    """

    __tablename__ = "jira_outbox"

    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id", ondelete="CASCADE"), nullable=False, index=True)
    comentario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("caso_comentarios.id", ondelete="CASCADE"), nullable=True
    )
    operacion: Mapped[OperacionJira] = mapped_column(Enum(OperacionJira, name="operacion_jira"), nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proximo_intento_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Jira la rechazó (4xx): no se reintenta sola, sólo con "Reintentar".
    descartada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    procesado_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class JiraSyncCursor(Base):
    """Una sola fila (id=1): hasta cuándo se trajeron cambios de Jira."""

    __tablename__ = "jira_sync_cursor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ultimo_poll_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
