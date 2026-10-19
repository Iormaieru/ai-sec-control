import datetime as dt
import uuid

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.alertas.analisis import AspectoOut
from app.alertas.models import EstadoAlerta, FuenteRegla, ModoRegla, SeveridadAlerta


class ReglaCreate(BaseModel):
    nombre: str = Field(min_length=3, max_length=200)
    descripcion: str | None = None
    consulta: str = Field(min_length=3, max_length=1000)  # sintaxis de Skope IT, ej. `app like mcp`
    severidad: SeveridadAlerta = SeveridadAlerta.MEDIA
    activa: bool = True
    notificar_email: bool = True
    modo: ModoRegla = ModoRegla.ALERTA


class ReglaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=3, max_length=200)
    descripcion: str | None = None
    consulta: str | None = Field(default=None, min_length=3, max_length=1000)
    severidad: SeveridadAlerta | None = None
    activa: bool | None = None
    notificar_email: bool | None = None
    modo: ModoRegla | None = None


class ReglaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    descripcion: str | None
    consulta: str
    severidad: SeveridadAlerta
    activa: bool
    notificar_email: bool
    modo: ModoRegla
    fuente: FuenteRegla
    consultada_hasta: dt.datetime | None
    ultimo_error: str | None
    alertas_abiertas: int = 0  # nuevas + en revisión


class AlertaOut(BaseModel):
    id: uuid.UUID
    regla_id: uuid.UUID
    regla_nombre: str
    regla_fuente: FuenteRegla
    regla_tipo: str | None  # sólo fuente Tenable: servicio_ia_expuesto | fuera_de_cobertura
    app: str
    usuario: str
    estado: EstadoAlerta
    severidad: SeveridadAlerta
    primera_vez: dt.datetime
    ultima_vez: dt.datetime
    cantidad_eventos: int
    actividades: dict[str, int]
    caso_id: uuid.UUID | None
    caso_nombre: str | None
    caso_jira_key: str | None
    nota: str | None
    notificada_at: dt.datetime | None
    equipos: list[str]
    atendida_at: dt.datetime | None
    cerrada_at: dt.datetime | None
    updated_at: dt.datetime


class EventoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evento_id: str
    fecha: dt.datetime
    actividad: str | None
    sitio: str | None
    objeto: str | None
    datos: dict


class EquipoContextoOut(BaseModel):
    """Lo que dice Tenable del equipo de una alerta."""

    equipo: str
    en_tenable: bool
    con_inventario: bool = False
    tiene_agente: bool = False
    sistema_operativo: str | None = None
    software_ia: list[str] = []
    puertos_ia: list[dict] = []
    visto_at: dt.datetime | None = None


class AlertaOrigenOut(BaseModel):
    """Alerta de Netskope que originó una de Tenable (la actividad vista en ese equipo)."""

    id: uuid.UUID
    regla_nombre: str
    app: str
    usuario: str
    estado: EstadoAlerta
    severidad: SeveridadAlerta
    ultima_vez: dt.datetime


class AlertaDetalleOut(AlertaOut):
    eventos: list[EventoOut]  # los más recientes
    contexto_equipos: list[EquipoContextoOut]
    # Sólo en "equipo fuera de Tenable": las alertas de Netskope con actividad en ese equipo.
    alertas_origen: list[AlertaOrigenOut] = []
    # Sólo Netskope: lectura de la alerta (quién, desde dónde, qué hizo, contra qué, Netskope).
    analisis: list[AspectoOut] = []


class AlertaUpdate(BaseModel):
    estado: EstadoAlerta | None = None
    nota: str | None = Field(default=None, max_length=4000)


class VincularCasoIn(BaseModel):
    """Vincular a un caso existente (caso_id) o crear uno nuevo con el nombre de la app."""

    caso_id: uuid.UUID | None = None
    crear: bool = False


class ResumenAlertasOut(BaseModel):
    nuevas: int
    en_revision: int


class PruebaReglaOut(BaseModel):
    desde: dt.datetime
    hasta: dt.datetime
    cantidad: int
    por_app: dict[str, int]
    usuarios: int
    muestra: list[EventoOut]


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DestinatarioCreate(BaseModel):
    email: str = Field(max_length=320)
    nombre: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, valor: str) -> str:
        valor = valor.strip().lower()
        if not _EMAIL.match(valor):
            raise ValueError("Email inválido")
        return valor


class DestinatarioUpdate(BaseModel):
    nombre: str | None = Field(default=None, max_length=200)
    activo: bool | None = None


class DestinatarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    nombre: str | None
    activo: bool


class DestinatariosOut(BaseModel):
    destinatarios: list[DestinatarioOut]
    # A quién se manda hoy y de dónde sale: "plataforma", "variable" (AISEC_ALERTAS_EMAIL_DESTINO) o "ninguno".
    origen: str
    en_uso: list[str]
