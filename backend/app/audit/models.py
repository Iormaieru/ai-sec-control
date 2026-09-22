import datetime as dt
import uuid

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPKMixin


class AuditLog(UUIDPKMixin, Base):
    """Generic 'who did what, when' trail, written automatically for every
    entity that uses AuditMixin (see app/audit/events.py). Not itself an
    AuditMixin entity, so its own writes are never re-audited."""

    __tablename__ = "audit_log"

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
