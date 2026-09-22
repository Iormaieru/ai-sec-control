import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.audit.mixin import AuditMixin
from app.db.base import Base


class CasoTipo(str, enum.Enum):
    CANDIDATO = "candidato"
    INGRESADO = "ingresado"
    HERRAMIENTA_TERCERO = "herramienta_tercero"


class CasoEstado(str, enum.Enum):
    ABIERTO = "abierto"
    EN_ANALISIS = "en_analisis"
    ESPERANDO_PROVEEDOR = "esperando_proveedor"
    CERRADO_APROBADO = "cerrado_aprobado"
    RECHAZADO = "rechazado"


class Caso(AuditMixin, Base):
    __tablename__ = "casos"

    gdld: Mapped[str | None] = mapped_column(String(100), nullable=True)
    empresa_responsable: Mapped[str] = mapped_column(String(200), nullable=False)
    nombre_proyecto: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[CasoTipo] = mapped_column(Enum(CasoTipo, name="caso_tipo"), nullable=False)
    estado: Mapped[CasoEstado] = mapped_column(
        Enum(CasoEstado, name="caso_estado"), nullable=False, default=CasoEstado.ABIERTO
    )

    contactos: Mapped[list["Contacto"]] = relationship(
        back_populates="caso", cascade="all, delete-orphan", order_by="Contacto.created_at"
    )


class Contacto(AuditMixin, Base):
    __tablename__ = "contactos"

    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rol: Mapped[str | None] = mapped_column(String(100), nullable=True)

    caso: Mapped["Caso"] = relationship(back_populates="contactos")
