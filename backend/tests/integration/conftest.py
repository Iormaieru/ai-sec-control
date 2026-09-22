from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.service import create_user
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers(db: Session, client: TestClient) -> dict[str, str]:
    """A logged-in regular user's Authorization header, for tests that just
    need *some* authenticated identity and don't care about roles."""
    create_user(db, username="test-user", password="test-user-pass")
    response = client.post("/auth/login", data={"username": "test-user", "password": "test-user-pass"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _reset_users_and_audit_log() -> Generator[None, None, None]:
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE users, audit_log, preguntas, dominios, casos, contactos "
                "RESTART IDENTITY CASCADE"
            )
        )
