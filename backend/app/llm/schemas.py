from pydantic import BaseModel


class DocumentImage(BaseModel):
    """Una imagen extraída del documento (página de PDF rasterizada, o
    imagen embebida en un .docx) para mandarle a un proveedor con visión.
    Un proveedor sin soporte de imágenes puede simplemente ignorar esta
    lista — no rompe la interfaz."""

    content: bytes
    media_type: str  # "image/png", "image/jpeg", etc.


class CatalogQuestionSummary(BaseModel):
    """Lo mínimo que el LLM necesita ver de una pregunta del catálogo para
    decidir si aplica a la solución descripta en el documento."""

    pregunta_id: str
    dominio_codigo: str
    numero: int
    texto_es: str
    tier: str


class RecommendedQuestion(BaseModel):
    pregunta_id: str
    instrucciones_es: str
    instrucciones_en: str


class DocumentAnalysisResult(BaseModel):
    clasificacion: str
    preguntas_recomendadas: list[RecommendedQuestion]
