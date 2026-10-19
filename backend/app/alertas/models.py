"""Alertas a partir de eventos de Netskope (Skope IT).

Una ReglaAlerta es una consulta de Skope IT (ej. `app like mcp`). El worker
la ejecuta periódicamente contra la API v2 y agrupa los eventos en Alertas
por regla + app + usuario: los eventos siguientes suman a la misma alerta.
"""

import datetime as dt
import enum
import uuid

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.audit.mixin import AuditMixin
from app.casos.models import Caso
from app.db.base import Base
from app.db.mixins import UUIDPKMixin


class SeveridadAlerta(str, enum.Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"


class EstadoAlerta(str, enum.Enum):
    NUEVA = "nueva"
    EN_REVISION = "en_revision"
    RESUELTA = "resuelta"  # si vuelven a llegar eventos, vuelve a "nueva"
    DESCARTADA = "descartada"  # falso positivo: acumula eventos sin volver a avisar


class FuenteRegla(str, enum.Enum):
    NETSKOPE = "netskope"  # consulta de Skope IT
    TENABLE = "tenable"  # tipo predefinido (ver TipoReglaTenable), sobre el inventario de equipos


class TipoReglaTenable(str, enum.Enum):
    SERVICIO_IA_EXPUESTO = "servicio_ia_expuesto"  # puerto de un servicio de IA abierto
    FUERA_DE_COBERTURA = "fuera_de_cobertura"  # equipo con actividad de IA que Tenable no inventaría


class ModoRegla(str, enum.Enum):
    ALERTA = "alerta"  # genera alertas (por app + usuario) y avisa por email
    METRICA = "metrica"  # sólo junta totales para el tablero (reglas muy amplias)


class ReglaAlerta(AuditMixin, Base):
    __tablename__ = "reglas_alerta"

    nombre: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    consulta: Mapped[str] = mapped_column(String(1000), nullable=False)  # sintaxis de Skope IT
    severidad: Mapped[SeveridadAlerta] = mapped_column(Enum(SeveridadAlerta, name="alerta_severidad"), nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notificar_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    modo: Mapped[ModoRegla] = mapped_column(
        Enum(ModoRegla, name="regla_modo"), nullable=False, default=ModoRegla.ALERTA, server_default="ALERTA"
    )
    fuente: Mapped[FuenteRegla] = mapped_column(
        Enum(FuenteRegla, name="regla_fuente"), nullable=False, default=FuenteRegla.NETSKOPE, server_default="NETSKOPE"
    )
    # Para fuente Tenable, `consulta` guarda el tipo (ver TipoReglaTenable).
    # Hasta dónde se consultó Netskope (lo mueve el worker).
    consultada_hasta: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Alerta(AuditMixin, Base):
    __tablename__ = "alertas"
    __table_args__ = (UniqueConstraint("regla_id", "app", "usuario", name="uq_alerta_regla_app_usuario"),)

    regla_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reglas_alerta.id", ondelete="CASCADE"), nullable=False, index=True)
    app: Mapped[str] = mapped_column(String(300), nullable=False)
    usuario: Mapped[str] = mapped_column(String(300), nullable=False)
    estado: Mapped[EstadoAlerta] = mapped_column(
        Enum(EstadoAlerta, name="alerta_estado"), nullable=False, default=EstadoAlerta.NUEVA
    )
    severidad: Mapped[SeveridadAlerta] = mapped_column(Enum(SeveridadAlerta, name="alerta_severidad"), nullable=False)
    primera_vez: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ultima_vez: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cantidad_eventos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actividades: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    # Equipos (hostname, en minúsculas y sin dominio) desde donde se vio la
    # actividad: la clave para cruzar con el inventario de Tenable.
    equipos: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # Primera vez que alguien la tomó (sale de "nueva") y cuándo se cerró
    # (resuelta o descartada): para los tiempos de atención del tablero.
    atendida_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cerrada_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    caso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("casos.id", ondelete="SET NULL"), nullable=True, index=True)
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Pendiente de aviso por email (nueva o reincidente) y cuándo se avisó por última vez.
    por_notificar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notificada_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    regla: Mapped["ReglaAlerta"] = relationship()
    caso: Mapped[Caso | None] = relationship()


class AlertaEvento(UUIDPKMixin, Base):
    """Evento de Netskope que alimentó una alerta (evidencia). Un evento que
    vuelve a aparecer en otra consulta no cuenta dos veces."""

    __tablename__ = "alerta_eventos"
    # Un mismo evento puede cumplir dos reglas: es único por alerta, no global.
    __table_args__ = (UniqueConstraint("alerta_id", "evento_id", name="uq_alerta_evento"),)

    alerta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alertas.id", ondelete="CASCADE"), nullable=False, index=True)
    evento_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    fecha: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    actividad: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sitio: Mapped[str | None] = mapped_column(String(300), nullable=True)
    objeto: Mapped[str | None] = mapped_column(String(500), nullable=True)
    datos: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class MetricaIA(UUIDPKMixin, Base):
    """Totales diarios de una regla en modo métrica (para el tablero): cuántos
    eventos hubo por día, app, usuario y actividad, sin guardar cada evento."""

    __tablename__ = "metricas_ia"
    __table_args__ = (
        UniqueConstraint("regla_id", "dia", "app", "usuario", "actividad", name="uq_metrica_ia"),
    )

    regla_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reglas_alerta.id", ondelete="CASCADE"), nullable=False, index=True)
    dia: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    app: Mapped[str] = mapped_column(String(300), nullable=False)
    usuario: Mapped[str] = mapped_column(String(300), nullable=False)
    actividad: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    eventos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class EquipoTenable(UUIDPKMixin, Base):
    """Un equipo del inventario de Tenable, con lo relevante para seguridad
    de IA. Lo reemplaza el worker en cada actualización (una vez por día)."""

    __tablename__ = "equipos_tenable"

    asset_uuid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)  # minúsculas, sin dominio
    netbios: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # minúsculas
    sistema_operativo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    tiene_agente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    con_inventario: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # escaneo con credenciales o agente
    software_ia: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # [{"puerto": 8888, "servicio": "Jupyter"}]
    puertos_ia: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    visto_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actualizado_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SincronizacionTenable(UUIDPKMixin, Base):
    """Registro de cada actualización del inventario (para saber cuándo toca la próxima)."""

    __tablename__ = "sincronizaciones_tenable"

    iniciada_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalizada_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    equipos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DestinatarioAlerta(AuditMixin, Base):
    """Casilla que recibe el email resumen de alertas. Se gestiona desde la
    plataforma; en el futuro saldrá de un grupo de Entra ID (ver
    app.alertas.destinatarios)."""

    __tablename__ = "destinatarios_alerta"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)  # en minúsculas
    nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
