import hashlib
import html
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casos.models import Caso, Contacto
from app.catalog.models import Dominio, Pregunta
from app.core.config import get_settings
from app.core.email import send_email
from app.cuestionarios.models import CuestionarioInvitacion, InvitacionEstado
from app.cuestionarios.schemas import (
    EnvioResultadoOut,
    FormularioOut,
    InvitacionOut,
    PreguntaFormularioOut,
    RespuestaFormulario,
)
from app.threat_model.enums import RespuestaValor
from app.threat_model.models import CasoPregunta, CasoRespuesta

_ACTIVAS = (InvitacionEstado.ENVIADA, InvitacionEstado.ABIERTA)


class CuestionarioError(Exception):
    pass


class ContactoInvalido(CuestionarioError):
    pass


class CasoSinPreguntas(CuestionarioError):
    pass


class PreguntaFueraDeAlcance(CuestionarioError):
    pass


class InvitacionNoVigente(CuestionarioError):
    pass


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_vencida(invitacion: CuestionarioInvitacion) -> bool:
    return invitacion.expira_at <= _now()


def to_invitacion_out(invitacion: CuestionarioInvitacion, enlace: str | None = None) -> InvitacionOut:
    return InvitacionOut(
        id=invitacion.id,
        contacto_id=invitacion.contacto_id,
        contacto_nombre=invitacion.contacto.nombre,
        email=invitacion.email,
        estado=invitacion.estado,
        vencida=invitacion.estado in _ACTIVAS and is_vencida(invitacion),
        created_at=invitacion.created_at,
        expira_at=invitacion.expira_at,
        abierta_at=invitacion.abierta_at,
        respondida_at=invitacion.respondida_at,
        enlace=enlace,
    )


# --- Lado del analista ---


def enviar_cuestionario(db: Session, caso: Caso, contacto_ids: list[uuid.UUID]) -> list[InvitacionOut]:
    """Crea una invitación por contacto y le manda el enlace por email.

    Reenviar a un contacto anula su invitación anterior todavía activa: el
    enlace viejo deja de funcionar. Cada contacto se confirma por separado,
    así que si falla el email del tercero, los dos primeros quedan enviados.
    """
    contactos = {c.id: c for c in caso.contactos}
    for contacto_id in contacto_ids:
        contacto = contactos.get(contacto_id)
        if contacto is None:
            raise ContactoInvalido("El contacto no pertenece a este caso")
        if not contacto.email:
            raise ContactoInvalido(f"El contacto {contacto.nombre} no tiene email")

    hay_preguntas = db.scalar(select(CasoPregunta.id).where(CasoPregunta.caso_id == caso.id).limit(1))
    if hay_preguntas is None:
        raise CasoSinPreguntas("El caso no tiene preguntas en alcance para enviar")

    settings = get_settings()
    resultado = []
    for contacto_id in dict.fromkeys(contacto_ids):
        contacto = contactos[contacto_id]
        for anterior in db.scalars(
            select(CuestionarioInvitacion).where(
                CuestionarioInvitacion.caso_id == caso.id,
                CuestionarioInvitacion.contacto_id == contacto.id,
                CuestionarioInvitacion.estado.in_(_ACTIVAS),
            )
        ):
            anterior.estado = InvitacionEstado.ANULADA

        token = secrets.token_urlsafe(32)
        invitacion = CuestionarioInvitacion(
            caso_id=caso.id,
            contacto_id=contacto.id,
            email=contacto.email,
            token_hash=hash_token(token),
            estado=InvitacionEstado.ENVIADA,
            expira_at=_now() + timedelta(days=settings.cuestionario_validez_dias),
        )
        db.add(invitacion)
        db.flush()

        enlace = f"{settings.frontend_base_url.rstrip('/')}/cuestionario/{token}"
        try:
            _send_invitacion_email(caso, contacto, invitacion, enlace)
        except Exception:
            db.rollback()
            raise
        db.commit()
        db.refresh(invitacion)
        resultado.append(
            to_invitacion_out(invitacion, enlace=enlace if settings.email_backend == "console" else None)
        )
    return resultado


