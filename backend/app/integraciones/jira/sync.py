"""Integración con Jira del lado del backend.

El backend no sincroniza en segundo plano: cada cambio hecho en la plataforma
queda como evento en jira_outbox (ver outbox.py) y lo envía el worker
(worker/). Acá queda lo que ocurre dentro de un request:

- acciones en vivo que el usuario elige entre lo que ofrece Jira:
  transiciones y asignación;
- aplicar un ticket de Jira a su caso (aplicar_issue / pull_issue), que usan
  el webhook, las acciones en vivo y el pull periódico del worker;
- reintentar las operaciones fallidas de un caso.

Lo que llega de Jira nunca se encola, así que no hay ecos. Para no duplicar
lo creado desde la plataforma, el ticket y los comentarios que se crean
llevan una propiedad con el id local (aisec.caso_id / aisec.comentario_id).
"""

import datetime as dt
import re
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.casos.models import Caso, CasoComentario, CasoEstado, JiraSyncEstado, Origen
from app.core.config import get_settings
from app.integraciones.jira import mapping
from app.integraciones.jira.client import ISSUE_FIELDS, JiraClient
from app.integraciones.jira.models import OperacionJira
from app.integraciones.jira.outbox import notificar, pendientes

PROP_CASO = "aisec.caso_id"
PROP_COMENTARIO = "aisec.comentario_id"
_RE_ISSUE_KEY = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_RE_GDLD_EN_RESUMEN = re.compile(r"GDLD[\s\-_]*(\d+)", re.IGNORECASE)


def prop_id(id_: uuid.UUID) -> dict:
    # Jira sólo acepta objetos JSON como valor de una propiedad de comentario.
    return {"id": str(id_)}


def _uuid_de_prop(valor: object) -> uuid.UUID | None:
    if isinstance(valor, dict):
        valor = valor.get("id")
    try:
        return uuid.UUID(str(valor))
    except ValueError:
        return None


class JiraDeshabilitada(Exception):
    pass


def crear_cliente() -> JiraClient:
    """Punto único de creación del cliente (los tests lo reemplazan)."""
    if not get_settings().jira_enabled:
        raise JiraDeshabilitada("La integración con Jira está deshabilitada (AISEC_JIRA_ENABLED)")
    return JiraClient()


def ahora() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# --- configuración del tablero (filtro y columnas), cacheada ---

_TABLERO_TTL_SEGUNDOS = 600
_tablero_cache: dict[int, tuple[float, str, dict[str, CasoEstado]]] = {}


def tablero(client: JiraClient) -> tuple[str, dict[str, CasoEstado]]:
    """(id del filtro, status id -> columna) del tablero IA-SEC."""
    board_id = client.settings.jira_board_id
    cacheado = _tablero_cache.get(board_id)
    if cacheado and time.monotonic() - cacheado[0] < _TABLERO_TTL_SEGUNDOS:
        return cacheado[1], cacheado[2]
    config = client.get_board_configuration(board_id)
    filtro_id = str(config["filter"]["id"])
    mapa = mapping.estados_por_status(config)
    _tablero_cache[board_id] = (time.monotonic(), filtro_id, mapa)
    return filtro_id, mapa


def jql_base(client: JiraClient, filtro_id: str) -> str:
    # El filtro del tablero también trae subtareas: sólo las Solicitudes son casos.
    return f"filter = {filtro_id} AND issuetype = {client.settings.jira_issue_type_id}"


def campos_issue(client: JiraClient) -> list[str]:
    s = client.settings
    return [*ISSUE_FIELDS, s.jira_gdld_field, s.jira_request_type_field]


# --- aplicar tickets de Jira a casos (lo usan el webhook, las acciones en vivo y el worker) ---


def pull_issue(db: Session, client: JiraClient, issue_key: str) -> Caso | None:
    """Trae un ticket puntual (webhook, después de una transición). Devuelve
    None si el ticket no es del tablero IA-SEC."""
    if not _RE_ISSUE_KEY.match(issue_key):
        raise ValueError(f"Clave de ticket inválida: {issue_key!r}")
    filtro_id, mapa = tablero(client)
    jql = f'{jql_base(client, filtro_id)} AND key = "{issue_key}"'
    issues = client.search_jql(jql, campos_issue(client), properties=[PROP_CASO])
    if not issues:
        return None
    aplicar_issue(db, client, issues[0], mapa)
    db.commit()
    return db.scalar(select(Caso).where(Caso.jira_issue_id == str(issues[0]["id"])))


