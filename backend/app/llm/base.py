"""LLMProvider: la interfaz agnóstica de proveedor. Un solo método de
negocio (no un passthrough genérico de chat) porque el análisis de
documento de Módulo 1 y Módulo 2 quedó unificado — ver docs/SPEC.md y
tasks/plan.md, sección Incremento 2. Cada adapter concreto
(providers/openai_provider.py, ...) implementa esta interfaz y es libre
de decidir sus propios prompts/parsing; nada por encima de
llm/factory.py debería importar un provider concreto."""

from abc import ABC, abstractmethod

from app.llm.schemas import CatalogQuestionSummary, DocumentAnalysisResult


class LLMProvider(ABC):
    @abstractmethod
    def analyze_document(
        self, document_text: str, catalog: list[CatalogQuestionSummary]
    ) -> DocumentAnalysisResult:
        """Clasifica el tipo de solución de IA descripta en `document_text` y
        recomienda cuáles de las preguntas de `catalog` aplican, con
        instrucciones de cómo responder cada una en español e inglés."""
        raise NotImplementedError
