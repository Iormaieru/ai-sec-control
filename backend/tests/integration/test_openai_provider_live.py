"""Único test que hace una llamada de red real a la API de OpenAI —
deliberadamente separado del resto (nunca corre en un ambiente sin
AISEC_OPENAI_API_KEY, y no participa de ningún golden test: el objetivo es
sólo confirmar que la integración real habla el mismo protocolo que el
cliente mockeado en tests/unit/test_openai_provider.py)."""

import pytest

from app.core.config import get_settings
from app.llm.schemas import CatalogQuestionSummary

pytestmark = pytest.mark.skipif(
    not get_settings().openai_api_key, reason="AISEC_OPENAI_API_KEY no configurada"
)


def test_analyze_document_against_real_openai_api() -> None:
    from app.llm.providers.openai_provider import OpenAIProvider

    catalog = [
        CatalogQuestionSummary(
            pregunta_id="DDG-01",
            dominio_codigo="DDG",
            numero=1,
            texto_es="¿Nuestros datos están completos, actualizados y son confiables?",
            tier="critico",
        ),
        CatalogQuestionSummary(
            pregunta_id="TAC-05",
            dominio_codigo="TAC",
            numero=5,
            texto_es="¿Es fácil para los usuarios aprender a utilizar y manejar el sistema de IA?",
            tier="estandar",
        ),
    ]
    documento = (
        "Sistema de scoring crediticio basado en un modelo de machine learning entrenado con "
        "datos históricos de clientes del banco (ingresos, historial de pagos, deuda actual). "
        "El modelo se usa para aprobar o rechazar solicitudes de préstamos personales de forma "
        "automática, sin revisión humana en la mayoría de los casos."
    )

    result = OpenAIProvider().analyze_document(documento, catalog)

    assert result.clasificacion
    assert isinstance(result.preguntas_recomendadas, list)
    for recomendada in result.preguntas_recomendadas:
        assert recomendada.pregunta_id in {q.pregunta_id for q in catalog}
        assert recomendada.instrucciones_es
        assert recomendada.instrucciones_en