def aplicar_issue(db: Session, client: JiraClient, issue: dict, mapa: dict[str, CasoEstado]) -> bool | None:
    """Aplica un ticket al caso que le corresponde (creándolo si no existe).
    Devuelve True si creó el caso, False si lo actualizó, None si no había
    nada nuevo. No hace commit."""
    s = client.settings
    campos = issue["fields"]
    issue_id = str(issue["id"])
    actualizado_en = mapping.fecha_jira(campos["updated"])

    caso = db.scalar(select(Caso).where(Caso.jira_issue_id == issue_id))
    if caso is None:
        caso = _caso_por_propiedad(db, issue)
    nuevo = caso is None
    if caso is None:
        caso = Caso(origen=Origen.JIRA, jira_issue_id=issue_id, jira_sync_estado=JiraSyncEstado.OK)
        db.add(caso)
    elif caso.jira_updated_at is not None and actualizado_en <= caso.jira_updated_at and caso.jira_issue_id:
        return None

    caso.jira_issue_id = issue_id
    caso.jira_issue_key = issue["key"]
    caso.jira_updated_at = actualizado_en
    status = campos["status"]
    caso.estado = mapping.estado_de_status(status, mapa)
    caso.jira_status_id = str(status["id"])
    caso.jira_status_nombre = status["name"]
    asignado = campos.get("assignee") or {}
    caso.jira_asignado_id = asignado.get("accountId")
    caso.jira_asignado_nombre = (asignado.get("displayName") or "")[:200] or None
    caso.jira_asignado_avatar_url = _avatar(asignado)
    tipo_solicitud = ((campos.get(s.jira_request_type_field) or {}).get("requestType") or {}).get("id")
    if tipo_solicitud:
        caso.jira_tipo_solicitud_id = str(tipo_solicitud)

    # Último cambio gana: si hay una edición local sin empujar, es más nueva
    # que lo que hay en Jira y va a pisarlo; si no, manda Jira.
    edicion_local = any(
        op.operacion in (OperacionJira.CREAR_ISSUE, OperacionJira.ACTUALIZAR_ISSUE) and not op.descartada
        for op in (pendientes(db, caso.id) if not nuevo else [])
    )
    if not edicion_local:
        resumen = campos.get("summary") or issue["key"]
        nombre = mapping.nombre_desde_resumen(resumen)[:255]
        if caso.nombre_proyecto != nombre:
            caso.nombre_proyecto = nombre
        gdld = mapping.gdld_desde_jira(campos.get(s.jira_gdld_field))
        if gdld is None and (m := _RE_GDLD_EN_RESUMEN.search(resumen)):
            gdld = m.group(1)
        if caso.gdld != gdld:
            caso.gdld = gdld

    db.flush()
    _importar_comentarios(db, client, caso)
    return nuevo


def _caso_por_propiedad(db: Session, issue: dict) -> Caso | None:
    """Un ticket creado desde la plataforma cuyo id todavía no se guardó (el
    pull le ganó a la respuesta del push)."""
    caso_id = _uuid_de_prop((issue.get("properties") or {}).get(PROP_CASO))
    if caso_id is None:
        return None
    caso = db.get(Caso, caso_id)
    return caso if caso is not None and caso.jira_issue_id is None else None


def _importar_comentarios(db: Session, client: JiraClient, caso: Caso) -> None:
    conocidos = set(
        db.scalars(select(CasoComentario.jira_comment_id).where(CasoComentario.caso_id == caso.id))
    )
    for c in client.get_comments(caso.jira_issue_key):
        comment_id = str(c["id"])
        if comment_id in conocidos:
            continue
        propiedades = {p["key"]: p.get("value") for p in c.get("properties", [])}
        local = _comentario_local(db, propiedades.get(PROP_COMENTARIO))
        if local is not None:
            local.jira_comment_id = comment_id
            continue
        interno = (propiedades.get("sd.public.comment") or {}).get("internal")
        db.add(
            CasoComentario(
                caso_id=caso.id,
                cuerpo=mapping.adf_a_texto(c.get("body")) or "(sin texto)",
                autor_nombre=((c.get("author") or {}).get("displayName") or "Jira")[:200],
                origen=Origen.JIRA,
                publico=c.get("jsdPublic", not interno),
                jira_comment_id=comment_id,
                fecha=mapping.fecha_jira(c["created"]),
            )
        )
    db.flush()


