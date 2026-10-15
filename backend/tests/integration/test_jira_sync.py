"""Sincronización con Jira contra un Jira falso en memoria (FakeJira): nada
sale a la red."""

import datetime as dt
import itertools
import re
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casos.models import Caso, CasoComentario, CasoEstado, JiraSyncEstado, Origen
from app.core.config import get_settings
from app.integraciones.jira import sync
from app.integraciones.jira.client import JiraError
from app.integraciones.jira.models import JiraOutbox

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


def _crear_caso(client: TestClient, auth_headers: dict[str, str], **overrides) -> dict:
    payload = {"gdld": "10967", "nombre_proyecto": "MVP Intent Edge", **overrides}
    response = client.post("/casos", json=payload, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


def _caso(db: Session, caso_id: str) -> Caso:
    db.expire_all()
    return db.get(Caso, uuid.UUID(caso_id))


# --- plataforma -> Jira ---


def test_caso_nuevo_se_crea_en_jira(client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira) -> None:
    caso = _crear_caso(client, auth_headers, tipo_solicitud_id="544")
    assert caso["jira_sync_estado"] == "pendiente"
    assert caso["tipo"] is None and caso["empresa_responsable"] is None

    resultado = sync.push(db, jira)

    assert resultado.enviados == 1
    issue = next(iter(jira.issues.values()))
    assert issue["creado_con"]["summary"] == "[IA-SEC] - GDLD-10967 - MVP Intent Edge"
    assert issue["creado_con"]["customfield_13707"] == "GDLD-10967"
    assert issue["creado_con"]["customfield_10067"] == "544"
    assert issue["properties"] == {"aisec.caso_id": {"id": caso["id"]}}
    actualizado = client.get(f"/casos/{caso['id']}", headers=auth_headers).json()
    assert actualizado["jira_issue_key"] == issue["key"]
    assert actualizado["jira_url"].endswith(f"/browse/{issue['key']}")
    assert actualizado["jira_sync_estado"] == "ok"


def test_tipo_solicitud_desconocido_devuelve_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/casos", json={"nombre_proyecto": "X", "tipo_solicitud_id": "1"}, headers=auth_headers)

    assert response.status_code == 422


def test_edicion_del_caso_actualiza_el_ticket(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = _crear_caso(client, auth_headers)
    sync.push(db, jira)

    client.patch(f"/casos/{caso['id']}", json={"nombre_proyecto": "Intent Edge v2"}, headers=auth_headers)
    client.patch(f"/casos/{caso['id']}", json={"gdld": "11000"}, headers=auth_headers)
    # Dos ediciones seguidas: una sola actualización en cola.
    assert db.scalar(select(JiraOutbox).where(JiraOutbox.procesado_at.is_(None))) is not None
    sync.push(db, jira)

    assert jira.llamadas.count("update") == 1
    issue = next(iter(jira.issues.values()))
    assert issue["fields"]["summary"] == "[IA-SEC] - GDLD-11000 - Intent Edge v2"
    assert issue["fields"]["customfield_13707"] == "GDLD-11000"


def test_editar_empresa_o_tipo_no_toca_jira(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = _crear_caso(client, auth_headers)
    sync.push(db, jira)

    client.patch(f"/casos/{caso['id']}", json={"empresa_responsable": "ACME", "tipo": "candidato"}, headers=auth_headers)

    assert _caso(db, caso["id"]).jira_sync_estado == JiraSyncEstado.OK
    assert sync.push(db, jira).enviados == 0


def test_jira_caido_se_reintenta_con_backoff(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = _crear_caso(client, auth_headers)
    jira.falla = JiraError("ConnectError")

    sync.push(db, jira)

    c = _caso(db, caso["id"])
    assert c.jira_sync_estado == JiraSyncEstado.ERROR
    assert "se reintenta" in c.jira_sync_error
    op = db.scalar(select(JiraOutbox).where(JiraOutbox.caso_id == c.id))
    assert op.intentos == 1 and op.proximo_intento_at > dt.datetime.now(dt.UTC)

    # Antes del backoff no se vuelve a intentar.
    jira.falla = None
    assert sync.push(db, jira).enviados == 0

    op.proximo_intento_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    db.commit()
    assert sync.push(db, jira).enviados == 1
    c = _caso(db, caso["id"])
    assert c.jira_sync_estado == JiraSyncEstado.OK and c.jira_sync_error is None


def test_rechazo_de_jira_queda_en_error_hasta_reintentar(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = _crear_caso(client, auth_headers)
    client.post(f"/casos/{caso['id']}/comentarios", json={"cuerpo": "hola"}, headers=auth_headers)
    jira.falla = JiraError("400: campo inválido", status_code=400)

    sync.push(db, jira)
    jira.falla = None
    sync.push(db, jira)

    # Descartada: no se reintenta sola, y el comentario espera detrás de la creación.
    assert jira.llamadas.count("create") == 1
    assert "comment" not in jira.llamadas
    assert _caso(db, caso["id"]).jira_sync_estado == JiraSyncEstado.ERROR

    response = client.post(f"/casos/{caso['id']}/jira/reintentar", headers=auth_headers)
    assert response.status_code == 200
    sync.push(db, jira)

    assert jira.llamadas.count("create") == 2 and "comment" in jira.llamadas
    assert _caso(db, caso["id"]).jira_sync_estado == JiraSyncEstado.OK


# --- Jira -> plataforma ---


def test_pull_importa_los_tickets_existentes(db: Session, jira: FakeJira) -> None:
    jira.agregar_issue("MDA-6215", "[IA-SEC] - GDLD-10967 - MVP Intent Edge", status="esperando", gdld="GDLD-10967")
    jira.agregar_issue("MDA-6220", "Generar informe de seguridad de Rovo - Jira", status="cancelado")
    jira.comentar("MDA-6215", "Esperamos la respuesta del proveedor")

    resultado = sync.pull(db, jira)

    assert (resultado.nuevos, resultado.actualizados) == (2, 0)
    casos = {c.jira_issue_key: c for c in db.scalars(select(Caso))}
    intent = casos["MDA-6215"]
    assert intent.origen == Origen.JIRA
    assert intent.nombre_proyecto == "MVP Intent Edge"
    assert intent.gdld == "10967"
    assert intent.estado == CasoEstado.ESPERANDO_RESPUESTA
    assert intent.jira_status_nombre == "Esperando por el Cliente"
    assert intent.jira_tipo_solicitud_id == "243"
    assert intent.tipo is None and intent.empresa_responsable is None
    assert intent.jira_asignado_nombre is None
    assert casos["MDA-6220"].estado == CasoEstado.HECHO
    assert casos["MDA-6220"].jira_status_nombre == "Cancelado"
    [comentario] = intent.comentarios
    assert comentario.cuerpo == "Esperamos la respuesta del proveedor"
    assert comentario.origen == Origen.JIRA and comentario.publico is False

    # Una segunda corrida no duplica nada.
    assert sync.pull(db, jira).nuevos == 0
    assert db.query(Caso).count() == 2
    assert db.query(CasoComentario).count() == 1


def test_pull_aplica_cambios_de_estado_y_resumen(db: Session, jira: FakeJira) -> None:
    jira.agregar_issue("MDA-1", "[IA-SEC] - POC RAN")
    sync.pull(db, jira)

    jira.editar("MDA-1", status="en_progreso", summary="[IA-SEC] - GDLD-555 - POC RAN Fase 2")
    resultado = sync.pull(db, jira)

    assert resultado.actualizados == 1
    caso = db.scalar(select(Caso).where(Caso.jira_issue_key == "MDA-1"))
    assert caso.estado == CasoEstado.EN_CURSO
    assert caso.nombre_proyecto == "POC RAN Fase 2"
    assert caso.gdld == "555"  # sin el campo GDLD, se toma del resumen


def test_edicion_local_sin_empujar_gana_sobre_jira(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    jira.agregar_issue("MDA-1", "[IA-SEC] - POC RAN")
    sync.pull(db, jira)
    caso = db.scalar(select(Caso).where(Caso.jira_issue_key == "MDA-1"))

    client.patch(f"/casos/{caso.id}", json={"nombre_proyecto": "Nombre local"}, headers=auth_headers)
    jira.editar("MDA-1", summary="[IA-SEC] - Nombre en Jira", status="en_progreso")
    sync.pull(db, jira)

    caso = _caso(db, str(caso.id))
    assert caso.nombre_proyecto == "Nombre local"
    assert caso.estado == CasoEstado.EN_CURSO  # el estado siempre lo manda Jira
    sync.push(db, jira)
    assert jira.issues["MDA-1"]["fields"]["summary"] == "[IA-SEC] - Nombre local"


def test_ticket_creado_desde_la_plataforma_no_se_duplica(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    """El pull encuentra el ticket antes de que el push guarde su key (por
    ejemplo, se perdió la respuesta de Jira): lo vincula por la propiedad."""
    caso = _crear_caso(client, auth_headers)
    jira.agregar_issue("MDA-7000", "[IA-SEC] - GDLD-10967 - MVP Intent Edge", props={"aisec.caso_id": caso["id"]})

    resultado = sync.pull(db, jira)
    sync.push(db, jira)

    assert resultado.nuevos == 0
    assert db.query(Caso).count() == 1
    c = _caso(db, caso["id"])
    assert c.jira_issue_key == "MDA-7000" and c.jira_sync_estado == JiraSyncEstado.OK
    assert "create" not in jira.llamadas


def test_comentarios_en_los_dos_sentidos_sin_eco(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = _crear_caso(client, auth_headers)
    sync.push(db, jira)
    key = _caso(db, caso["id"]).jira_issue_key

    response = client.post(f"/casos/{caso['id']}/comentarios", json={"cuerpo": "Pedimos el SOC2"}, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["publico"] is False
    sync.push(db, jira)
    jira.comentar(key, "Lo envío mañana", autor="Proveedor", publico=True)
    sync.pull(db, jira)

    [enviado] = jira.comments[key][:1]
    assert enviado["properties"] == [{"key": "aisec.comentario_id", "value": {"id": response.json()["id"]}}]
    assert "Pedimos el SOC2" in str(enviado["body"])
    comentarios = client.get(f"/casos/{caso['id']}/comentarios", headers=auth_headers).json()
    assert [(c["cuerpo"], c["origen"], c["publico"]) for c in comentarios] == [
        ("Pedimos el SOC2", "plataforma", False),
        ("Lo envío mañana", "jira", True),
    ]


def test_caso_anterior_a_la_integracion_no_va_a_jira(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = _crear_caso(client, auth_headers)
    c = _caso(db, caso["id"])
    db.query(JiraOutbox).delete()
    c.jira_sync_estado = None  # como los casos que ya existían
    db.commit()

    client.post(f"/casos/{caso['id']}/comentarios", json={"cuerpo": "nota"}, headers=auth_headers)
    response = client.patch(f"/casos/{caso['id']}", json={"estado": "hecho"}, headers=auth_headers)

    assert response.status_code == 200 and response.json()["estado"] == "hecho"
    assert db.query(JiraOutbox).count() == 0


# --- transiciones ---


def test_transiciones_del_workflow_de_jira(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = _crear_caso(client, auth_headers)
    sync.push(db, jira)

    response = client.get(f"/casos/{caso['id']}/transiciones", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == [
        {"id": "2", "nombre": "En curso", "destino": "En Progreso", "estado": "en_curso"},
        {"id": "4", "nombre": "Consultar al Cliente", "destino": "Esperando por el Cliente", "estado": "esperando_respuesta"},
    ]

    response = client.post(f"/casos/{caso['id']}/transiciones", json={"transition_id": "4"}, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["estado"] == "esperando_respuesta"
    assert response.json()["jira_status_nombre"] == "Esperando por el Cliente"

    response = client.post(f"/casos/{caso['id']}/transiciones", json={"transition_id": "3"}, headers=auth_headers)
    assert response.status_code == 400
    assert _caso(db, caso["id"]).estado == CasoEstado.ESPERANDO_RESPUESTA


def test_estado_de_caso_vinculado_no_se_cambia_por_patch(
    client: TestClient, auth_headers: dict[str, str], jira: FakeJira
) -> None:
    caso = _crear_caso(client, auth_headers)

    response = client.patch(f"/casos/{caso['id']}", json={"estado": "hecho"}, headers=auth_headers)

    assert response.status_code == 409


def test_transiciones_sin_ticket_todavia(client: TestClient, auth_headers: dict[str, str], jira: FakeJira) -> None:
    caso = _crear_caso(client, auth_headers)

    response = client.get(f"/casos/{caso['id']}/transiciones", headers=auth_headers)

    assert response.status_code == 409


# --- endpoints de sincronización ---


def test_sync_y_webhook_exigen_secreto(client: TestClient, monkeypatch: pytest.MonkeyPatch, jira: FakeJira) -> None:
    assert client.post("/integraciones/jira/sync").status_code == 404  # sin secreto configurado

    settings = get_settings()
    monkeypatch.setattr(settings, "jira_sync_secret", "s3cret-sync")
    monkeypatch.setattr(settings, "jira_webhook_secret", "s3cret-hook")

    assert client.post("/integraciones/jira/sync", headers={"X-Aisec-Secret": "otro"}).status_code == 401
    assert client.post("/integraciones/jira/webhook", json={"issueKey": "MDA-1"}).status_code == 401
    assert (
        client.post("/integraciones/jira/webhook", json={"issueKey": "MDA-1"}, headers={"X-Aisec-Secret": "s3cret-sync"})
        .status_code
        == 401
    )


def test_sync_endpoint_empuja_y_trae(client: TestClient, monkeypatch: pytest.MonkeyPatch, db: Session, jira: FakeJira) -> None:
    monkeypatch.setattr(get_settings(), "jira_sync_secret", "s3cret-sync")
    jira.agregar_issue("MDA-1", "[IA-SEC] - POC RAN")

    response = client.post("/integraciones/jira/sync", headers={"X-Aisec-Secret": "s3cret-sync"})

    assert response.status_code == 200
    assert response.json()["pull"]["nuevos"] == 1


def test_webhook_trae_el_ticket(client: TestClient, monkeypatch: pytest.MonkeyPatch, db: Session, jira: FakeJira) -> None:
    monkeypatch.setattr(get_settings(), "jira_webhook_secret", "s3cret-hook")
    jira.agregar_issue("MDA-5", "[IA-SEC] - POC Netskope AI", status="esperando")
    headers = {"X-Aisec-Secret": "s3cret-hook"}

    response = client.post("/integraciones/jira/webhook", json={"issue": {"key": "MDA-5"}}, headers=headers)

    assert response.status_code == 204
    caso = db.scalar(select(Caso).where(Caso.jira_issue_key == "MDA-5"))
    assert caso.estado == CasoEstado.ESPERANDO_RESPUESTA
    bad = client.post("/integraciones/jira/webhook", json={"issueKey": "MDA-5 OR 1=1"}, headers=headers)
    assert bad.status_code == 422


def test_pull_trae_la_persona_asignada(db: Session, jira: FakeJira) -> None:
    jira.agregar_issue("MDA-1", "[IA-SEC] - POC RAN")
    avatar = "https://avatar-management--avatars.us-west-2.prod.public.atl-paas.net/712020:abc/48"
    jira.editar(
        "MDA-1",
        assignee={"accountId": "712020:abc", "displayName": "Malena Abugoch", "avatarUrls": {"48x48": avatar}},
    )
    sync.pull(db, jira)
    caso = db.scalar(select(Caso).where(Caso.jira_issue_key == "MDA-1"))
    assert (caso.jira_asignado_id, caso.jira_asignado_nombre) == ("712020:abc", "Malena Abugoch")
    assert caso.jira_asignado_avatar_url == avatar

    jira.editar("MDA-1", assignee=None)  # lo desasignan en Jira
    sync.pull(db, jira)

    caso = _caso(db, str(caso.id))
    assert caso.jira_asignado_nombre is None and caso.jira_asignado_avatar_url is None


# --- asignación ---


def test_asignar_y_desasignar_desde_la_plataforma(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = _crear_caso(client, auth_headers)
    sync.push(db, jira)

    response = client.get(f"/casos/{caso['id']}/asignables", params={"query": "male"}, headers=auth_headers)
    assert response.status_code == 200
    assert [p["nombre"] for p in response.json()] == ["Malena Andrea Abugoch Santana"]

    response = client.put(f"/casos/{caso['id']}/asignado", json={"account_id": "712020:malena"}, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["jira_asignado_nombre"] == "Malena Andrea Abugoch Santana"
    assert response.json()["jira_asignado_avatar_url"].startswith("https://")
    key = _caso(db, caso["id"]).jira_issue_key
    assert jira.issues[key]["fields"]["assignee"]["accountId"] == "712020:malena"

    equipo = client.get("/casos/equipo-jira", headers=auth_headers).json()
    assert [p["account_id"] for p in equipo] == ["712020:malena"]

    response = client.put(f"/casos/{caso['id']}/asignado", json={"account_id": None}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["jira_asignado_nombre"] is None
    assert jira.issues[key]["fields"]["assignee"] is None


def test_asignacion_rechazada_por_jira(client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira) -> None:
    caso = _crear_caso(client, auth_headers)
    sync.push(db, jira)

    response = client.put(f"/casos/{caso['id']}/asignado", json={"account_id": "712020:otro"}, headers=auth_headers)
    assert response.status_code == 400

    response = client.put(f"/casos/{caso['id']}/asignado", json={"account_id": "x OR 1=1"}, headers=auth_headers)
    assert response.status_code == 422


def test_no_se_asigna_un_caso_sin_ticket(client: TestClient, auth_headers: dict[str, str], jira: FakeJira) -> None:
    caso = _crear_caso(client, auth_headers)

    response = client.put(f"/casos/{caso['id']}/asignado", json={"account_id": "712020:malena"}, headers=auth_headers)

    assert response.status_code == 409
