from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.audit.context import current_actor_id
from app.auth.models import User
from app.casos.deps import get_caso_from_path
from app.casos.models import Caso
from app.core.deps import get_current_user
from app.core.email import EmailNoEnviado
from app.cuestionarios import service
from app.cuestionarios.models import CuestionarioInvitacion
from app.cuestionarios.schemas import (
    EnviarCuestionarioRequest,
    EnvioResultadoOut,
    FormularioOut,
    InvitacionOut,
    RespuestasFormularioRequest,
)
from app.db.session import get_db

router = APIRouter(prefix="/casos/{caso_id}/cuestionarios", tags=["cuestionarios"])
# Sin JWT: lo usa el contacto externo desde el enlace del email. El token
# viaja en un header y no en la URL para que no quede en los logs de acceso
# (RequestLoggingMiddleware registra el path).
public_router = APIRouter(prefix="/cuestionario", tags=["cuestionarios"])

_TOKEN_INVALIDO = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace inválido")


@router.post("", response_model=list[InvitacionOut], status_code=status.HTTP_201_CREATED)
def enviar_cuestionario(
    payload: EnviarCuestionarioRequest,
    caso: Caso = Depends(get_caso_from_path),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[InvitacionOut]:
    try:
        return service.enviar_cuestionario(db, caso, payload.contacto_ids)
    except (service.ContactoInvalido, service.CasoSinPreguntas) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EmailNoEnviado as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("", response_model=list[InvitacionOut])
def list_invitaciones(
    caso: Caso = Depends(get_caso_from_path), db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> list[InvitacionOut]:
    return service.list_invitaciones(db, caso)


def _load_invitacion(
    x_cuestionario_token: str = Header(), db: Session = Depends(get_db)
) -> CuestionarioInvitacion:
    invitacion = service.get_invitacion_por_token(db, x_cuestionario_token)
    if invitacion is None:
        raise _TOKEN_INVALIDO
    try:
        service.verificar_vigente(invitacion)
    except service.InvitacionNoVigente as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    return invitacion


async def get_invitacion_vigente(
    invitacion: CuestionarioInvitacion = Depends(_load_invitacion),
) -> CuestionarioInvitacion:
    # Async por el mismo motivo que get_current_user (app/core/deps.py): el
    # actor tiene que quedar en el contexto del request. Lo que cambie el
    # contacto queda auditado con su contacto_id como actor (audit_log no
    # tiene FK a users, ver AuditMixin).
    current_actor_id.set(invitacion.contacto_id)
    return invitacion


@public_router.get("", response_model=FormularioOut)
def get_formulario(
    invitacion: CuestionarioInvitacion = Depends(get_invitacion_vigente), db: Session = Depends(get_db)
) -> FormularioOut:
    return service.get_formulario(db, invitacion)


@public_router.put("/borrador", status_code=status.HTTP_204_NO_CONTENT)
def guardar_borrador(
    payload: RespuestasFormularioRequest,
    invitacion: CuestionarioInvitacion = Depends(get_invitacion_vigente),
    db: Session = Depends(get_db),
) -> None:
    try:
        service.guardar_borrador(db, invitacion, payload.respuestas)
    except service.PreguntaFueraDeAlcance as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@public_router.post("/enviar", response_model=EnvioResultadoOut)
def enviar_respuestas(
    payload: RespuestasFormularioRequest,
    invitacion: CuestionarioInvitacion = Depends(get_invitacion_vigente),
    db: Session = Depends(get_db),
) -> EnvioResultadoOut:
    try:
        return service.enviar_respuestas(db, invitacion, payload.respuestas)
    except service.PreguntaFueraDeAlcance as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
