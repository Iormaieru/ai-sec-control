import datetime as dt
import uuid
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.alertas.analisis import analizar
from app.alertas.models import (
    Alerta,
    AlertaEvento,
    EquipoTenable,
    EstadoAlerta,
    FuenteRegla,
    ReglaAlerta,
    SeveridadAlerta,
    TipoReglaTenable,
)
from app.alertas.netskope import NetskopeClient
from app.alertas.schemas import (
    AlertaDetalleOut,
    AlertaOrigenOut,
    AlertaOut,
    EquipoContextoOut,
    EventoOut,
    PruebaReglaOut,
    ReglaCreate,
    ReglaOut,
    ReglaUpdate,
    ResumenAlertasOut,
)
from app.casos import service as casos_service
from app.casos.models import Caso
from app.core.config import get_settings

ABIERTAS = [EstadoAlerta.NUEVA, EstadoAlerta.EN_REVISION]
_ORDEN_SEVERIDAD = {SeveridadAlerta.CRITICA: 0, SeveridadAlerta.ALTA: 1, SeveridadAlerta.MEDIA: 2, SeveridadAlerta.BAJA: 3}
EVENTOS_EN_DETALLE = 50
EVENTOS_PARA_ANALISIS = 1000  # evidencia que se lee para armar el análisis


class CasoInexistente(Exception):
    pass


# --- reglas ---


def listar_reglas(db: Session) -> list[ReglaOut]:
    abiertas = dict(
        db.execute(
            select(Alerta.regla_id, func.count()).where(Alerta.estado.in_(ABIERTAS)).group_by(Alerta.regla_id)
        ).all()
    )
    reglas = db.scalars(select(ReglaAlerta).order_by(ReglaAlerta.nombre)).all()
    return [ReglaOut.model_validate(r).model_copy(update={"alertas_abiertas": abiertas.get(r.id, 0)}) for r in reglas]


def crear_regla(db: Session, datos: ReglaCreate) -> ReglaAlerta:
    regla = ReglaAlerta(**datos.model_dump())
    db.add(regla)
    db.commit()
    return regla


def actualizar_regla(db: Session, regla: ReglaAlerta, datos: ReglaUpdate) -> ReglaAlerta:
    cambios = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    if "consulta" in cambios and cambios["consulta"] != regla.consulta:
        # Consulta distinta: se vuelve a mirar hacia atrás desde la retrospectiva.
        regla.consultada_hasta = None
    for campo, valor in cambios.items():
        setattr(regla, campo, valor)
    db.commit()
    return regla


def eliminar_regla(db: Session, regla: ReglaAlerta) -> None:
    db.delete(regla)  # sus alertas y eventos se borran en cascada
    db.commit()


def probar_regla(client: NetskopeClient, consulta: str) -> PruebaReglaOut:
    """Consulta en vivo las últimas 24 h (sin crear alertas)."""
    settings = get_settings()
    hasta = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=settings.netskope_demora_minutos)
    desde = hasta - dt.timedelta(hours=24)
    eventos = client.eventos(consulta, desde, hasta)
    eventos.sort(key=lambda e: e.fecha, reverse=True)
    return PruebaReglaOut(
        desde=desde,
        hasta=hasta,
        cantidad=len(eventos),
        por_app=dict(Counter(e.app for e in eventos).most_common(10)),
        usuarios=len({e.usuario for e in eventos}),
        muestra=[
            EventoOut(evento_id=e.evento_id, fecha=e.fecha, actividad=e.actividad, sitio=e.sitio, objeto=e.objeto, datos=e.datos)
            for e in eventos[:10]
        ],
    )


# --- alertas ---


