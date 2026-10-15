import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.casos.models import Caso, CasoComentario, CasoEstado, CasoTipo, Contacto, JiraSyncEstado, Origen
from app.integraciones.jira.models import OperacionJira
from app.integraciones.jira.outbox import encolar


class EstadoGestionadoPorJira(Exception):
    """El caso está vinculado a un ticket: el estado cambia sólo con las
    transiciones del workflow de Jira (POST /casos/{id}/transiciones)."""


def create_caso(
    db: Session,
    *,
    gdld: str | None,
    empresa_responsable: str | None,
    nombre_proyecto: str,
    tipo: CasoTipo | None,
    tipo_solicitud_id: str,
) -> Caso:
    """Los casos nuevos se crean también en Jira (vía outbox)."""
    caso = Caso(
        gdld=gdld,
        empresa_responsable=empresa_responsable,
        nombre_proyecto=nombre_proyecto,
        tipo=tipo,
        estado=CasoEstado.POR_HACER,
        origen=Origen.PLATAFORMA,
        jira_tipo_solicitud_id=tipo_solicitud_id,
        # Ya nace pendiente: así el alta queda auditada como un solo CREATE.
        jira_sync_estado=JiraSyncEstado.PENDIENTE,
    )
    db.add(caso)
    db.flush()
    encolar(db, caso, OperacionJira.CREAR_ISSUE)
    db.commit()
    return caso


def get_caso(db: Session, caso_id: uuid.UUID) -> Caso | None:
    return db.get(Caso, caso_id)


def list_casos(
    db: Session,
    *,
    estado: CasoEstado | None = None,
    tipo: CasoTipo | None = None,
    empresa_responsable: str | None = None,
) -> list[Caso]:
    stmt = select(Caso)
    if estado is not None:
        stmt = stmt.where(Caso.estado == estado)
    if tipo is not None:
        stmt = stmt.where(Caso.tipo == tipo)
    if empresa_responsable is not None:
        stmt = stmt.where(Caso.empresa_responsable.ilike(f"%{empresa_responsable}%"))
    stmt = stmt.order_by(Caso.created_at.desc())
    return list(db.scalars(stmt))


def update_caso(
    db: Session,
    caso: Caso,
    *,
    gdld: str | None = None,
    empresa_responsable: str | None = None,
    nombre_proyecto: str | None = None,
    tipo: CasoTipo | None = None,
    estado: CasoEstado | None = None,
) -> Caso:
    if estado is not None and estado != caso.estado:
        if caso.jira_sync_estado is not None:
            raise EstadoGestionadoPorJira("El estado de un caso vinculado a Jira se cambia con sus transiciones")
        caso.estado = estado

    cambia_ticket = (gdld is not None and gdld != caso.gdld) or (
        nombre_proyecto is not None and nombre_proyecto != caso.nombre_proyecto
    )
    if gdld is not None:
        caso.gdld = gdld
    if empresa_responsable is not None:
        caso.empresa_responsable = empresa_responsable
    if tipo is not None:
        caso.tipo = tipo
    if nombre_proyecto is not None:
        caso.nombre_proyecto = nombre_proyecto
    if cambia_ticket and caso.jira_sync_estado is not None:
        encolar(db, caso, OperacionJira.ACTUALIZAR_ISSUE)

    db.commit()
    return caso


def add_contacto(db: Session, caso: Caso, *, nombre: str, email: str | None, rol: str | None) -> Contacto:
    contacto = Contacto(caso_id=caso.id, nombre=nombre, email=email, rol=rol)
    db.add(contacto)
    db.commit()
    return contacto


def remove_contacto(db: Session, contacto: Contacto) -> None:
    db.delete(contacto)
    db.commit()


def add_comentario(db: Session, caso: Caso, *, cuerpo: str, autor: User) -> CasoComentario:
    """Se publica en Jira como comentario interno si el caso está vinculado."""
    comentario = CasoComentario(
        caso_id=caso.id,
        cuerpo=cuerpo,
        autor_nombre=autor.full_name or autor.username,
        origen=Origen.PLATAFORMA,
        publico=False,
    )
    db.add(comentario)
    db.flush()
    if caso.jira_sync_estado is not None:
        encolar(db, caso, OperacionJira.CREAR_COMENTARIO, comentario_id=comentario.id)
    db.commit()
    return comentario
