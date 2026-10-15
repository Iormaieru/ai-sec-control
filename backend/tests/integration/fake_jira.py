"""Jira falso en memoria (FakeJira) y helpers compartidos por los tests de la
integración: los del backend (tests/integration/test_jira_*.py) y los del
worker (worker/tests). Nada sale a la red."""

import datetime as dt
import itertools
import re
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.casos.models import Caso
from app.core.config import get_settings
from app.integraciones.jira import sync
from app.integraciones.jira.client import JiraError

STATUS = {
    "pendiente": {"id": "10261", "name": "Pendiente", "statusCategory": {"key": "new"}},
    "en_progreso": {"id": "10005", "name": "En Progreso", "statusCategory": {"key": "indeterminate"}},
    "esperando": {"id": "11802", "name": "Esperando por el Cliente", "statusCategory": {"key": "indeterminate"}},
    "finalizado": {"id": "10094", "name": "Finalizado", "statusCategory": {"key": "done"}},
    "cancelado": {"id": "10190", "name": "Cancelado", "statusCategory": {"key": "done"}},
}
TRANSICIONES = {
    "10261": [("2", "En curso", "en_progreso"), ("4", "Consultar al Cliente", "esperando")],
    "10005": [("3", "Finalizar", "finalizado"), ("4", "Consultar al Cliente", "esperando")],
    "11802": [("5", "Responder", "pendiente")],
}
USUARIOS = {
    "712020:malena": {
        "accountId": "712020:malena",
        "displayName": "Malena Andrea Abugoch Santana",
        "accountType": "atlassian",
        "active": True,
        "avatarUrls": {"48x48": "https://avatar-management--avatars.us-west-2.prod.public.atl-paas.net/malena/48"},
    },
    "712020:tomas": {
        "accountId": "712020:tomas",
        "displayName": "Tomás Carballo",
        "accountType": "atlassian",
        "active": True,
        "avatarUrls": {"48x48": "https://secure.gravatar.com/avatar/tc"},
    },
}
BOARD_CONFIG = {
    "filter": {"id": "42527"},
    "columnConfig": {
        "columns": [
            {"name": "Backlog", "statuses": []},
            {"name": "Por hacer", "statuses": [{"id": "10261"}]},
            {"name": "En curso", "statuses": [{"id": "10005"}]},
            {"name": "ESPERANDO RESPUESTA", "statuses": [{"id": "11802"}]},
            {"name": "Hecho", "statuses": [{"id": "10094"}, {"id": "10190"}]},
        ]
    },
}


_INICIO = dt.datetime.now(dt.UTC)


def _fecha(minutos: int = 0) -> str:
    # Cada operación del Jira falso avanza un minuto desde que arrancan los tests.
    momento = _INICIO + dt.timedelta(minutes=minutos)
    return momento.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _adf(texto: str) -> dict:
    return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": texto}]}]}


