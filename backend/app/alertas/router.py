"""Sector Alertas: alertas generadas por el worker a partir de Netskope y las
reglas (consultas de Skope IT) que las disparan.

Permisos (provisorios hasta tener roles de Entra ID): cualquier usuario
autenticado ve y gestiona alertas; crear, editar, borrar y probar reglas es
de admin.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.alertas import destinatarios, netskope
from app.alertas import service as svc
from app.alertas.models import DestinatarioAlerta, EstadoAlerta, FuenteRegla, ReglaAlerta, SeveridadAlerta
from app.alertas.schemas import (
    AlertaDetalleOut,
    AlertaOut,
    AlertaUpdate,
    DestinatarioCreate,
    DestinatarioOut,
    DestinatariosOut,
    DestinatarioUpdate,
    PruebaReglaOut,
    ReglaCreate,
    ReglaOut,
    ReglaUpdate,
    ResumenAlertasOut,
    VincularCasoIn,
)
from app.auth.models import User
from app.core.config import get_settings
from app.core.deps import get_current_user, require_admin
from app.db.session import get_db

router = APIRouter(prefix="/alertas", tags=["alertas"])


def _regla(regla_id: uuid.UUID, db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> ReglaAlerta:
    regla = db.get(ReglaAlerta, regla_id)
    if regla is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regla no encontrada")
    return regla


def _alerta(alerta_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    alerta = svc.obtener(db, alerta_id)
    if alerta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada")
    return alerta


def _conflicto(db: Session, exc: Exception) -> HTTPException:
    db.rollback()
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una regla con ese nombre")


# --- resumen y reglas (antes de /{alerta_id}) ---


@router.get("/resumen", response_model=ResumenAlertasOut)
def resumen(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> ResumenAlertasOut:
    return svc.resumen(db)


@router.get("/reglas", response_model=list[ReglaOut])
def listar_reglas(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> list[ReglaOut]:
    return svc.listar_reglas(db)


@router.post("/reglas", response_model=ReglaOut, status_code=status.HTTP_201_CREATED)
def crear_regla(payload: ReglaCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> ReglaAlerta:
    try:
        return svc.crear_regla(db, payload)
    except IntegrityError as exc:
        raise _conflicto(db, exc) from exc


@router.patch("/reglas/{regla_id}", response_model=ReglaOut)
def actualizar_regla(payload: ReglaUpdate, regla: ReglaAlerta = Depends(_regla), db: Session = Depends(get_db)) -> ReglaAlerta:
    try:
        return svc.actualizar_regla(db, regla, payload)
    except IntegrityError as exc:
        raise _conflicto(db, exc) from exc


@router.delete("/reglas/{regla_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_regla(regla: ReglaAlerta = Depends(_regla), db: Session = Depends(get_db)) -> None:
    svc.eliminar_regla(db, regla)


# --- destinatarios del email (antes de /{alerta_id}) ---


def _destinatario(destinatario_id: uuid.UUID, db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> DestinatarioAlerta:
    destinatario = db.get(DestinatarioAlerta, destinatario_id)
    if destinatario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destinatario no encontrado")
    return destinatario


def _destinatarios_out(db: Session) -> DestinatariosOut:
    en_uso, origen = destinatarios.destinatarios(db, get_settings())
    filas = db.scalars(select(DestinatarioAlerta).order_by(DestinatarioAlerta.email)).all()
    return DestinatariosOut(
        destinatarios=[DestinatarioOut.model_validate(d) for d in filas], origen=origen, en_uso=en_uso
    )


@router.get("/destinatarios", response_model=DestinatariosOut)
def listar_destinatarios(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> DestinatariosOut:
    return _destinatarios_out(db)


@router.post("/destinatarios", response_model=DestinatariosOut, status_code=status.HTTP_201_CREATED)
def agregar_destinatario(
    payload: DestinatarioCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)
) -> DestinatariosOut:
    db.add(DestinatarioAlerta(email=payload.email, nombre=payload.nombre or None))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese email ya está cargado") from exc
    return _destinatarios_out(db)


@router.patch("/destinatarios/{destinatario_id}", response_model=DestinatariosOut)
def actualizar_destinatario(
    payload: DestinatarioUpdate, destinatario: DestinatarioAlerta = Depends(_destinatario), db: Session = Depends(get_db)
) -> DestinatariosOut:
    cambios = payload.model_dump(exclude_unset=True)
    if "nombre" in cambios:
        destinatario.nombre = cambios["nombre"] or None
    if cambios.get("activo") is not None:
        destinatario.activo = cambios["activo"]
    db.commit()
    return _destinatarios_out(db)


@router.delete("/destinatarios/{destinatario_id}", response_model=DestinatariosOut)
def eliminar_destinatario(
    destinatario: DestinatarioAlerta = Depends(_destinatario), db: Session = Depends(get_db)
) -> DestinatariosOut:
    db.delete(destinatario)
    db.commit()
    return _destinatarios_out(db)


@router.post("/reglas/{regla_id}/probar", response_model=PruebaReglaOut)
def probar_regla(regla: ReglaAlerta = Depends(_regla)) -> PruebaReglaOut:
    """Ejecuta la consulta contra Netskope (últimas 24 h) sin crear alertas."""
    if regla.fuente != FuenteRegla.NETSKOPE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sólo se pueden probar reglas de Netskope")
    try:
        with netskope.crear_cliente() as client:
            return svc.probar_regla(client, regla.consulta)
    except netskope.NetskopeError as exc:
        code = status.HTTP_502_BAD_GATEWAY if exc.status_code else status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=code, detail=f"Netskope: {exc}") from exc


# --- alertas ---


@router.get("", response_model=list[AlertaOut])
def listar(
    estado: EstadoAlerta | None = None,
    severidad: SeveridadAlerta | None = None,
    regla_id: uuid.UUID | None = None,
    caso_id: uuid.UUID | None = None,
    usuario: str | None = Query(default=None, max_length=200, description="Contiene (usuario o equipo)"),
    app: str | None = Query(default=None, max_length=200, description="Contiene"),
    desde: dt.date | None = Query(default=None, description="Con actividad desde este día (UTC)"),
    hasta: dt.date | None = Query(default=None, description="Con actividad hasta este día inclusive (UTC)"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[AlertaOut]:
    return svc.listar(
        db, estado=estado, severidad=severidad, regla_id=regla_id, caso_id=caso_id,
        usuario=usuario, app=app, desde=desde, hasta=hasta,
    )


@router.get("/{alerta_id}", response_model=AlertaDetalleOut)
def obtener(alerta=Depends(_alerta), db: Session = Depends(get_db)) -> AlertaDetalleOut:
    return svc.detalle(db, alerta)


@router.patch("/{alerta_id}", response_model=AlertaDetalleOut)
def actualizar(payload: AlertaUpdate, alerta=Depends(_alerta), db: Session = Depends(get_db)) -> AlertaDetalleOut:
    return svc.detalle(db, svc.actualizar(db, alerta, estado=payload.estado, nota=payload.nota))


@router.post("/{alerta_id}/caso", response_model=AlertaDetalleOut)
def vincular_caso(payload: VincularCasoIn, alerta=Depends(_alerta), db: Session = Depends(get_db)) -> AlertaDetalleOut:
    """Vincula la alerta a un caso, crea uno nuevo (y su ticket en Jira) o la desvincula."""
    try:
        return svc.detalle(db, svc.vincular_caso(db, alerta, caso_id=payload.caso_id, crear=payload.crear))
    except svc.CasoInexistente as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