def _send_invitacion_email(
    caso: Caso, contacto: Contacto, invitacion: CuestionarioInvitacion, enlace: str
) -> None:
    vence = invitacion.expira_at.strftime("%d/%m/%Y")
    subject = f"Cuestionario de seguridad de IA — {caso.nombre_proyecto}"
    text = (
        f"Hola {contacto.nombre}:\n\n"
        f"Te pedimos completar el cuestionario de modelado de amenazas del proyecto "
        f"{caso.nombre_proyecto} ({caso.empresa_responsable}).\n\n"
        f"Completalo desde este enlace (vence el {vence}):\n{enlace}\n\n"
        "Podés guardar y continuar más tarde. El enlace es personal: no lo reenvíes.\n"
    )
    nombre = html.escape(contacto.nombre)
    proyecto = html.escape(caso.nombre_proyecto)
    empresa = html.escape(caso.empresa_responsable)
    body_html = f"""\
<p>Hola {nombre}:</p>
<p>Te pedimos completar el cuestionario de modelado de amenazas del proyecto
<strong>{proyecto}</strong> ({empresa}).</p>
<p><a href="{html.escape(enlace)}" style="display:inline-block;padding:10px 18px;background:#0d6efd;\
color:#fff;text-decoration:none;border-radius:6px">Completar cuestionario</a></p>
<p>El enlace vence el {vence}. Podés guardar y continuar más tarde.<br>
Es personal: no lo reenvíes.</p>
"""
    send_email(to=invitacion.email, subject=subject, text=text, html=body_html)


def list_invitaciones(db: Session, caso: Caso) -> list[InvitacionOut]:
    invitaciones = db.scalars(
        select(CuestionarioInvitacion)
        .where(CuestionarioInvitacion.caso_id == caso.id)
        .order_by(CuestionarioInvitacion.created_at.desc())
    )
    return [to_invitacion_out(i) for i in invitaciones]


# --- Lado del contacto (formulario público) ---


def get_invitacion_por_token(db: Session, token: str) -> CuestionarioInvitacion | None:
    return db.scalar(select(CuestionarioInvitacion).where(CuestionarioInvitacion.token_hash == hash_token(token)))


def verificar_vigente(invitacion: CuestionarioInvitacion) -> None:
    if invitacion.estado == InvitacionEstado.RESPONDIDA:
        raise InvitacionNoVigente("Este cuestionario ya fue enviado. ¡Gracias!")
    if invitacion.estado == InvitacionEstado.ANULADA:
        raise InvitacionNoVigente("Este enlace fue reemplazado por uno más nuevo. Revisá tu último email.")
    if is_vencida(invitacion):
        raise InvitacionNoVigente("Este enlace venció. Pedile al equipo de seguridad que te lo reenvíe.")


def _rows_pendientes(db: Session, caso_id: uuid.UUID):
    """Preguntas del caso que el equipo todavía no respondió: son las únicas
    que ve el contacto (no se pisan respuestas cargadas por el analista)."""
    return db.execute(
        select(CasoRespuesta, Pregunta, Dominio)
        .join(CasoPregunta, CasoRespuesta.caso_pregunta_id == CasoPregunta.id)
        .join(Pregunta, CasoPregunta.pregunta_id == Pregunta.id)
        .join(Dominio, Pregunta.dominio_id == Dominio.id)
        .where(CasoPregunta.caso_id == caso_id, CasoRespuesta.respuesta == RespuestaValor.PENDIENTE)
        .order_by(Dominio.codigo, Pregunta.numero)
    ).all()


