"""El catálogo llega por una migración de datos, no por un script: tras
`alembic upgrade head` (lo hace tests/conftest.py) la base ya lo tiene."""

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.catalog.models import Dominio, Pregunta, Tier
from app.db.session import engine

MIGRATION = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "8c55274c7ed7_seed_catalogo_maestro_138_preguntas_.py"
)

EXPECTED = {"DDG": 10, "TAC": 7, "PDP": 18, "CYB": 37, "SAF": 25, "BFD": 15, "EHR": 13, "AHO": 13}


def test_la_migracion_dejo_los_8_dominios_y_las_138_preguntas(db: Session) -> None:
    assert db.query(Dominio).count() == 8
    assert db.query(Pregunta).count() == 138

    por_dominio = dict(
        db.query(Dominio.codigo, func.count(Pregunta.id)).join(Pregunta).group_by(Dominio.codigo).all()
    )
    assert por_dominio == EXPECTED


def test_los_pesos_de_los_dominios_suman_uno(db: Session) -> None:
    assert sum(d.peso for d in db.query(Dominio)) == Decimal("1.0")


def test_multiplicador_es_coherente_con_el_tier(db: Session) -> None:
    esperado = {Tier.CRITICO: 3, Tier.ALTO: 2, Tier.ESTANDAR: 1}
    assert all(p.multiplicador == esperado[p.tier] for p in db.query(Pregunta))


def test_la_migracion_es_idempotente() -> None:
    """En una base que ya tiene el catálogo (ej. cargado a mano antes de que
    existiera la migración) volver a aplicarla no duplica ni falla."""
    spec = importlib.util.spec_from_file_location("seed_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with engine.begin() as conn:
        module.seed_catalog(conn)
        module.seed_catalog(conn)

    with Session(engine) as session:
        assert session.query(Dominio).count() == 8
        assert session.query(Pregunta).count() == 138


@pytest.mark.parametrize("codigo,tier,cantidad", [("CYB", Tier.CRITICO, 20), ("PDP", Tier.ESTANDAR, 0)])
def test_conteo_por_tier_de_dominios_conocidos(db: Session, codigo: str, tier: Tier, cantidad: int) -> None:
    total = (
        db.query(Pregunta).join(Dominio).filter(Dominio.codigo == codigo, Pregunta.tier == tier).count()
    )
    assert total == cantidad
