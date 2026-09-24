"""Runs before any other conftest or test module. Points the test session at
a dedicated local `aisec_test` database — never at whatever backend/.env
points to. Two reasons: (1) every test truncates tables, which once wiped
the dev data a human was using; (2) with a managed database (Cloud SQL) in
backend/.env, running the suite would create and truncate a test database
inside that instance. Must set the env var before `app.core.config`'s
Settings are ever instantiated (they're cached via lru_cache on first use).

Override with AISEC_TEST_DATABASE_URL; it must point to a local host.
"""

import os

from sqlalchemy.engine import make_url

DEFAULT_LOCAL_TEST_URL = "postgresql+psycopg://aisec:aisec@localhost:5433/aisec_test"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db"}

_test_url = os.environ.get("AISEC_TEST_DATABASE_URL", DEFAULT_LOCAL_TEST_URL)
if make_url(_test_url).host not in LOCAL_HOSTS:
    raise RuntimeError(
        "AISEC_TEST_DATABASE_URL debe apuntar a una base local (localhost/127.0.0.1/db): "
        "los tests truncan tablas y crean la base de test, no deben correr contra "
        f"una instancia remota o administrada. Recibido: {make_url(_test_url).host!r}"
    )
os.environ["AISEC_DATABASE_URL"] = _test_url


import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import ProgrammingError  # noqa: E402


def _ensure_test_database_exists(test_url: str) -> None:
    url = make_url(test_url)
    admin_url = url.set(database="postgres")
    db_name = url.database
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name}
            ).first()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except ProgrammingError:
        pass  # otro proceso la creó en paralelo
    finally:
        engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _test_database_ready() -> None:
    _ensure_test_database_exists(_test_url)

    backend_dir = __import__("pathlib").Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(alembic_cfg, "head")
