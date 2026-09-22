import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.casos import service
from app.casos.deps import get_caso_from_path
from app.casos.models import Caso, CasoEstado, CasoTipo, Contacto
from app.casos.schemas import CasoCreate, CasoOut, CasoUpdate, ContactoCreate, ContactoOut
from app.core.deps import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/casos", tags=["casos"])


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
def get_caso(caso: Caso = Depends(get_caso_from_path), _user: User = Depends(get_current_user)) -> Caso:
    return caso


@router.patch("/{caso_id}", response_model=CasoOut)
def update_caso(
    payload: CasoUpdate,
    caso: Caso = Depends(get_caso_from_path),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Caso:
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
    payload: ContactoCreate,
    caso: Caso = Depends(get_caso_from_path),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Contacto:
    return service.add_contacto(db, caso, nombre=payload.nombre, email=payload.email, rol=payload.rol)


@router.delete("/{caso_id}/contactos/{contacto_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_contacto(
    contacto_id: uuid.UUID,
    caso: Caso = Depends(get_caso_from_path),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    contacto = next((c for c in caso.contactos if c.id == contacto_id), None)
    if contacto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
    service.remove_contacto(db, contacto)
