from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.service import create_user
from app.catalog.models import Pregunta
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


@pytest.fixture
def catalog_loaded(db: Session) -> None:
    """El catálogo lo carga la migración de datos (alembic upgrade head, ver
    tests/conftest.py) y ningún test lo trunca; esta fixture sólo falla con
    un mensaje claro si algún test lo dejó incompleto."""
    total = db.query(Pregunta).count()
    assert total == 138, f"El catálogo debería tener 138 preguntas y tiene {total}"


@pytest.fixture(autouse=True)
def _cleanup_test_estandares() -> Generator[None, None, None]:
    """Los estándares sembrados por migración no se truncan (igual que el
    catálogo PLOT4AI); los que crean los tests usan código TST-* y se borran."""
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pentests WHERE estandar_id IN (SELECT id FROM pentest_estandares WHERE codigo LIKE 'TST-%')"))
        conn.execute(text("DELETE FROM pentest_estandares WHERE codigo LIKE 'TST-%'"))


@pytest.fixture(autouse=True)
def _reset_users_and_audit_log() -> Generator[None, None, None]:
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE users, audit_log, casos, contactos, "
                "caso_preguntas, caso_respuestas, caso_documentos, herramientas_pentest, "
                "pentests, pentest_ataques, pentest_ataque_herramientas RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def admin_headers(db: Session, client: TestClient) -> dict[str, str]:
    from app.auth.models import UserRole

    create_user(db, username="test-admin", password="test-admin-pass", role=UserRole.ADMIN)
    response = client.post("/auth/login", data={"username": "test-admin", "password": "test-admin-pass"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
