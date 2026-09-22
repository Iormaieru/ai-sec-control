import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.models import Dominio, Polaridad, Pregunta, PreguntaTipo, Tier


def _make_dominio(db: Session, codigo: str = "CYB") -> Dominio:
    dominio = Dominio(codigo=codigo, nombre="Cybersecurity", peso="0.22", total_preguntas=37)
    db.add(dominio)
    db.commit()
    return dominio


def test_create_dominio_and_pregunta(db: Session) -> None:
    dominio = _make_dominio(db)
    pregunta = Pregunta(
        dominio_id=dominio.id,
        numero=1,
        texto_es="¿Pregunta?",
        texto_en="Question?",
        tipo=PreguntaTipo.RIESGO,
        polaridad=Polaridad.NEGATIVA,
        tier=Tier.CRITICO,
        multiplicador=3,
    )
    db.add(pregunta)
    db.commit()

    assert pregunta.dominio.codigo == "CYB"
    assert float(dominio.peso) == pytest.approx(0.22)


def test_pregunta_numero_unique_within_dominio(db: Session) -> None:
    dominio = _make_dominio(db, codigo="PRI")
    db.add(
        Pregunta(
            dominio_id=dominio.id,
            numero=1,
            texto_es="A",
            texto_en="A",
            tipo=PreguntaTipo.CONTROL,
            polaridad=Polaridad.POSITIVA,
            tier=Tier.ALTO,
            multiplicador=2,
        )
    )
    db.commit()

    db.add(
        Pregunta(
            dominio_id=dominio.id,
            numero=1,
            texto_es="B",
            texto_en="B",
            tipo=PreguntaTipo.CONTROL,
            polaridad=Polaridad.POSITIVA,
            tier=Tier.ALTO,
            multiplicador=2,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
