import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.casos import service
from app.casos.models import Caso
from app.core.deps import get_current_user
from app.db.session import get_db


def get_caso_from_path(
    caso_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Caso:
    """`_user` no se usa acá, pero al declararlo como dependencia de ESTA
    función (no como parámetro suelto de cada endpoint) queda garantizado
    que la autenticación se resuelve antes que la búsqueda del caso, sin
    importar en qué orden cada router declare sus propios parámetros —
    401 (no autenticado) siempre gana contra 404 (caso inexistente)."""
    caso = service.get_caso(db, caso_id)
    if caso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caso no encontrado")
    return caso
