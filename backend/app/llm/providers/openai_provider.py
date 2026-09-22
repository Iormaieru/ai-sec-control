"""Adapter concreto de LLMProvider para OpenAI. Usa chat.completions.parse()
del SDK oficial, que valida la respuesta del modelo contra un schema
Pydantic — evita el parseo manual/frágil de JSON de texto libre."""

import json

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.schemas import CatalogQuestionSummary, DocumentAnalysisResult, RecommendedQuestion

SYSTEM_PROMPT = (
    "Sos un analista de seguridad de IA del área AI-SEC de un banco. Se te da el texto de un "
    "documento de arquitectura o de un proyecto/herramienta que usa IA, y un catálogo de preguntas "
    "de modelado de amenazas (framework PLOT4AI). Tu trabajo es: (1) clasificar en una frase el "
    "tipo de solución de IA descripta, y (2) para cada pregunta del catálogo, decidir si aplica a "
    "esta solución específica y, si aplica, dar instrucciones concretas y accionables de cómo "
    "debería responderla el equipo del proyecto, en español y en inglés. No recomiendes preguntas "
    "que no tengan relación clara con lo que describe el documento."
)


class _LLMRecommendedQuestion(BaseModel):
    pregunta_id: str
    aplica: bool
    instrucciones_es: str
    instrucciones_en: str


class _LLMAnalysisResponse(BaseModel):
    clasificacion: str
    preguntas: list[_LLMRecommendedQuestion]


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError(
                "AISEC_OPENAI_API_KEY no está configurada. Definila en backend/.env o cambiá "
                "AISEC_LLM_PROVIDER a 'mock' para desarrollar sin llamadas reales."
            )
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def analyze_document(
        self, document_text: str, catalog: list[CatalogQuestionSummary]
    ) -> DocumentAnalysisResult:
        catalog_payload = [q.model_dump() for q in catalog]
        completion = self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Documento:\n{document_text}\n\n"
                        f"Catálogo de preguntas (JSON, un objeto por pregunta con "
                        f"pregunta_id/dominio_codigo/numero/texto_es/tier):\n"
                        f"{json.dumps(catalog_payload, ensure_ascii=False)}"
                    ),
                },
            ],
            response_format=_LLMAnalysisResponse,
        )

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("El proveedor no devolvió una respuesta parseable.")

        recomendadas = [
            RecommendedQuestion(
                pregunta_id=q.pregunta_id,
                instrucciones_es=q.instrucciones_es,
                instrucciones_en=q.instrucciones_en,
            )
            for q in parsed.preguntas
            if q.aplica
        ]
        return DocumentAnalysisResult(clasificacion=parsed.clasificacion, preguntas_recomendadas=recomendadas)
