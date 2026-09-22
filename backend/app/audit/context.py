import uuid
from contextvars import ContextVar

current_actor_id: ContextVar[uuid.UUID | None] = ContextVar("current_actor_id", default=None)
