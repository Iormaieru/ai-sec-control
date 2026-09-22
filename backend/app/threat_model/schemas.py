import uuid
from datetime import date

from pydantic import BaseModel

from app.catalog.models import Tier
from app.threat_model.enums import Estado, RespuestaValor


class SeleccionarPreguntasRequest(BaseModel):
    pregunta_ids: list[uuid.UUID] = []
    dominio_codigo: str | None = None


class RespuestaUpdate(BaseModel):
    respuesta: RespuestaValor
    control_compensatorio: str | None = None
    factor_mitigacion_pct: int | None = None
    owner_responsable: str | None = None
    accion_remediacion: str | None = None
    fecha_objetivo: date | None = None
    evidencia_esperada: str | None = None
    observaciones: str | None = None


class CasoPreguntaOut(BaseModel):
    caso_pregunta_id: uuid.UUID
    pregunta_id: uuid.UUID
    dominio_codigo: str
    numero: int
    texto_es: str
    texto_en: str
    tier: Tier
    multiplicador: int
    respuesta: RespuestaValor
    estado: Estado
    pts_obtenidos: float | None
    maximo_aplicable: float
    riesgo_residual: float | None
    control_compensatorio: str | None
    factor_mitigacion_pct: int | None
    owner_responsable: str | None
    accion_remediacion: str | None
    fecha_objetivo: date | None
    evidencia_esperada: str | None
    observaciones: str | None
