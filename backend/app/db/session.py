from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
# expire_on_commit=False: a request-scoped session may commit more than once
# (e.g. a bulk endpoint), and the audit hooks in app/audit/events.py need an
# attribute's pre-mutation value to still be in memory (not expired) to
# compute an accurate before/after diff on a later commit in the same session.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from app.audit import events  # noqa: E402, F401  (registers before_flush audit hook)
