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


class ToolSummary(BaseModel):
    """Una herramienta de pentesting descubierta, para que el LLM decida en
    qué pasos de los estándares sirve."""

    nombre: str
    descripcion: str | None
    temas: list[str]
    readme: str | None  # extracto


class StepSummary(BaseModel):
    """Un paso de un estándar de pentesting (OWASP LLM, ML, ATLAS, ...)."""

    codigo: str  # "LLM01", "ML01", "AML.TA0005", ...
    estandar: str
    titulo: str
    descripcion: str | None


class SuggestedStep(BaseModel):
    codigo: str
    justificacion: str
