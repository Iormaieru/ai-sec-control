import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.casos import service
from app.casos.deps import get_caso_from_path
from app.casos.models import Caso, CasoComentario, CasoEstado, CasoTipo, Contacto
from app.casos.schemas import (
    AsignarIn,
    CasoCreate,
    CasoOut,
    CasoUpdate,
    ComentarioCreate,
    ComentarioOut,
    ContactoCreate,
    PersonaJiraOut,
    ContactoOut,
    TipoSolicitudOut,
    TransicionIn,
    TransicionOut,
)
from app.core.config import get_settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.integraciones.jira import sync
from app.integraciones.jira.client import JiraClient, JiraError

router = APIRouter(prefix="/casos", tags=["casos"])


@router.post("", response_model=CasoOut, status_code=status.HTTP_201_CREATED)
def create_caso(
    payload: CasoCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Caso:
    return service.create_caso(
        db,
        gdld=payload.gdld,
        empresa_responsable=payload.empresa_responsable,
        nombre_proyecto=payload.nombre_proyecto,
        tipo=payload.tipo,
        tipo_solicitud_id=payload.tipo_solicitud_id or next(iter(get_settings().jira_request_types)),
    )


@router.get("/equipo-jira", response_model=list[PersonaJiraOut])
def list_equipo_jira(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> list[sync.PersonaJira]:
    """Personas que ya tienen casos asignados (atajo del selector de asignado)."""
    return sync.equipo(db)


@router.get("/tipos-solicitud", response_model=list[TipoSolicitudOut])
def list_tipos_solicitud(_user: User = Depends(get_current_user)) -> list[TipoSolicitudOut]:
    return [TipoSolicitudOut(id=k, nombre=v) for k, v in get_settings().jira_request_types.items()]


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
            tipo=payload.tipo,
            estado=payload.estado,
        )
    except service.EstadoGestionadoPorJira as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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


@router.get("/{caso_id}/comentarios", response_model=list[ComentarioOut])
def list_comentarios(caso: Caso = Depends(get_caso_from_path)) -> list[CasoComentario]:
    return caso.comentarios


@router.post("/{caso_id}/comentarios", response_model=ComentarioOut, status_code=status.HTTP_201_CREATED)
def add_comentario(
    payload: ComentarioCreate,
    caso: Caso = Depends(get_caso_from_path),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CasoComentario:
    return service.add_comentario(db, caso, cuerpo=payload.cuerpo, autor=user)


def _cliente_para(caso: Caso) -> JiraClient:
    if not caso.jira_issue_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El caso todavía no tiene ticket en Jira"
        )
    try:
        return sync.crear_cliente()
    except sync.JiraDeshabilitada as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/{caso_id}/transiciones", response_model=list[TransicionOut])
def list_transiciones(caso: Caso = Depends(get_caso_from_path)) -> list[sync.Transicion]:
    """Las transiciones que el workflow de Jira permite hoy para el ticket."""
    with _cliente_para(caso) as client:
        try:
            return sync.transiciones(client, caso)
        except JiraError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo consultar Jira: {exc}"
            ) from exc


@router.post("/{caso_id}/transiciones", response_model=CasoOut)
def transicionar(
    payload: TransicionIn, caso: Caso = Depends(get_caso_from_path), db: Session = Depends(get_db)
) -> Caso:
    with _cliente_para(caso) as client:
        try:
            return sync.transicionar(db, client, caso, payload.transition_id)
        except JiraError as exc:
            db.rollback()
            code = status.HTTP_400_BAD_REQUEST if not exc.transitorio else status.HTTP_503_SERVICE_UNAVAILABLE
            raise HTTPException(status_code=code, detail=f"Jira rechazó la transición: {exc}") from exc


@router.post("/{caso_id}/jira/reintentar", response_model=CasoOut)
def reintentar_jira(caso: Caso = Depends(get_caso_from_path), db: Session = Depends(get_db)) -> Caso:
    """Vuelve a poner en cola los eventos fallidos del caso; los envía el worker."""
    sync.reintentar(db, caso)
    return caso


@router.get("/{caso_id}/asignables", response_model=list[PersonaJiraOut])
def list_asignables(query: str = "", caso: Caso = Depends(get_caso_from_path)) -> list[sync.PersonaJira]:
    """Personas de Jira a las que se puede asignar el ticket (búsqueda por nombre)."""
    with _cliente_para(caso) as client:
        try:
            return sync.asignables(client, caso, query[:100])
        except JiraError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo consultar Jira: {exc}"
            ) from exc


@router.put("/{caso_id}/asignado", response_model=CasoOut)
def asignar(payload: AsignarIn, caso: Caso = Depends(get_caso_from_path), db: Session = Depends(get_db)) -> Caso:
    """Asigna (o desasigna) el ticket en Jira y actualiza el caso."""
    with _cliente_para(caso) as client:
        try:
            return sync.asignar(db, client, caso, payload.account_id)
        except JiraError as exc:
            db.rollback()
            code = status.HTTP_400_BAD_REQUEST if not exc.transitorio else status.HTTP_503_SERVICE_UNAVAILABLE
            raise HTTPException(status_code=code, detail=f"Jira rechazó la asignación: {exc}") from exc
