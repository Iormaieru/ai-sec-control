from collections.abc import Generator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _reset_users_and_audit_log() -> Generator[None, None, None]:
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE users, audit_log RESTART IDENTITY CASCADE"))
