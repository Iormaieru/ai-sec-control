from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.models import User
from app.casos.models import CasoTipo
from app.core.deps import get_current_user
from app.db.session import get_db
from app.metricas import service
from app.metricas.schemas import MetricasOut

router = APIRouter(prefix="/metricas", tags=["metricas"])


@router.get("", response_model=MetricasOut)
def get_metricas(
    desde: date | None = None,
    hasta: date | None = None,
    tipo: CasoTipo | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MetricasOut:
    return service.get_metricas(db, desde, hasta, tipo)
