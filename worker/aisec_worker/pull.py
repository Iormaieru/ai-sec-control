"""Jira -> plataforma: trae los tickets del tablero IA-SEC que cambiaron.

Jira no avisa (no hay webhook), así que el worker pregunta cada
AISEC_JIRA_SYNC_INTERVALO_SEGUNDOS por los tickets actualizados desde la
última corrida exitosa (jira_sync_cursor; la primera vez, todos) y los
aplica con la misma lógica que usa el backend (sync.aplicar_issue).
"""

import math
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.integraciones.jira.client import JiraClient, JiraError
from app.integraciones.jira.models import JiraSyncCursor
from app.integraciones.jira.sync import PROP_CASO, ahora, aplicar_issue, campos_issue, jql_base, tablero


@dataclass
class ResultadoPull:
    nuevos: int = 0
    actualizados: int = 0
    errores: list[str] = field(default_factory=list)


def pull(db: Session, client: JiraClient) -> ResultadoPull:
    filtro_id, mapa = tablero(client)
    cursor = db.get(JiraSyncCursor, 1) or JiraSyncCursor(id=1)
    inicio = ahora()

    jql = jql_base(client, filtro_id)
    if cursor.ultimo_poll_at is not None:
        # Relativo en minutos: el JQL con fecha absoluta se interpreta en la
        # zona horaria del usuario de Jira. 2 minutos de margen por relojes.
        minutos = math.ceil((inicio - cursor.ultimo_poll_at).total_seconds() / 60) + 2
        jql += f" AND updated >= -{minutos}m"
    jql += " ORDER BY updated ASC"

    resultado = ResultadoPull()
    for issue in client.search_jql(jql, campos_issue(client), properties=[PROP_CASO]):
        try:
            nuevo = aplicar_issue(db, client, issue, mapa)
            db.commit()
        except JiraError as exc:
            db.rollback()
            resultado.errores.append(f"{issue.get('key')}: {exc}")
            continue
        if nuevo is True:
            resultado.nuevos += 1
        elif nuevo is False:
            resultado.actualizados += 1

    # Si algún ticket falló no se avanza el cursor: la próxima corrida lo vuelve a traer.
    if not resultado.errores:
        cursor.ultimo_poll_at = inicio
        db.add(cursor)
        db.commit()
    return resultado
