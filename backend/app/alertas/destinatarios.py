"""A quién se manda el email resumen de alertas.

Punto único para el worker y la API: hoy son las casillas activas cargadas en
la plataforma y, si no hay ninguna, AISEC_ALERTAS_EMAIL_DESTINO (compatibilidad
con la configuración anterior). Cuando la plataforma se integre con Entra ID,
los destinatarios van a salir de un grupo del AD del banco: se cambia sólo esta
función.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alertas.models import DestinatarioAlerta
from app.core.config import Settings


def de_la_plataforma(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(DestinatarioAlerta.email).where(DestinatarioAlerta.activo.is_(True)).order_by(DestinatarioAlerta.email)
        )
    )


def destinatarios(db: Session, settings: Settings) -> tuple[list[str], str]:
    """(casillas, origen): origen es "plataforma", "variable" o "ninguno"."""
    cargados = de_la_plataforma(db)
    if cargados:
        return cargados, "plataforma"
    if settings.alertas_email_destino_list:
        return settings.alertas_email_destino_list, "variable"
    return [], "ninguno"
