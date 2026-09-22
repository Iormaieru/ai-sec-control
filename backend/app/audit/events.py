"""Session-level hooks that make audit logging automatic instead of ad-hoc.

Importing this module registers a `before_flush` listener on every
SQLAlchemy Session. It (1) stamps created_by_id/updated_by_id on any
AuditMixin entity being written, and (2) emits a matching AuditLog row for
every CREATE/UPDATE/DELETE — so entity code never has to remember to log
anything itself. This is the documented SQLAlchemy pattern for audit trails:
before_flush is allowed to session.add() further objects and have them
included in the same flush.
"""

import uuid

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.audit.context import current_actor_id
from app.audit.mixin import AuditMixin
from app.audit.models import AuditLog


def _serialize(obj: AuditMixin) -> dict[str, str | None]:
    mapper = inspect(obj).mapper
    return {col.key: _stringify(getattr(obj, col.key)) for col in mapper.columns}


def _changed_fields(obj: AuditMixin) -> dict[str, dict[str, str | None]]:
    state = inspect(obj)
    changes: dict[str, dict[str, str | None]] = {}
    for attr in state.mapper.column_attrs:
        if attr.key in ("updated_at", "updated_by_id"):
            continue
        history = state.attrs[attr.key].history
        if not history.has_changes():
            continue
        before = history.deleted[0] if history.deleted else None
        after = history.added[0] if history.added else getattr(obj, attr.key)
        changes[attr.key] = {"before": _stringify(before), "after": _stringify(after)}
    return changes


def _stringify(value: object) -> str | None:
    return None if value is None else str(value)


@event.listens_for(Session, "before_flush")
def audit_before_flush(session: Session, flush_context: object, instances: object) -> None:
    actor_id = current_actor_id.get()

    for obj in list(session.new):
        if not isinstance(obj, AuditMixin):
            continue
        if obj.id is None:
            obj.id = uuid.uuid4()
        obj.created_by_id = actor_id
        obj.updated_by_id = actor_id
        session.add(
            AuditLog(
                entity_type=type(obj).__name__,
                entity_id=obj.id,
                action="CREATE",
                actor_id=actor_id,
                diff={"after": _serialize(obj)},
            )
        )

    for obj in list(session.dirty):
        if not isinstance(obj, AuditMixin) or not session.is_modified(obj, include_collections=False):
            continue
        changes = _changed_fields(obj)
        if not changes:
            continue
        obj.updated_by_id = actor_id
        session.add(
            AuditLog(
                entity_type=type(obj).__name__,
                entity_id=obj.id,
                action="UPDATE",
                actor_id=actor_id,
                diff=changes,
            )
        )

    for obj in list(session.deleted):
        if not isinstance(obj, AuditMixin):
            continue
        session.add(
            AuditLog(
                entity_type=type(obj).__name__,
                entity_id=obj.id,
                action="DELETE",
                actor_id=actor_id,
                diff={"before": _serialize(obj)},
            )
        )