def _to_out(alerta: Alerta) -> dict:
    return {
        "id": alerta.id,
        "regla_id": alerta.regla_id,
        "regla_nombre": alerta.regla.nombre,
        "regla_fuente": alerta.regla.fuente,
        "regla_tipo": alerta.regla.consulta if alerta.regla.fuente == FuenteRegla.TENABLE else None,
        "app": alerta.app,
        "usuario": alerta.usuario,
        "estado": alerta.estado,
        "severidad": alerta.severidad,
        "primera_vez": alerta.primera_vez,
        "ultima_vez": alerta.ultima_vez,
        "cantidad_eventos": alerta.cantidad_eventos,
        "actividades": alerta.actividades,
        "caso_id": alerta.caso_id,
        "caso_nombre": alerta.caso.nombre_proyecto if alerta.caso else None,
        "caso_jira_key": alerta.caso.jira_issue_key if alerta.caso else None,
        "nota": alerta.nota,
        "notificada_at": alerta.notificada_at,
        "equipos": alerta.equipos,
        "atendida_at": alerta.atendida_at,
        "cerrada_at": alerta.cerrada_at,
        "updated_at": alerta.updated_at,
    }


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar(
    db: Session,
    *,
    estado: EstadoAlerta | None = None,
    severidad: SeveridadAlerta | None = None,
    regla_id: uuid.UUID | None = None,
    caso_id: uuid.UUID | None = None,
    usuario: str | None = None,
    app: str | None = None,
    desde: dt.date | None = None,
    hasta: dt.date | None = None,
) -> list[AlertaOut]:
    stmt = select(Alerta).options(selectinload(Alerta.regla), selectinload(Alerta.caso))
    if usuario:
        stmt = stmt.where(Alerta.usuario.ilike(f"%{_escapar_like(usuario.strip())}%", escape="\\"))
    if app:
        stmt = stmt.where(Alerta.app.ilike(f"%{_escapar_like(app.strip())}%", escape="\\"))
    # Por fecha: las alertas con actividad dentro del rango (se superponen con él).
    if desde is not None:
        stmt = stmt.where(Alerta.ultima_vez >= dt.datetime.combine(desde, dt.time(), dt.UTC))
    if hasta is not None:
        stmt = stmt.where(Alerta.primera_vez < dt.datetime.combine(hasta + dt.timedelta(days=1), dt.time(), dt.UTC))
    if estado is not None:
        stmt = stmt.where(Alerta.estado == estado)
    if severidad is not None:
        stmt = stmt.where(Alerta.severidad == severidad)
    if regla_id is not None:
        stmt = stmt.where(Alerta.regla_id == regla_id)
    if caso_id is not None:
        stmt = stmt.where(Alerta.caso_id == caso_id)
    alertas = db.scalars(stmt).all()
    # Abiertas primero, después por severidad y por la actividad más reciente.
    alertas = sorted(alertas, key=lambda a: a.ultima_vez, reverse=True)
    alertas.sort(key=lambda a: (a.estado not in ABIERTAS, _ORDEN_SEVERIDAD[a.severidad]))
    return [AlertaOut(**_to_out(a)) for a in alertas]


def obtener(db: Session, alerta_id: uuid.UUID) -> Alerta | None:
    return db.scalar(
        select(Alerta).options(selectinload(Alerta.regla), selectinload(Alerta.caso)).where(Alerta.id == alerta_id)
    )


def detalle(db: Session, alerta: Alerta) -> AlertaDetalleOut:
    eventos = db.scalars(
        select(AlertaEvento)
        .where(AlertaEvento.alerta_id == alerta.id)
        .order_by(AlertaEvento.fecha.desc())
        .limit(EVENTOS_EN_DETALLE)
    ).all()
    contexto = contexto_equipos(db, alerta.equipos)
    analisis_ = []
    if alerta.regla.fuente == FuenteRegla.NETSKOPE:
        evidencia = db.scalars(
            select(AlertaEvento.datos)
            .where(AlertaEvento.alerta_id == alerta.id)
            .order_by(AlertaEvento.fecha.desc())
            .limit(EVENTOS_PARA_ANALISIS)
        ).all()
        analisis_ = analizar(alerta, list(evidencia), {c.equipo for c in contexto if not c.en_tenable})
    return AlertaDetalleOut(
        **_to_out(alerta),
        eventos=[EventoOut.model_validate(e) for e in eventos],
        contexto_equipos=contexto,
        alertas_origen=alertas_origen(db, alerta),
        analisis=analisis_,
    )


