import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.audit.mixin import AuditMixin
from app.db.base import Base
from app.threat_model.enums import RespuestaValor


class CasoPregunta(AuditMixin, Base):
    """Una pregunta del catálogo maestro puesta 'en alcance' para un caso
    concreto — el equivalente a la copia manual a un Excel con sólo las
    preguntas pertinentes a esa solución."""

    __tablename__ = "caso_preguntas"
    __table_args__ = (UniqueConstraint("caso_id", "pregunta_id", name="uq_caso_pregunta"),)

    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), nullable=False)
    pregunta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("preguntas.id"), nullable=False)

    caso: Mapped["Caso"] = relationship()  # noqa: F821
    pregunta: Mapped["Pregunta"] = relationship()  # noqa: F821
    respuesta: Mapped["CasoRespuesta"] = relationship(
        back_populates="caso_pregunta", uselist=False, cascade="all, delete-orphan"
    )


class CasoRespuesta(AuditMixin, Base):
    """Columnas H, M-U de una fila del Excel. Las columnas calculadas
    (Estado/Pts./Máx./Gap/Riesgo Residual, I/J/K/L/O) no se guardan: se
    derivan en threat_model/scoring.py a partir de esta respuesta."""

    __tablename__ = "caso_respuestas"

    caso_pregunta_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("caso_preguntas.id"), unique=True, nullable=False
    )
    respuesta: Mapped[RespuestaValor] = mapped_column(
        Enum(RespuestaValor, name="respuesta_valor"), nullable=False, default=RespuestaValor.PENDIENTE
    )
    control_compensatorio: Mapped[str | None] = mapped_column(Text, nullable=True)
    factor_mitigacion_pct: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    owner_responsable: Mapped[str | None] = mapped_column(String(200), nullable=True)
    accion_remediacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_objetivo: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidencia_esperada: Mapped[str | None] = mapped_column(Text, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

    caso_pregunta: Mapped["CasoPregunta"] = relationship(back_populates="respuesta")
