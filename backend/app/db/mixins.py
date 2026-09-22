import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPKMixin:
    """UUID primary key generated client-side (Python), not by the DB.

    Client-side generation means the id is already available on the object
    before it reaches the database, which is what lets the audit hooks in
    app/audit/events.py record a CREATE's entity_id in the same flush that
    creates the row (an autoincrement PK wouldn't be known until after the
    INSERT executes).
    """

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
