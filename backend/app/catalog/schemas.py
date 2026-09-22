import uuid

from pydantic import BaseModel, ConfigDict

from app.catalog.models import Polaridad, PreguntaTipo, Tier


class DominioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    nombre: str
    peso: float
    total_preguntas: int


class PreguntaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dominio_id: uuid.UUID
    numero: int
    texto_es: str
    texto_en: str
    tipo: PreguntaTipo
    polaridad: Polaridad
    tier: Tier
    multiplicador: int
    impacto_primario: str | None
    referencias_regulatorias: str | None
    justificacion_tier: str | None
    explicacion_control_es: str | None
    explicacion_control_en: str | None
