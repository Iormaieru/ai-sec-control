import pytest
from sqlalchemy.orm import Session

from app.catalog.models import Dominio, Pregunta
from app.catalog.seed import load_catalog


def test_load_catalog_populates_dominios_and_preguntas(db: Session) -> None:
    load_catalog(db)

    assert db.query(Dominio).count() == 8
    assert db.query(Pregunta).count() == 138

    cyb = db.query(Dominio).filter(Dominio.codigo == "CYB").one()
    assert db.query(Pregunta).filter(Pregunta.dominio_id == cyb.id).count() == 37


def test_load_catalog_refuses_to_run_twice(db: Session) -> None:
    load_catalog(db)

    with pytest.raises(RuntimeError):
        load_catalog(db)
