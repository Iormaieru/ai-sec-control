import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.audit.mixin import AuditMixin
from app.db.base import Base


class PreguntaTipo(str, enum.Enum):
    CONTROL = "control"
    RIESGO = "riesgo"


class Polaridad(str, enum.Enum):
    POSITIVA = "positiva"  # +1 (SI=bien)
    NEGATIVA = "negativa"  # -1 (NO=bien)


class Tier(str, enum.Enum):
    CRITICO = "critico"
    ALTO = "alto"
    ESTANDAR = "estandar"


TIER_MULTIPLICADOR = {Tier.CRITICO: 3, Tier.ALTO: 2, Tier.ESTANDAR: 1}


class Dominio(AuditMixin, Base):
    """Uno de los 8 dominios PLOT4AI. Datos fijos, cargados una sola vez por
    el seed (ver app/catalog/seed.py) desde el Catálogo Maestro del Excel."""

    __tablename__ = "dominios"

    codigo: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    peso: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    total_preguntas: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    preguntas: Mapped[list["Pregunta"]] = relationship(back_populates="dominio", order_by="Pregunta.numero")


class Pregunta(AuditMixin, Base):
    """Una fila del Catálogo Maestro (una pregunta dentro de un dominio)."""

    __tablename__ = "preguntas"
    __table_args__ = (UniqueConstraint("dominio_id", "numero", name="uq_pregunta_dominio_numero"),)

    dominio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dominios.id"), nullable=False)
    numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    texto_es: Mapped[str] = mapped_column(Text, nullable=False)
    texto_en: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[PreguntaTipo] = mapped_column(Enum(PreguntaTipo, name="pregunta_tipo"), nullable=False)
    polaridad: Mapped[Polaridad] = mapped_column(Enum(Polaridad, name="polaridad"), nullable=False)
    tier: Mapped[Tier] = mapped_column(Enum(Tier, name="tier"), nullable=False)
    multiplicador: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    impacto_primario: Mapped[str | None] = mapped_column(String(200), nullable=True)
    referencias_regulatorias: Mapped[str | None] = mapped_column(Text, nullable=True)
    justificacion_tier: Mapped[str | None] = mapped_column(Text, nullable=True)
    explicacion_control_es: Mapped[str | None] = mapped_column(Text, nullable=True)
    explicacion_control_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    dominio: Mapped["Dominio"] = relationship(back_populates="preguntas")
