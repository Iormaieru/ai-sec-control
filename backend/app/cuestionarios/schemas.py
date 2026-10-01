import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.cuestionarios.models import InvitacionEstado
from app.threat_model.enums import RespuestaValor


class EnviarCuestionarioRequest(BaseModel):
    contacto_ids: list[uuid.UUID] = Field(min_length=1)


class InvitacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contacto_id: uuid.UUID
    contacto_nombre: str
    email: str
    estado: InvitacionEstado
    vencida: bool
    created_at: datetime
    expira_at: datetime
    abierta_at: datetime | None
    respondida_at: datetime | None
    # Sólo con AISEC_EMAIL_BACKEND=console y recién creada: el email no salió,
    # el analista copia el enlace a mano. Nunca se puede volver a obtener.
    enlace: str | None = None


# --- Formulario público (lo ve el contacto, sin login) ---


class PreguntaFormularioOut(BaseModel):
    pregunta_id: uuid.UUID
    dominio_codigo: str
    dominio_nombre: str
    numero: int
    texto_es: str
    explicacion_es: str | None
    instrucciones_es: str | None
    evidencia_esperada: str | None
    # Borrador guardado por el contacto, si lo hay.
    respuesta: RespuestaValor
    comentario: str | None


class FormularioOut(BaseModel):
    nombre_proyecto: str
    empresa_responsable: str
    contacto_nombre: str
    expira_at: datetime
    preguntas: list[PreguntaFormularioOut]


class RespuestaFormulario(BaseModel):
    pregunta_id: uuid.UUID
    respuesta: RespuestaValor = RespuestaValor.PENDIENTE
    comentario: str | None = Field(default=None, max_length=4000)


class RespuestasFormularioRequest(BaseModel):
    respuestas: list[RespuestaFormulario]


class EnvioResultadoOut(BaseModel):
    aplicadas: int
    # Ya las había respondido el equipo de seguridad: no se pisan.
    omitidas: int
