import datetime as dt
import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.audit.mixin import AuditMixin
from app.db.base import Base


class CasoTipo(str, enum.Enum):
    CANDIDATO = "candidato"
    INGRESADO = "ingresado"
    HERRAMIENTA_TERCERO = "herramienta_tercero"


class CasoEstado(str, enum.Enum):
    """Las columnas del tablero IA-SEC de Jira. El status exacto del ticket
    (ej. "Cancelado" dentro de Hecho) se guarda aparte en jira_status_nombre."""

    POR_HACER = "por_hacer"
    EN_CURSO = "en_curso"
    ESPERANDO_RESPUESTA = "esperando_respuesta"
    HECHO = "hecho"


class Origen(str, enum.Enum):
    PLATAFORMA = "plataforma"
    JIRA = "jira"


class JiraSyncEstado(str, enum.Enum):
    OK = "ok"
    PENDIENTE = "pendiente"
    ERROR = "error"


class Caso(AuditMixin, Base):
    __tablename__ = "casos"

    gdld: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Opcionales: los casos importados de Jira llegan sin estos datos y se
    # completan en la plataforma (no se sincronizan).
    empresa_responsable: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nombre_proyecto: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[CasoTipo | None] = mapped_column(Enum(CasoTipo, name="caso_tipo"), nullable=True)
    estado: Mapped[CasoEstado] = mapped_column(
        Enum(CasoEstado, name="caso_estado"), nullable=False, default=CasoEstado.POR_HACER
    )
    origen: Mapped[Origen] = mapped_column(
        Enum(Origen, name="origen"), nullable=False, default=Origen.PLATAFORMA, server_default="PLATAFORMA"
    )

    # Vínculo con el ticket de Jira. Un caso sin jira_sync_estado es anterior
    # a la integración y no se sube a Jira.
    jira_issue_id: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    jira_issue_key: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    jira_status_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    jira_status_nombre: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_tipo_solicitud_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Persona asignada en Jira (la asignación se gestiona allá; acá sólo se muestra).
    jira_asignado_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    jira_asignado_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Foto de perfil (CDN público de Atlassian o Gravatar; no requiere credenciales).
    jira_asignado_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    jira_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    jira_sync_estado: Mapped[JiraSyncEstado | None] = mapped_column(
        Enum(JiraSyncEstado, name="jira_sync_estado"), nullable=True
    )
    jira_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    contactos: Mapped[list["Contacto"]] = relationship(
        back_populates="caso", cascade="all, delete-orphan", order_by="Contacto.created_at"
    )
    comentarios: Mapped[list["CasoComentario"]] = relationship(
        back_populates="caso", cascade="all, delete-orphan", order_by="CasoComentario.fecha"
    )


class Contacto(AuditMixin, Base):
    __tablename__ = "contactos"

    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rol: Mapped[str | None] = mapped_column(String(100), nullable=True)

    caso: Mapped["Caso"] = relationship(back_populates="contactos")


class CasoComentario(AuditMixin, Base):
    __tablename__ = "caso_comentarios"

    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), nullable=False, index=True)
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    autor_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    origen: Mapped[Origen] = mapped_column(Enum(Origen, name="origen"), nullable=False)
    # Visible para el solicitante en el portal de Jira. Los que se escriben en
    # la plataforma siempre son internos.
    publico: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    jira_comment_id: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    # Cuándo se escribió (en Jira, para los importados): ordena la conversación.
    fecha: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    caso: Mapped["Caso"] = relationship(back_populates="comentarios")
