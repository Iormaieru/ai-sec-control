"""Verifies AuditMixin + the before_flush hooks (app/audit/events.py) against
a real Postgres connection: created/updated stamps and AuditLog rows must be
produced automatically, without the test ever calling an audit function."""

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.audit.context import current_actor_id
from app.audit.mixin import AuditMixin
from app.audit.models import AuditLog
from app.db.base import Base
from app.db.session import engine


class Widget(AuditMixin, Base):
    """Throwaway entity that exists only to exercise the audit hooks."""

    __tablename__ = "test_widgets"

    name: Mapped[str] = mapped_column(String(100))


@pytest.fixture(autouse=True)
def _widget_table() -> Generator[None, None, None]:
    Widget.__table__.create(bind=engine, checkfirst=True)
    yield
    Widget.__table__.drop(bind=engine, checkfirst=True)


@pytest.fixture
def actor() -> Generator[uuid.UUID, None, None]:
    actor_id = uuid.uuid4()
    token = current_actor_id.set(actor_id)
    yield actor_id
    current_actor_id.reset(token)


def _audit_logs_for(db: Session, entity_id: uuid.UUID) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "Widget", AuditLog.entity_id == entity_id)
        .order_by(AuditLog.timestamp)
        .all()
    )


def test_create_stamps_created_by_and_writes_audit_log(db: Session, actor: uuid.UUID) -> None:
    widget = Widget(name="thingamajig")
    db.add(widget)
    db.commit()

    assert widget.created_by_id == actor
    assert widget.updated_by_id == actor
    assert widget.created_at is not None

    logs = _audit_logs_for(db, widget.id)
    assert len(logs) == 1
    assert logs[0].action == "CREATE"
    assert logs[0].actor_id == actor
    assert logs[0].diff["after"]["name"] == "thingamajig"


def test_update_stamps_updated_by_and_writes_diff(db: Session, actor: uuid.UUID) -> None:
    widget = Widget(name="original")
    db.add(widget)
    db.commit()

    other_actor = uuid.uuid4()
    token = current_actor_id.set(other_actor)
    try:
        widget.name = "renamed"
        db.commit()
    finally:
        current_actor_id.reset(token)

    assert widget.updated_by_id == other_actor

    logs = _audit_logs_for(db, widget.id)
    assert [log.action for log in logs] == ["CREATE", "UPDATE"]
    update_log = logs[1]
    assert update_log.actor_id == other_actor
    assert update_log.diff["name"] == {"before": "original", "after": "renamed"}


def test_delete_writes_audit_log(db: Session, actor: uuid.UUID) -> None:
    widget = Widget(name="disposable")
    db.add(widget)
    db.commit()
    widget_id = widget.id

    db.delete(widget)
    db.commit()

    logs = _audit_logs_for(db, widget_id)
    assert [log.action for log in logs] == ["CREATE", "DELETE"]
    assert logs[1].diff["before"]["name"] == "disposable"


def test_no_op_update_does_not_write_extra_audit_log(db: Session, actor: uuid.UUID) -> None:
    widget = Widget(name="stable")
    db.add(widget)
    db.commit()

    widget.name = "stable"  # unchanged value
    db.commit()

    logs = _audit_logs_for(db, widget.id)
    assert [log.action for log in logs] == ["CREATE"]
