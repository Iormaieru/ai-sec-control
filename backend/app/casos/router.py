import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.casos import service
from app.casos.models import Caso, CasoEstado, CasoTipo, Contacto
from app.casos.schemas import CasoCreate, CasoOut, CasoUpdate, ContactoCreate, ContactoOut
from app.core.deps import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/casos", tags=["casos"])


def _get_caso_or_404(db: Session, caso_id: uuid.UUID) -> Caso:
    caso = service.get_caso(db, caso_id)
    if caso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caso no encontrado")
    return caso


@router.post("", response_model=CasoOut, status_code=status.HTTP_201_CREATED)
def create_caso(
    payload: CasoCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> Caso:
    return service.create_caso(
        db,
        gdld=payload.gdld,
        empresa_responsable=payload.empresa_responsable,
        nombre_proyecto=payload.nombre_proyecto,
        tipo=payload.tipo,
    )


@router.get("", response_model=list[CasoOut])
def list_casos(
    estado: CasoEstado | None = None,
    tipo: CasoTipo | None = None,
    empresa_responsable: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[Caso]:
    return service.list_casos(db, estado=estado, tipo=tipo, empresa_responsable=empresa_responsable)


@router.get("/{caso_id}", response_model=CasoOut)
def get_caso(
    caso_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> Caso:
    return _get_caso_or_404(db, caso_id)


@router.patch("/{caso_id}", response_model=CasoOut)
def update_caso(
    caso_id: uuid.UUID,
    payload: CasoUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Caso:
    caso = _get_caso_or_404(db, caso_id)
    try:
        return service.update_caso(
            db,
            caso,
            gdld=payload.gdld,
            empresa_responsable=payload.empresa_responsable,
            nombre_proyecto=payload.nombre_proyecto,
            estado=payload.estado,
        )
    except service.InvalidEstadoTransition as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{caso_id}/contactos", response_model=ContactoOut, status_code=status.HTTP_201_CREATED)
def add_contacto(
    caso_id: uuid.UUID,
    payload: ContactoCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Contacto:
    caso = _get_caso_or_404(db, caso_id)
    return service.add_contacto(db, caso, nombre=payload.nombre, email=payload.email, rol=payload.rol)


@router.delete("/{caso_id}/contactos/{contacto_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_contacto(
    caso_id: uuid.UUID,
    contacto_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    caso = _get_caso_or_404(db, caso_id)
    contacto = next((c for c in caso.contactos if c.id == contacto_id), None)
    if contacto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
    service.remove_contacto(db, contacto)
