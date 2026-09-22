import datetime as dt
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import UUIDPKMixin


class AuditMixin(UUIDPKMixin):
    """Adds id + created/updated who-and-when to any entity.

    created_by_id/updated_by_id intentionally have no DB-level foreign key to
    the users table: it keeps this module independent from the auth module's
    migration order, and it means audit history for an entity survives even
    if the acting user is later deleted. Values are populated automatically
    by the SQLAlchemy session hooks in app/audit/events.py, not by callers.
    """

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
