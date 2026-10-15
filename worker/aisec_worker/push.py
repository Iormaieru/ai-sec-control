"""Plataforma -> Jira: procesa los eventos de jira_outbox.

Los eventos de un caso salen en orden: si uno no puede salir, los siguientes
del mismo caso esperan. Un error transitorio (red, 429, 5xx) se reintenta con
backoff; un 4xx descarta el evento y deja el caso en error hasta que alguien
pulse "Reintentar" en la plataforma.
"""

import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casos.models import Caso, CasoComentario, JiraSyncEstado
from app.integraciones.jira import mapping
from app.integraciones.jira.client import JiraClient, JiraError
from app.integraciones.jira.models import JiraOutbox, OperacionJira
from app.integraciones.jira.outbox import pendientes
from app.integraciones.jira.sync import PROP_CASO, PROP_COMENTARIO, ahora, prop_id

logger = logging.getLogger(__name__)


@dataclass
class ResultadoPush:
    enviados: int = 0
    errores: list[str] = field(default_factory=list)


def _backoff(intentos: int) -> dt.timedelta:
    return dt.timedelta(seconds=min(60 * 2 ** (intentos - 1), 3600))


def push(db: Session, client: JiraClient, caso_id: uuid.UUID | None = None) -> ResultadoPush:
    stmt = select(JiraOutbox).where(JiraOutbox.procesado_at.is_(None)).order_by(JiraOutbox.created_at)
    if caso_id is not None:
        stmt = stmt.where(JiraOutbox.caso_id == caso_id)
    resultado = ResultadoPush()
    bloqueados: set[uuid.UUID] = set()
    momento = ahora()

    for op in db.scalars(stmt).all():
        if op.caso_id in bloqueados:
            continue
        if op.descartada or op.proximo_intento_at > momento:
            bloqueados.add(op.caso_id)
            continue
        caso = db.get(Caso, op.caso_id)
        try:
            _ejecutar(db, client, op, caso)
        except JiraError as exc:
            op.intentos += 1
            op.ultimo_error = str(exc)
            if exc.transitorio:
                op.proximo_intento_at = momento + _backoff(op.intentos)
            else:
                op.descartada = True
            caso.jira_sync_estado = JiraSyncEstado.ERROR
            caso.jira_sync_error = _mensaje_error(op, exc)
            bloqueados.add(op.caso_id)
            resultado.errores.append(f"{caso.id} {op.operacion.value}: {exc}")
            logger.warning(
                "Falló el envío a Jira",
                extra={"caso_id": str(caso.id), "operacion": op.operacion.value, "status": exc.status_code},
            )
        else:
            op.procesado_at = momento
            op.ultimo_error = None
            resultado.enviados += 1
            _recalcular_estado_sync(db, caso)
            logger.info(
                "Evento enviado a Jira",
                extra={"caso_id": str(caso.id), "operacion": op.operacion.value, "issue": caso.jira_issue_key},
            )
        db.commit()
    return resultado


def _ejecutar(db: Session, client: JiraClient, op: JiraOutbox, caso: Caso) -> None:
    s = client.settings
    if op.operacion == OperacionJira.CREAR_ISSUE:
        if caso.jira_issue_id:
            return  # ya vinculado (lo encontró un pull por la propiedad)
        campos: dict = {
            "project": {"key": s.jira_project_key},
            "issuetype": {"id": s.jira_issue_type_id},
            "summary": mapping.formatear_resumen(caso.nombre_proyecto, caso.gdld),
            s.jira_request_type_field: caso.jira_tipo_solicitud_id or next(iter(s.jira_request_types)),
        }
        if caso.gdld:
            campos[s.jira_gdld_field] = mapping.gdld_a_jira(caso.gdld)
        creado = client.create_issue(campos, properties={PROP_CASO: prop_id(caso.id)})
        caso.jira_issue_id = str(creado["id"])
        caso.jira_issue_key = creado["key"]
        db.flush()

    elif op.operacion == OperacionJira.ACTUALIZAR_ISSUE:
        if not caso.jira_issue_key:
            raise JiraError("El ticket todavía no existe en Jira", status_code=409)
        client.update_issue(
            caso.jira_issue_key,
            {
                "summary": mapping.formatear_resumen(caso.nombre_proyecto, caso.gdld),
                s.jira_gdld_field: mapping.gdld_a_jira(caso.gdld),
            },
        )

    elif op.operacion == OperacionJira.CREAR_COMENTARIO:
        comentario = db.get(CasoComentario, op.comentario_id) if op.comentario_id else None
        if comentario is None or comentario.jira_comment_id:
            return
        if not caso.jira_issue_key:
            raise JiraError("El ticket todavía no existe en Jira", status_code=409)
        cuerpo = f"[AI-SEC Control – {comentario.autor_nombre}]\n{comentario.cuerpo}"
        creado = client.add_internal_comment(
            caso.jira_issue_key, mapping.texto_a_adf(cuerpo), properties={PROP_COMENTARIO: prop_id(comentario.id)}
        )
        comentario.jira_comment_id = str(creado["id"])
        db.flush()


_DESCRIPCION_OP = {
    OperacionJira.CREAR_ISSUE: "crear el ticket",
    OperacionJira.ACTUALIZAR_ISSUE: "actualizar el ticket",
    OperacionJira.CREAR_COMENTARIO: "publicar un comentario",
}


def _mensaje_error(op: JiraOutbox, exc: JiraError) -> str:
    cuando = "se reintenta automáticamente" if exc.transitorio else "Jira lo rechazó"
    return f"No se pudo {_DESCRIPCION_OP[op.operacion]} en Jira ({cuando}): {exc}"[:2000]


def _recalcular_estado_sync(db: Session, caso: Caso) -> None:
    db.flush()
    restantes = pendientes(db, caso.id)
    if not restantes:
        caso.jira_sync_estado = JiraSyncEstado.OK
        caso.jira_sync_error = None
    elif any(op.descartada or op.ultimo_error for op in restantes):
        caso.jira_sync_estado = JiraSyncEstado.ERROR
    else:
        caso.jira_sync_estado = JiraSyncEstado.PENDIENTE
