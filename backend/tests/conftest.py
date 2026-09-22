"""Runs before any other conftest or test module. Points the test session at
a dedicated `aisec_test` database instead of the dev database configured in
backend/.env — otherwise every test run truncates the same tables a human
is using for manual/demo purposes (which is exactly what happened once and
is why this file exists). Must set the env var before `app.core.config`'s
Settings are ever instantiated (they're cached via lru_cache on first use).
"""

import os
import re

_dev_url = os.environ.get("AISEC_DATABASE_URL")
if _dev_url is None:
    # Ningún AISEC_DATABASE_URL en el entorno: leer backend/.env a mano
    # (pydantic-settings todavía no se importó) sólo para derivar la URL de
    # test a partir de la de dev, sin adivinar host/usuario/contraseña.
    from pathlib import Path

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("AISEC_DATABASE_URL="):
                _dev_url = line.split("=", 1)[1].strip()
                break

_dev_url = _dev_url or "postgresql+psycopg://aisec:aisec@localhost:5433/aisec"
_test_url = re.sub(r"/([^/]+)$", "/aisec_test", _dev_url)
os.environ["AISEC_DATABASE_URL"] = _test_url


import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import ProgrammingError  # noqa: E402


def _ensure_test_database_exists(test_url: str) -> None:
    admin_url = re.sub(r"/[^/]+$", "/postgres", test_url)
    db_name = test_url.rsplit("/", 1)[-1]
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
