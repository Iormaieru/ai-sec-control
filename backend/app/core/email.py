"""Envío de emails. Sin dependencias nuevas (smtplib de la stdlib).

Backends (AISEC_EMAIL_BACKEND):
- "console": no envía; deja un log con destinatario y asunto. Es el default
  para que un ambiente sin SMTP configurado no falle al invitar.
- "smtp": envía por el relay de AISEC_SMTP_HOST/PORT, con STARTTLS y login
  opcionales.

El cuerpo nunca se loguea: lleva el enlace con el token del cuestionario.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailNoEnviado(Exception):
    pass


def send_email(*, to: str, subject: str, text: str, html: str) -> None:
    settings = get_settings()

    if settings.email_backend == "console":
        logger.info("Email no enviado (backend console)", extra={"email_to": to, "email_subject": subject})
        return

    if settings.email_backend != "smtp":
        raise EmailNoEnviado(f"AISEC_EMAIL_BACKEND desconocido: {settings.email_backend!r}")
    if not settings.smtp_host:
        raise EmailNoEnviado("AISEC_SMTP_HOST no está configurado")

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("Falló el envío de email", extra={"email_to": to, "error": type(exc).__name__})
        raise EmailNoEnviado(f"No se pudo enviar el email a {to}") from exc
