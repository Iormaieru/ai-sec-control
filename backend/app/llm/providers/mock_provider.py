"""Provider determinístico, sin red — usado en tests y disponible como
AISEC_LLM_PROVIDER=mock para desarrollar sin gastar cuota de API real."""

from app.llm.base import LLMProvider
from app.llm.schemas import CatalogQuestionSummary, DocumentAnalysisResult, DocumentImage, RecommendedQuestion


class MockProvider(LLMProvider):
    def analyze_document(
        self,
        document_text: str,
        catalog: list[CatalogQuestionSummary],
        images: list[DocumentImage] | None = None,
    ) -> DocumentAnalysisResult:
        # Aproximación determinística sin LLM real: recomienda las preguntas
        # Crítico de cada dominio presente en el catálogo pasado.
        recomendadas = [
            RecommendedQuestion(
                pregunta_id=q.pregunta_id,
                instrucciones_es=f"Verificar el control correspondiente a: {q.texto_es}",
                instrucciones_en="Verify the control that corresponds to this question.",
            )
            for q in catalog
            if q.tier == "critico"
        ]
        return DocumentAnalysisResult(
            clasificacion="Clasificación simulada (MockProvider, sin llamada real a un LLM)",
            preguntas_recomendadas=recomendadas,
        )
