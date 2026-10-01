import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.casos.models import CasoEstado, CasoTipo


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
    empresa_responsable: str
    nombre_proyecto: str
    tipo: CasoTipo

    _gdld = field_validator("gdld")(normalizar_gdld)


class CasoUpdate(BaseModel):
    gdld: str | None = None
    empresa_responsable: str | None = None
    nombre_proyecto: str | None = None
    estado: CasoEstado | None = None

    _gdld = field_validator("gdld")(normalizar_gdld)


class CasoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gdld: str | None
    empresa_responsable: str
    nombre_proyecto: str
    tipo: CasoTipo
    estado: CasoEstado
    created_at: datetime
    updated_at: datetime
    contactos: list[ContactoOut] = []
