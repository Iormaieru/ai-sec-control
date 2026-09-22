import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casos.models import Caso, CasoEstado, CasoTipo, Contacto

# Transiciones válidas de estado. ABIERTO -> EN_ANALISIS -> (ESPERANDO_PROVEEDOR <-> EN_ANALISIS)
# -> CERRADO_APROBADO, con RECHAZADO alcanzable desde cualquier estado no terminal.
# CERRADO_APROBADO y RECHAZADO son terminales (no hay vuelta atrás por API; una
# corrección post-cierre es un caso nuevo o una acción administrativa directa en DB).
ALLOWED_TRANSITIONS: dict[CasoEstado, set[CasoEstado]] = {
    CasoEstado.ABIERTO: {CasoEstado.EN_ANALISIS, CasoEstado.RECHAZADO},
    CasoEstado.EN_ANALISIS: {CasoEstado.ESPERANDO_PROVEEDOR, CasoEstado.CERRADO_APROBADO, CasoEstado.RECHAZADO},
    CasoEstado.ESPERANDO_PROVEEDOR: {CasoEstado.EN_ANALISIS, CasoEstado.CERRADO_APROBADO, CasoEstado.RECHAZADO},
    CasoEstado.CERRADO_APROBADO: set(),
    CasoEstado.RECHAZADO: set(),
}


class InvalidEstadoTransition(Exception):
    def __init__(self, actual: CasoEstado, nuevo: CasoEstado) -> None:
        self.actual = actual
        self.nuevo = nuevo
        super().__init__(f"No se puede pasar de '{actual.value}' a '{nuevo.value}'")


def create_caso(
    db: Session, *, gdld: str | None, empresa_responsable: str, nombre_proyecto: str, tipo: CasoTipo
) -> Caso:
    caso = Caso(
        gdld=gdld, empresa_responsable=empresa_responsable, nombre_proyecto=nombre_proyecto, tipo=tipo
    )
    db.add(caso)
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
    estado: CasoEstado | None = None,
) -> Caso:
    if gdld is not None:
        caso.gdld = gdld
    if empresa_responsable is not None:
        caso.empresa_responsable = empresa_responsable
    if nombre_proyecto is not None:
        caso.nombre_proyecto = nombre_proyecto
    if estado is not None and estado != caso.estado:
        if estado not in ALLOWED_TRANSITIONS[caso.estado]:
            raise InvalidEstadoTransition(caso.estado, estado)
        caso.estado = estado

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
