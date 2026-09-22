import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.casos.deps import get_caso_from_path
from app.casos.models import Caso
from app.core.deps import get_current_user
from app.db.session import get_db
from app.threat_model import service
from app.threat_model.schemas import CasoPreguntaOut, RespuestaUpdate, SeleccionarPreguntasRequest

router = APIRouter(prefix="/casos/{caso_id}/preguntas", tags=["threat-model"])


@router.post("", response_model=list[CasoPreguntaOut], status_code=status.HTTP_201_CREATED)
def seleccionar_preguntas(
    payload: SeleccionarPreguntasRequest,
    caso: Caso = Depends(get_caso_from_path),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[CasoPreguntaOut]:
    try:
        service.add_preguntas(
            db, caso, pregunta_ids=payload.pregunta_ids, dominio_codigo=payload.dominio_codigo
        )
    except service.DominioDesconocido as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return service.list_caso_preguntas(db, caso)


@router.get("", response_model=list[CasoPreguntaOut])
def get_preguntas(
    caso: Caso = Depends(get_caso_from_path), db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> list[CasoPreguntaOut]:
    return service.list_caso_preguntas(db, caso)


@router.put("/{pregunta_id}/respuesta", response_model=CasoPreguntaOut)
def actualizar_respuesta(
    pregunta_id: uuid.UUID,
    payload: RespuestaUpdate,
    caso: Caso = Depends(get_caso_from_path),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CasoPreguntaOut:
    caso_pregunta = service.get_caso_pregunta(db, caso, pregunta_id)
    if caso_pregunta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="La pregunta no está en el alcance de este caso"
        )
    return service.upsert_respuesta(db, caso_pregunta, payload.model_dump())
