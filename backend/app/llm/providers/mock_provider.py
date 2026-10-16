"""Provider determinístico, sin red — usado en tests y disponible como
AISEC_LLM_PROVIDER=mock para desarrollar sin gastar cuota de API real."""

from app.llm.base import LLMProvider
from app.llm.schemas import (
    CatalogQuestionSummary,
    DocumentAnalysisResult,
    DocumentImage,
    RecommendedQuestion,
    StepSummary,
    SuggestedStep,
    ToolSummary,
)

# Para suggest_tool_steps: palabra clave (en temas o descripción) -> pasos.
_PASOS_POR_PALABRA = {
    "prompt-injection": ["LLM01", "RT05"],
    "injection": ["LLM01"],
    "jailbreak": ["RT04"],
    "guardrail": ["LLM01", "RT04"],
    "red-team": ["RT03"],
    "adversarial": ["ML01", "DL02", "DL03"],
    "poison": ["ML02", "DL05"],
    "privacy": ["ML04", "DL07"],
    "membership": ["ML04", "DL07"],
    "extraction": ["ML05", "DL06"],
}


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

    def suggest_tool_steps(self, tool: ToolSummary, steps: list[StepSummary]) -> list[SuggestedStep]:
        # Coincidencia de palabras clave: determinística, sin LLM real.
        texto = " ".join([*tool.temas, tool.descripcion or ""]).lower()
        disponibles = {s.codigo for s in steps}
        codigos: list[str] = []
        for palabra, pasos in _PASOS_POR_PALABRA.items():
            if palabra in texto:
                codigos += [c for c in pasos if c in disponibles and c not in codigos]
        return [SuggestedStep(codigo=c, justificacion=f"Sugerencia simulada (MockProvider) para {tool.nombre}") for c in codigos]