def _comentario_local(db: Session, valor: object) -> CasoComentario | None:
    comentario_id = _uuid_de_prop(valor)
    if comentario_id is None:
        return None
    comentario = db.get(CasoComentario, comentario_id)
    return comentario if comentario is not None and comentario.jira_comment_id is None else None


def reintentar(db: Session, caso: Caso) -> None:
    """Vuelve a poner en cola, para ya, las operaciones fallidas del caso."""
    for op in pendientes(db, caso.id):
        op.descartada = False
        op.proximo_intento_at = ahora()
    caso.jira_sync_estado = JiraSyncEstado.PENDIENTE
    caso.jira_sync_error = None
    notificar(db, caso.id)
    db.commit()


# --- transiciones (sincrónicas: requieren Jira disponible) ---


@dataclass
class Transicion:
    id: str
    nombre: str
    destino: str
    estado: CasoEstado


def transiciones(client: JiraClient, caso: Caso) -> list[Transicion]:
    _, mapa = tablero(client)
    return [
        Transicion(
            id=str(t["id"]),
            nombre=t["name"],
            destino=t["to"]["name"],
            estado=mapping.estado_de_status(t["to"], mapa),
        )
        for t in client.get_transitions(caso.jira_issue_key)
    ]


def transicionar(db: Session, client: JiraClient, caso: Caso, transition_id: str) -> Caso:
    client.transition_issue(caso.jira_issue_key, transition_id)
    # Se relee el ticket para tomar el status real (y lo que haya cambiado).
    caso.jira_updated_at = None
    db.flush()
    pull_issue(db, client, caso.jira_issue_key)
    return caso


# --- asignación (sincrónica, igual que las transiciones) ---


@dataclass
class PersonaJira:
    account_id: str
    nombre: str
    avatar_url: str | None


def _avatar(usuario: dict) -> str | None:
    """Foto de perfil (CDN de Atlassian o Gravatar). Sólo https, para que el
    navegador la cargue tal cual."""
    url = (usuario.get("avatarUrls") or {}).get("48x48") or ""
    return url if url.startswith("https://") and len(url) <= 500 else None


def asignables(client: JiraClient, caso: Caso, query: str) -> list[PersonaJira]:
    return [
        PersonaJira(account_id=u["accountId"], nombre=u.get("displayName") or u["accountId"], avatar_url=_avatar(u))
        for u in client.search_assignable(caso.jira_issue_key, query)
        if u.get("accountType", "atlassian") == "atlassian" and u.get("active", True)
    ]


def equipo(db: Session) -> list[PersonaJira]:
    """Quienes ya tienen casos asignados, los más frecuentes primero: el
    atajo para asignar sin buscar entre todo el proyecto MDA."""
    filas = db.execute(
        select(Caso.jira_asignado_id, Caso.jira_asignado_nombre, Caso.jira_asignado_avatar_url, func.count())
        .where(Caso.jira_asignado_id.is_not(None))
        .group_by(Caso.jira_asignado_id, Caso.jira_asignado_nombre, Caso.jira_asignado_avatar_url)
        .order_by(func.count().desc(), Caso.jira_asignado_nombre)
    ).all()
    personas: dict[str, PersonaJira] = {}
    for account_id, nombre, avatar_url, _ in filas:
        personas.setdefault(account_id, PersonaJira(account_id=account_id, nombre=nombre, avatar_url=avatar_url))
    return list(personas.values())


def asignar(db: Session, client: JiraClient, caso: Caso, account_id: str | None) -> Caso:
    client.assign_issue(caso.jira_issue_key, account_id)
    # Se relee el ticket: nombre y foto del asignado salen de Jira.
    caso.jira_updated_at = None
    db.flush()
    pull_issue(db, client, caso.jira_issue_key)
    return caso