def get_formulario(db: Session, invitacion: CuestionarioInvitacion) -> FormularioOut:
    if invitacion.estado == InvitacionEstado.ENVIADA:
        invitacion.estado = InvitacionEstado.ABIERTA
        invitacion.abierta_at = _now()
        db.commit()

    borrador = invitacion.borrador or {}
    preguntas = []
    for respuesta, pregunta, dominio in _rows_pendientes(db, invitacion.caso_id):
        guardada = borrador.get(str(pregunta.id), {})
        preguntas.append(
            PreguntaFormularioOut(
                pregunta_id=pregunta.id,
                dominio_codigo=dominio.codigo,
                dominio_nombre=dominio.nombre,
                numero=pregunta.numero,
                texto_es=pregunta.texto_es,
                explicacion_es=pregunta.explicacion_control_es,
                instrucciones_es=respuesta.instrucciones_respuesta_es,
                evidencia_esperada=respuesta.evidencia_esperada,
                respuesta=guardada.get("respuesta", RespuestaValor.PENDIENTE),
                comentario=guardada.get("comentario"),
            )
        )

    caso = invitacion.caso
    return FormularioOut(
        nombre_proyecto=caso.nombre_proyecto,
        empresa_responsable=caso.empresa_responsable,
        contacto_nombre=invitacion.contacto.nombre,
        expira_at=invitacion.expira_at,
        preguntas=preguntas,
    )


def _validar_alcance(db: Session, caso_id: uuid.UUID, respuestas: list[RespuestaFormulario]) -> None:
    en_alcance = set(db.scalars(select(CasoPregunta.pregunta_id).where(CasoPregunta.caso_id == caso_id)))
    if any(r.pregunta_id not in en_alcance for r in respuestas):
        raise PreguntaFueraDeAlcance("Alguna de las preguntas no pertenece a este cuestionario")


def _to_borrador(respuestas: list[RespuestaFormulario]) -> dict:
    return {
        str(r.pregunta_id): {"respuesta": r.respuesta.value, "comentario": (r.comentario or "").strip() or None}
        for r in respuestas
    }


def guardar_borrador(db: Session, invitacion: CuestionarioInvitacion, respuestas: list[RespuestaFormulario]) -> None:
    _validar_alcance(db, invitacion.caso_id, respuestas)
    invitacion.borrador = _to_borrador(respuestas)
    if invitacion.estado == InvitacionEstado.ENVIADA:
        invitacion.estado = InvitacionEstado.ABIERTA
        invitacion.abierta_at = _now()
    db.commit()


def enviar_respuestas(
    db: Session, invitacion: CuestionarioInvitacion, respuestas: list[RespuestaFormulario]
) -> EnvioResultadoOut:
    """Aplica las respuestas al caso y cierra la invitación.

    Sólo toca preguntas que siguen PENDIENTE: si el analista respondió una
    mientras el contacto completaba el formulario, gana la del analista. El
    comentario se agrega a observaciones (no las reemplaza), firmado con el
    nombre del contacto.
    """
    _validar_alcance(db, invitacion.caso_id, respuestas)

    filas = {
        pregunta_id: respuesta
        for respuesta, pregunta_id in db.execute(
            select(CasoRespuesta, CasoPregunta.pregunta_id)
            .join(CasoPregunta, CasoRespuesta.caso_pregunta_id == CasoPregunta.id)
            .where(CasoPregunta.caso_id == invitacion.caso_id)
        )
    }

    firma = f"[{invitacion.contacto.nombre}, cuestionario {_now().strftime('%d/%m/%Y')}]"
    aplicadas = omitidas = 0
    for item in respuestas:
        comentario = (item.comentario or "").strip()
        if item.respuesta == RespuestaValor.PENDIENTE and not comentario:
            continue
        fila = filas[item.pregunta_id]
        if fila.respuesta != RespuestaValor.PENDIENTE:
            omitidas += 1
            continue
        fila.respuesta = item.respuesta
        if comentario:
            nota = f"{firma} {comentario}"
            fila.observaciones = f"{fila.observaciones}\n\n{nota}" if fila.observaciones else nota
        aplicadas += 1

    invitacion.borrador = _to_borrador(respuestas)
    invitacion.estado = InvitacionEstado.RESPONDIDA
    invitacion.respondida_at = _now()
    invitacion.abierta_at = invitacion.abierta_at or invitacion.respondida_at
    db.commit()
    return EnvioResultadoOut(aplicadas=aplicadas, omitidas=omitidas)
