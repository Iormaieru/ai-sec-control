"""Aviso por email de las alertas nuevas o reincidentes: un solo resumen por
vuelta a los destinatarios cargados en la plataforma (o, si no hay ninguno, a
AISEC_ALERTAS_EMAIL_DESTINO; ver app.alertas.destinatarios)."""

import datetime as dt
import html
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alertas.destinatarios import destinatarios
from app.alertas.models import Alerta, EstadoAlerta, ReglaAlerta
from app.core.config import Settings
from app.core.email import EmailNoEnviado, send_email

logger = logging.getLogger(__name__)

_ORDEN_SEVERIDAD = {"critica": 0, "alta": 1, "media": 2, "baja": 3}


def _fecha(valor: dt.datetime) -> str:
    return valor.strftime("%d/%m/%Y %H:%M UTC")


def _cuando(a: Alerta) -> str:
    eventos = f"{a.cantidad_eventos} evento{'s' if a.cantidad_eventos != 1 else ''}"
    if _fecha(a.primera_vez) == _fecha(a.ultima_vez):  # mismo minuto
        return f"{eventos} el {_fecha(a.ultima_vez)}"
    return f"{eventos} entre {_fecha(a.primera_vez)} y {_fecha(a.ultima_vez)}"


def armar_email(alertas: list[Alerta], base_url: str) -> tuple[str, str, str]:
    """(asunto, texto, html) del resumen."""
    n = len(alertas)
    asunto = f"[AI-SEC] {n} alerta{'s' if n != 1 else ''} nueva{'s' if n != 1 else ''} de Netskope"
    lineas, filas = [], []
    for a in alertas:
        enlace = f"{base_url.rstrip('/')}/alertas?alerta={a.id}"
        actividades = ", ".join(f"{k} ×{v}" for k, v in sorted(a.actividades.items(), key=lambda kv: -kv[1])[:5])
        lineas.append(
            f"- [{a.severidad.value.upper()}] {a.regla.nombre}: {a.app} — {a.usuario}\n"
            f"  {_cuando(a)} ({actividades})\n"
            f"  {enlace}"
        )
        filas.append(
            "<tr>"
            f"<td><strong>{html.escape(a.severidad.value.upper())}</strong></td>"
            f"<td>{html.escape(a.regla.nombre)}</td>"
            f"<td>{html.escape(a.app)}</td>"
            f"<td>{html.escape(a.usuario)}</td>"
            f"<td>{a.cantidad_eventos}<br><small>{html.escape(actividades)}</small></td>"
            f"<td>{html.escape(_cuando(a))}</td>"
            f'<td><a href="{html.escape(enlace)}">Ver</a></td>'
            "</tr>"
        )
    texto = "Netskope registró actividad que coincide con reglas de AI-SEC:\n\n" + "\n\n".join(lineas)
    cuerpo = (
        "<p>Netskope registró actividad que coincide con reglas de AI-SEC:</p>"
        '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px">'
        "<tr><th>Severidad</th><th>Regla</th><th>App</th><th>Usuario</th><th>Eventos</th><th>Cuándo</th><th></th></tr>"
        + "".join(filas)
        + "</table>"
    )
    return asunto, texto, cuerpo


def notificar(db: Session, settings: Settings, ahora: dt.datetime | None = None) -> int:
    """Envía el resumen y devuelve cuántas alertas avisó. Si el email falla,
    las alertas quedan pendientes y se reintenta en la próxima vuelta."""
    ahora = ahora or dt.datetime.now(dt.UTC)
    pendientes = db.scalars(
        select(Alerta).join(ReglaAlerta, Alerta.regla_id == ReglaAlerta.id).where(Alerta.por_notificar.is_(True))
    ).all()
    # Las de reglas sin aviso, o que ya no están nuevas, no se mandan.
    a_avisar = [a for a in pendientes if a.regla.notificar_email and a.estado == EstadoAlerta.NUEVA]
    for a in pendientes:
        if a not in a_avisar:
            a.por_notificar = False
    if not a_avisar:
        db.commit()
        return 0

    destinos, _origen = destinatarios(db, settings)
    if not destinos:
        logger.warning(
            "Hay alertas para avisar pero no hay destinatarios (ni en la plataforma ni en AISEC_ALERTAS_EMAIL_DESTINO)",
            extra={"alertas": len(a_avisar)},
        )
        db.commit()
        return 0

    a_avisar.sort(key=lambda a: (_ORDEN_SEVERIDAD[a.severidad.value], a.app, a.usuario))
    asunto, texto, cuerpo = armar_email(a_avisar, settings.frontend_base_url)
    try:
        for destino in destinos:
            send_email(to=destino, subject=asunto, text=texto, html=cuerpo)
    except EmailNoEnviado:
        logger.warning("No se pudo enviar el resumen de alertas; se reintenta en la próxima vuelta", extra={"alertas": len(a_avisar)})
        db.rollback()
        return 0
    for a in a_avisar:
        a.por_notificar = False
        a.notificada_at = ahora
    db.commit()
    return len(a_avisar)
