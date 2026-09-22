import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.casos import service
from app.casos.models import Caso
from app.db.session import get_db


def get_caso_from_path(caso_id: uuid.UUID, db: Session = Depends(get_db)) -> Caso:
    caso = service.get_caso(db, caso_id)
    if caso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caso no encontrado")
    return caso
