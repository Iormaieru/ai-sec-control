"""Worker: envío de eventos a Jira (push), pull periódico y el loop con
LISTEN/NOTIFY, contra el Jira falso en memoria."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from aisec_worker import __main__ as worker
from aisec_worker.pull import pull
from aisec_worker.push import push
from app.casos.models import Caso, CasoComentario, CasoEstado, JiraSyncEstado, Origen
from app.core.config import get_settings
from app.db.session import engine
from app.integraciones.jira.client import JiraError
from app.integraciones.jira.models import JiraOutbox
from tests.integration.fake_jira import FakeJira, crear_caso, recargar


# --- plataforma -> Jira (push) ---


def test_caso_nuevo_se_crea_en_jira(client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira) -> None:
    caso = crear_caso(client, auth_headers, tipo_solicitud_id="544")
    assert caso["jira_sync_estado"] == "pendiente"
    assert caso["tipo"] is None and caso["empresa_responsable"] is None

    resultado = push(db, jira)

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


def test_edicion_del_caso_actualiza_el_ticket(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = crear_caso(client, auth_headers)
    push(db, jira)

    client.patch(f"/casos/{caso['id']}", json={"nombre_proyecto": "Intent Edge v2"}, headers=auth_headers)
    client.patch(f"/casos/{caso['id']}", json={"gdld": "11000"}, headers=auth_headers)
    # Dos ediciones seguidas: una sola actualización en cola.
    assert db.scalar(select(JiraOutbox).where(JiraOutbox.procesado_at.is_(None))) is not None
    push(db, jira)

    assert jira.llamadas.count("update") == 1
    issue = next(iter(jira.issues.values()))
    assert issue["fields"]["summary"] == "[IA-SEC] - GDLD-11000 - Intent Edge v2"
    assert issue["fields"]["customfield_13707"] == "GDLD-11000"


def test_jira_caido_se_reintenta_con_backoff(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = crear_caso(client, auth_headers)
    jira.falla = JiraError("ConnectError")

    push(db, jira)

    c = recargar(db, caso["id"])
    assert c.jira_sync_estado == JiraSyncEstado.ERROR
    assert "se reintenta" in c.jira_sync_error
    op = db.scalar(select(JiraOutbox).where(JiraOutbox.caso_id == c.id))
    assert op.intentos == 1 and op.proximo_intento_at > dt.datetime.now(dt.UTC)

    # Antes del backoff no se vuelve a intentar.
    jira.falla = None
    assert push(db, jira).enviados == 0

    op.proximo_intento_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    db.commit()
    assert push(db, jira).enviados == 1
    c = recargar(db, caso["id"])
    assert c.jira_sync_estado == JiraSyncEstado.OK and c.jira_sync_error is None


def test_rechazo_de_jira_queda_en_error_hasta_reintentar(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = crear_caso(client, auth_headers)
    client.post(f"/casos/{caso['id']}/comentarios", json={"cuerpo": "hola"}, headers=auth_headers)
    jira.falla = JiraError("400: campo inválido", status_code=400)

    push(db, jira)
    jira.falla = None
    push(db, jira)

    # Descartada: no se reintenta sola, y el comentario espera detrás de la creación.
    assert jira.llamadas.count("create") == 1
    assert "comment" not in jira.llamadas
    assert recargar(db, caso["id"]).jira_sync_estado == JiraSyncEstado.ERROR

    response = client.post(f"/casos/{caso['id']}/jira/reintentar", headers=auth_headers)
    assert response.status_code == 200
    push(db, jira)

    assert jira.llamadas.count("create") == 2 and "comment" in jira.llamadas
    assert recargar(db, caso["id"]).jira_sync_estado == JiraSyncEstado.OK


def test_pull_importa_los_tickets_existentes(db: Session, jira: FakeJira) -> None:
    jira.agregar_issue("MDA-6215", "[IA-SEC] - GDLD-10967 - MVP Intent Edge", status="esperando", gdld="GDLD-10967")
    jira.agregar_issue("MDA-6220", "Generar informe de seguridad de Rovo - Jira", status="cancelado")
    jira.comentar("MDA-6215", "Esperamos la respuesta del proveedor")

    resultado = pull(db, jira)

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
    assert pull(db, jira).nuevos == 0
    assert db.query(Caso).count() == 2
    assert db.query(CasoComentario).count() == 1


def test_pull_aplica_cambios_de_estado_y_resumen(db: Session, jira: FakeJira) -> None:
    jira.agregar_issue("MDA-1", "[IA-SEC] - POC RAN")
    pull(db, jira)

    jira.editar("MDA-1", status="en_progreso", summary="[IA-SEC] - GDLD-555 - POC RAN Fase 2")
    resultado = pull(db, jira)

    assert resultado.actualizados == 1
    caso = db.scalar(select(Caso).where(Caso.jira_issue_key == "MDA-1"))
    assert caso.estado == CasoEstado.EN_CURSO
    assert caso.nombre_proyecto == "POC RAN Fase 2"
    assert caso.gdld == "555"  # sin el campo GDLD, se toma del resumen


def test_edicion_local_sin_empujar_gana_sobre_jira(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    jira.agregar_issue("MDA-1", "[IA-SEC] - POC RAN")
    pull(db, jira)
    caso = db.scalar(select(Caso).where(Caso.jira_issue_key == "MDA-1"))

    client.patch(f"/casos/{caso.id}", json={"nombre_proyecto": "Nombre local"}, headers=auth_headers)
    jira.editar("MDA-1", summary="[IA-SEC] - Nombre en Jira", status="en_progreso")
    pull(db, jira)

    caso = recargar(db, str(caso.id))
    assert caso.nombre_proyecto == "Nombre local"
    assert caso.estado == CasoEstado.EN_CURSO  # el estado siempre lo manda Jira
    push(db, jira)
    assert jira.issues["MDA-1"]["fields"]["summary"] == "[IA-SEC] - Nombre local"


def test_ticket_creado_desde_la_plataforma_no_se_duplica(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    """El pull encuentra el ticket antes de que el push guarde su key (por
    ejemplo, se perdió la respuesta de Jira): lo vincula por la propiedad."""
    caso = crear_caso(client, auth_headers)
    jira.agregar_issue("MDA-7000", "[IA-SEC] - GDLD-10967 - MVP Intent Edge", props={"aisec.caso_id": caso["id"]})

    resultado = pull(db, jira)
    push(db, jira)

    assert resultado.nuevos == 0
    assert db.query(Caso).count() == 1
    c = recargar(db, caso["id"])
    assert c.jira_issue_key == "MDA-7000" and c.jira_sync_estado == JiraSyncEstado.OK
    assert "create" not in jira.llamadas


def test_comentarios_en_los_dos_sentidos_sin_eco(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    caso = crear_caso(client, auth_headers)
    push(db, jira)
    key = recargar(db, caso["id"]).jira_issue_key

    response = client.post(f"/casos/{caso['id']}/comentarios", json={"cuerpo": "Pedimos el SOC2"}, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["publico"] is False
    push(db, jira)
    jira.comentar(key, "Lo envío mañana", autor="Proveedor", publico=True)
    pull(db, jira)

    [enviado] = jira.comments[key][:1]
    assert enviado["properties"] == [{"key": "aisec.comentario_id", "value": {"id": response.json()["id"]}}]
    assert "Pedimos el SOC2" in str(enviado["body"])
    comentarios = client.get(f"/casos/{caso['id']}/comentarios", headers=auth_headers).json()
    assert [(c["cuerpo"], c["origen"], c["publico"]) for c in comentarios] == [
        ("Pedimos el SOC2", "plataforma", False),
        ("Lo envío mañana", "jira", True),
    ]


def test_pull_trae_la_persona_asignada(db: Session, jira: FakeJira) -> None:
    jira.agregar_issue("MDA-1", "[IA-SEC] - POC RAN")
    avatar = "https://avatar-management--avatars.us-west-2.prod.public.atl-paas.net/712020:abc/48"
    jira.editar(
        "MDA-1",
        assignee={"accountId": "712020:abc", "displayName": "Malena Abugoch", "avatarUrls": {"48x48": avatar}},
    )
    pull(db, jira)
    caso = db.scalar(select(Caso).where(Caso.jira_issue_key == "MDA-1"))
    assert (caso.jira_asignado_id, caso.jira_asignado_nombre) == ("712020:abc", "Malena Abugoch")
    assert caso.jira_asignado_avatar_url == avatar

    jira.editar("MDA-1", assignee=None)  # lo desasignan en Jira
    pull(db, jira)

    caso = recargar(db, str(caso.id))
    assert caso.jira_asignado_nombre is None and caso.jira_asignado_avatar_url is None


# --- loop del worker ---


def test_el_worker_se_despierta_con_el_aviso_de_la_plataforma(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    escucha = worker.Escucha(get_settings().database_url)
    try:
        assert escucha.esperar(0.2) is False  # nada pendiente: espera hasta el timeout

        crear_caso(client, auth_headers)

        assert escucha.esperar(2) is True
    finally:
        escucha.cerrar()


def test_vuelta_completa_envia_y_trae(client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira) -> None:
    caso = crear_caso(client, auth_headers)
    jira.agregar_issue("MDA-1", "[IA-SEC] - POC RAN")

    worker.vuelta(con_pull=True)

    assert recargar(db, caso["id"]).jira_issue_key is not None
    assert db.scalar(select(Caso).where(Caso.jira_issue_key == "MDA-1")) is not None


def test_vuelta_sin_pull_solo_envia_eventos(
    client: TestClient, auth_headers: dict[str, str], db: Session, jira: FakeJira
) -> None:
    crear_caso(client, auth_headers)
    jira.agregar_issue("MDA-1", "[IA-SEC] - POC RAN")

    worker.vuelta(con_pull=False)

    assert "create" in jira.llamadas and "search" not in jira.llamadas


def test_vuelta_se_omite_si_otra_instancia_esta_sincronizando(
    client: TestClient, auth_headers: dict[str, str], jira: FakeJira
) -> None:
    crear_caso(client, auth_headers)
    with engine.connect() as otra:
        otra.execute(text("SELECT pg_advisory_lock(:k)"), {"k": worker._LOCK})
        try:
            worker.vuelta(con_pull=True)
        finally:
            otra.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": worker._LOCK})

    assert jira.llamadas == []
