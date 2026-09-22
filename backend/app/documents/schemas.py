import uuid

from pydantic import BaseModel

from app.threat_model.schemas import CasoPreguntaOut


class DocumentoAnalizadoOut(BaseModel):
    id: uuid.UUID
    nombre_archivo: str
    clasificacion: str
    preguntas_recomendadas: list[CasoPreguntaOut]