class FakeJira:
    """Implementa la misma interfaz que JiraClient sobre diccionarios."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.issues: dict[str, dict] = {}
        self.comments: dict[str, list[dict]] = {}
        self.falla: JiraError | None = None
        self.llamadas: list[str] = []
        self._ids = itertools.count(1000)
        self._reloj = itertools.count(1)

    def __enter__(self) -> "FakeJira":
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def _tick(self) -> str:
        return _fecha(next(self._reloj))

    def _check(self, llamada: str) -> None:
        self.llamadas.append(llamada)
        if self.falla is not None:
            raise self.falla

    # --- helpers para preparar el escenario ---

    def agregar_issue(
        self, key: str, summary: str, status: str = "pendiente", gdld: str | None = None, props: dict | None = None
    ) -> dict:
        issue = {
            "id": str(next(self._ids)),
            "key": key,
            "fields": {
                "summary": summary,
                "status": STATUS[status],
                "updated": self._tick(),
                "customfield_13707": gdld,
                "customfield_10067": {"requestType": {"id": "243"}},
                "assignee": None,
            },
            "properties": props or {},
        }
        self.issues[key] = issue
        self.comments.setdefault(key, [])
        return issue

    def editar(self, key: str, **campos: object) -> None:
        issue = self.issues[key]
        if "status" in campos:
            campos["status"] = STATUS[campos["status"]]
        issue["fields"].update(campos)
        issue["fields"]["updated"] = self._tick()

    def comentar(self, key: str, texto: str, autor: str = "Malena", publico: bool = False) -> None:
        self.comments[key].append(
            {
                "id": str(next(self._ids)),
                "body": _adf(texto),
                "author": {"displayName": autor},
                "jsdPublic": publico,
                "created": self._tick(),
                "properties": [],
            }
        )
        self.issues[key]["fields"]["updated"] = self._tick()

    # --- interfaz de JiraClient ---

    def get_board_configuration(self, board_id: int) -> dict:
        self._check("board")
        return BOARD_CONFIG

    def search_jql(self, jql: str, fields: list[str], properties: list[str] | None = None) -> list[dict]:
        self._check("search")
        issues = list(self.issues.values())
        if m := re.search(r'key = "([^"]+)"', jql):
            issues = [i for i in issues if i["key"] == m.group(1)]
        return [dict(i) for i in issues]

    def get_comments(self, issue_key: str) -> list[dict]:
        self._check("comments")
        return list(self.comments.get(issue_key, []))

    def get_transitions(self, issue_key: str) -> list[dict]:
        self._check("transitions")
        status_id = self.issues[issue_key]["fields"]["status"]["id"]
        return [{"id": t, "name": n, "to": STATUS[d]} for t, n, d in TRANSICIONES.get(status_id, [])]

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        self._check("transition")
        status_id = self.issues[issue_key]["fields"]["status"]["id"]
        destino = next((d for t, _, d in TRANSICIONES.get(status_id, []) if t == transition_id), None)
        if destino is None:
            raise JiraError("Transición inválida", status_code=400)
        self.editar(issue_key, status=destino)

    def create_issue(self, fields: dict, properties: dict | None = None) -> dict:
        self._check("create")
        key = f"MDA-{len(self.issues) + 9000}"
        issue = self.agregar_issue(key, fields["summary"], gdld=fields.get("customfield_13707"), props=properties)
        issue["fields"]["customfield_10067"] = {"requestType": {"id": fields["customfield_10067"]}}
        issue["creado_con"] = fields
        return {"id": issue["id"], "key": key}

    def update_issue(self, issue_key: str, fields: dict) -> None:
        self._check("update")
        self.editar(issue_key, **fields)

    def search_assignable(self, issue_key: str, query: str, limit: int = 20) -> list[dict]:
        self._check("assignable")
        return [u for u in USUARIOS.values() if query.lower() in u["displayName"].lower()][:limit]

    def assign_issue(self, issue_key: str, account_id: str | None) -> None:
        self._check("assign")
        if account_id is not None and account_id not in USUARIOS:
            raise JiraError("400: usuario no asignable", status_code=400)
        self.editar(issue_key, assignee=USUARIOS.get(account_id))

    def add_internal_comment(self, issue_key: str, body_adf: dict, properties: dict | None = None) -> dict:
        self._check("comment")
        comment = {
            "id": str(next(self._ids)),
            "body": body_adf,
            "author": {"displayName": "Ivan"},
            "jsdPublic": False,
            "created": self._tick(),
            "properties": [{"key": k, "value": v} for k, v in (properties or {}).items()],
        }
        self.comments[issue_key].append(comment)
        return comment


@pytest.fixture
def jira(monkeypatch: pytest.MonkeyPatch) -> Generator[FakeJira, None, None]:
    fake = FakeJira()
    sync._tablero_cache.clear()
    monkeypatch.setattr(sync, "crear_cliente", lambda: fake)
    yield fake
    sync._tablero_cache.clear()


def crear_caso(client: TestClient, auth_headers: dict[str, str], **overrides) -> dict:
    payload = {"gdld": "10967", "nombre_proyecto": "MVP Intent Edge", **overrides}
    response = client.post("/casos", json=payload, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


def recargar(db: Session, caso_id: str) -> Caso:
    db.expire_all()
    return db.get(Caso, uuid.UUID(caso_id))


def vincular(db: Session, jira: FakeJira, caso_id: str, status: str = "pendiente") -> str:
    """Deja el caso con su ticket en Jira sin pasar por el worker: el ticket
    "ya existe" (con la propiedad del caso) y el backend lo trae con
    pull_issue, igual que si el worker lo hubiera creado."""
    caso = recargar(db, caso_id)
    key = f"MDA-{8000 + len(jira.issues)}"
    jira.agregar_issue(key, f"[IA-SEC] - {caso.nombre_proyecto}", status=status, props={"aisec.caso_id": {"id": caso_id}})
    sync.pull_issue(db, jira, key)
    return key
