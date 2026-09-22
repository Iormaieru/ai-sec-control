from pydantic import BaseModel


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
