import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

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


class CasoCreate(BaseModel):
    gdld: str | None = None
    empresa_responsable: str
    nombre_proyecto: str
    tipo: CasoTipo


class CasoUpdate(BaseModel):
    gdld: str | None = None
    empresa_responsable: str | None = None
    nombre_proyecto: str | None = None
    estado: CasoEstado | None = None


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
