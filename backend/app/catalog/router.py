from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.catalog.models import Dominio, Pregunta
from app.catalog.schemas import DominioOut, PreguntaOut
from app.core.deps import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/catalogo", tags=["catalogo"])


@router.get("/dominios", response_model=list[DominioOut])
def list_dominios(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> list[Dominio]:
    return list(db.scalars(select(Dominio).order_by(Dominio.codigo)))


@router.get("/preguntas", response_model=list[PreguntaOut])
def list_preguntas(
    dominio: str | None = None, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> list[Pregunta]:
    stmt = select(Pregunta).join(Dominio).order_by(Dominio.codigo, Pregunta.numero)
    if dominio is not None:
        stmt = stmt.where(Dominio.codigo == dominio)
    return list(db.scalars(stmt))
