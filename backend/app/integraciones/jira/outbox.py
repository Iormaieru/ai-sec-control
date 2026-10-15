"""Encolado de cambios para Jira. Lo llaman los servicios de casos dentro de
su propia transacción (no hace commit): el cambio y su entrada en la outbox
se guardan juntos o no se guarda ninguno."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casos.models import Caso, JiraSyncEstado
from app.integraciones.jira.models import JiraOutbox, OperacionJira


def pendientes(db: Session, caso_id: uuid.UUID) -> list[JiraOutbox]:
    return list(
        db.scalars(
            select(JiraOutbox)
            .where(JiraOutbox.caso_id == caso_id, JiraOutbox.procesado_at.is_(None))
            .order_by(JiraOutbox.created_at)
        )
    )


def encolar(db: Session, caso: Caso, operacion: OperacionJira, comentario_id: uuid.UUID | None = None) -> None:
    if operacion == OperacionJira.ACTUALIZAR_ISSUE:
        # La creación y la actualización mandan los valores actuales del caso
        # al momento de empujar: si ya hay una pendiente, alcanza con esa.
        en_cola = {op.operacion for op in pendientes(db, caso.id) if not op.descartada}
        if en_cola & {OperacionJira.CREAR_ISSUE, OperacionJira.ACTUALIZAR_ISSUE}:
            return
    db.add(JiraOutbox(caso_id=caso.id, comentario_id=comentario_id, operacion=operacion, intentos=0, descartada=False))
    caso.jira_sync_estado = JiraSyncEstado.PENDIENTE
