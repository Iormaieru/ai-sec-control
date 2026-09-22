"""Loads the versioned catalog seed (data/seed/catalogo_maestro.json) into
the DB. Run once per environment, after migrations:
    uv run python scripts/seed_catalog.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog.models import Dominio  # noqa: E402
from app.catalog.seed import load_catalog  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        if db.query(Dominio).count() > 0:
            print("El catálogo ya está cargado; nada para hacer.")
            return
        load_catalog(db)
        print("Catálogo cargado correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
