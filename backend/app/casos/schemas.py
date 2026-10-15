import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.casos.models import CasoEstado, CasoTipo, JiraSyncEstado, Origen
from app.core.config import get_settings


class ContactoCreate(BaseModel):
    nombre: str
    email: str | None = None
    rol: str | None = None


class ContactoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    email: str | None
    rol: str | None


_GDLD_PREFIJO = re.compile(r"^\s*GDLD\s*(N[°º]?\.?)?\s*[-:#]?\s*", re.IGNORECASE)


def normalizar_gdld(value: str | None) -> str | None:
    """Se guarda sólo el número; la UI lo muestra como "GDLD 12190". Acepta
    que lo peguen con el prefijo ("GDLD-12190", "GDLD N° 12190")."""
    if value is None:
        return None
    numero = _GDLD_PREFIJO.sub("", value).strip()
    if not numero:
        return None
    if not numero.isdigit():
        raise ValueError("El GDLD debe ser un número")
    return numero


class CasoCreate(BaseModel):
    gdld: str | None = None
    empresa_responsable: str | None = None
    nombre_proyecto: str = Field(min_length=1, max_length=200)
    tipo: CasoTipo | None = None
    # "Tipo de solicitud" del ticket en Jira; sin indicar, el primero configurado.
    tipo_solicitud_id: str | None = None

    _gdld = field_validator("gdld")(normalizar_gdld)

    @field_validator("tipo_solicitud_id")
    @classmethod
    def _tipo_solicitud_valido(cls, value: str | None) -> str | None:
        if value is not None and value not in get_settings().jira_request_types:
            raise ValueError("Tipo de solicitud desconocido")
        return value


class CasoUpdate(BaseModel):
    gdld: str | None = None
    empresa_responsable: str | None = None
    nombre_proyecto: str | None = Field(default=None, min_length=1, max_length=200)
    tipo: CasoTipo | None = None
    # Sólo para casos no vinculados a Jira; los demás usan /transiciones.
    estado: CasoEstado | None = None

    _gdld = field_validator("gdld")(normalizar_gdld)


class CasoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gdld: str | None
    empresa_responsable: str | None
    nombre_proyecto: str
    tipo: CasoTipo | None
    estado: CasoEstado
    origen: Origen
    jira_issue_key: str | None
    jira_status_nombre: str | None
    jira_tipo_solicitud_id: str | None
    jira_asignado_id: str | None
    jira_asignado_nombre: str | None
    jira_asignado_avatar_url: str | None
    jira_sync_estado: JiraSyncEstado | None
    jira_sync_error: str | None
    created_at: datetime
    updated_at: datetime
    contactos: list[ContactoOut] = []

    @computed_field
    @property
    def jira_url(self) -> str | None:
        if not self.jira_issue_key:
            return None
        return f"{get_settings().jira_base_url.rstrip('/')}/browse/{self.jira_issue_key}"


class ComentarioCreate(BaseModel):
    cuerpo: str = Field(min_length=1, max_length=10000)


class ComentarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cuerpo: str
    autor_nombre: str
    origen: Origen
    publico: bool
    jira_comment_id: str | None
    fecha: datetime


class TransicionOut(BaseModel):
    id: str
    nombre: str
    destino: str
    estado: CasoEstado


class TransicionIn(BaseModel):
    transition_id: str = Field(min_length=1, max_length=32)


class PersonaJiraOut(BaseModel):
    account_id: str
    nombre: str
    avatar_url: str | None


class AsignarIn(BaseModel):
    # None = sin asignar. Formato de accountId de Atlassian (ej. "712020:8f88...").
    account_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9:\-]{1,128}$")


class TipoSolicitudOut(BaseModel):
    id: str
    nombre: str