def alertas_origen(db: Session, alerta: Alerta) -> list[AlertaOrigenOut]:
    """Para "equipo fuera de Tenable": las alertas de Netskope en las que aparece
    ese equipo (quién lo usaba y qué actividad de IA se vio)."""
    if alerta.regla.consulta != TipoReglaTenable.FUERA_DE_COBERTURA.value or alerta.regla.fuente != FuenteRegla.TENABLE:
        return []
    origen = db.scalars(
        select(Alerta)
        .join(ReglaAlerta, Alerta.regla_id == ReglaAlerta.id)
        .where(ReglaAlerta.fuente == FuenteRegla.NETSKOPE, Alerta.equipos.contains([alerta.usuario]))
        .order_by(Alerta.ultima_vez.desc())
        .limit(EVENTOS_EN_DETALLE)
    ).all()
    return [
        AlertaOrigenOut(
            id=a.id, regla_nombre=a.regla.nombre, app=a.app, usuario=a.usuario, estado=a.estado,
            severidad=a.severidad, ultima_vez=a.ultima_vez,
        )
        for a in origen
    ]


def contexto_equipos(db: Session, nombres: list[str]) -> list[EquipoContextoOut]:
    """Para cada equipo, su ficha en el inventario de Tenable (por hostname o NetBIOS)."""
    if not nombres:
        return []
    encontrados = db.scalars(
        select(EquipoTenable).where((EquipoTenable.hostname.in_(nombres)) | (EquipoTenable.netbios.in_(nombres)))
    ).all()
    por_nombre: dict[str, EquipoTenable] = {}
    for e in encontrados:
        for nombre in (e.hostname, e.netbios):
            # Si un nombre aparece en varios activos, gana el que tiene inventario.
            if nombre and (nombre not in por_nombre or (e.con_inventario and not por_nombre[nombre].con_inventario)):
                por_nombre[nombre] = e
    salida = []
    for nombre in nombres:
        e = por_nombre.get(nombre)
        salida.append(
            EquipoContextoOut(equipo=nombre, en_tenable=False)
            if e is None
            else EquipoContextoOut(
                equipo=nombre, en_tenable=True, con_inventario=e.con_inventario, tiene_agente=e.tiene_agente,
                sistema_operativo=e.sistema_operativo, software_ia=e.software_ia, puertos_ia=e.puertos_ia, visto_at=e.visto_at,
            )
        )
    return salida


def actualizar(db: Session, alerta: Alerta, *, estado: EstadoAlerta | None, nota: str | None) -> Alerta:
    if estado is not None:
        ahora = dt.datetime.now(dt.UTC)
        alerta.estado = estado
        if estado != EstadoAlerta.NUEVA:
            alerta.por_notificar = False  # ya la está viendo alguien
            alerta.atendida_at = alerta.atendida_at or ahora
        alerta.cerrada_at = ahora if estado in (EstadoAlerta.RESUELTA, EstadoAlerta.DESCARTADA) else None
    if nota is not None:
        alerta.nota = nota
    db.commit()
    return obtener(db, alerta.id)


def vincular_caso(db: Session, alerta: Alerta, *, caso_id: uuid.UUID | None, crear: bool) -> Alerta:
    if crear:
        caso = casos_service.create_caso(
            db,
            gdld=None,
            empresa_responsable=None,
            # Las de Tenable son por equipo: el nombre de la "app" solo no dice nada.
            nombre_proyecto=(alerta.app if alerta.regla.fuente == FuenteRegla.NETSKOPE else f"{alerta.app} – {alerta.usuario}")[:200],
            tipo=None,
            tipo_solicitud_id=next(iter(get_settings().jira_request_types)),
        )
    elif caso_id is not None:
        caso = db.get(Caso, caso_id)
        if caso is None:
            raise CasoInexistente("Caso no encontrado")
    else:
        caso = None  # desvincular
    alerta.caso = caso  # la relación (no sólo el id): queda coherente sin recargar
    db.commit()
    return obtener(db, alerta.id)


def resumen(db: Session) -> ResumenAlertasOut:
    conteos = dict(
        db.execute(select(Alerta.estado, func.count()).where(Alerta.estado.in_(ABIERTAS)).group_by(Alerta.estado)).all()
    )
    return ResumenAlertasOut(
        nuevas=conteos.get(EstadoAlerta.NUEVA, 0), en_revision=conteos.get(EstadoAlerta.EN_REVISION, 0)
    )
