"""Tests del adapter de OpenAI con el cliente mockeado — nunca hace una
llamada de red real. Ver tests/integration/test_openai_provider_live.py
para el smoke test opcional contra la API real."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.llm.schemas import CatalogQuestionSummary


@pytest.fixture
def settings_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AISEC_OPENAI_API_KEY", "sk-test-fake-key")


def _catalog() -> list[CatalogQuestionSummary]:
    return [
        CatalogQuestionSummary(
            pregunta_id="p1", dominio_codigo="CYB", numero=1, texto_es="¿Pregunta?", tier="critico"
        ),
        CatalogQuestionSummary(
            pregunta_id="p2", dominio_codigo="CYB", numero=2, texto_es="¿Otra pregunta?", tier="alto"
        ),
    ]


def test_missing_api_key_raises() -> None:
    from app.llm.providers.openai_provider import OpenAIProvider

    with patch("app.llm.providers.openai_provider.get_settings", return_value=Settings(_env_file=None)):
        with pytest.raises(ValueError, match="AISEC_OPENAI_API_KEY"):
            OpenAIProvider()


def test_analyze_document_maps_applicable_questions_only(settings_with_key: None) -> None:
    from app.llm.providers.openai_provider import OpenAIProvider, _LLMAnalysisResponse, _LLMRecommendedQuestion

    fake_parsed = _LLMAnalysisResponse(
        clasificacion="Chatbot de atención al cliente basado en LLM",
        preguntas=[
            _LLMRecommendedQuestion(
                pregunta_id="p1", aplica=True, instrucciones_es="Verificar X", instrucciones_en="Verify X"
            ),
            _LLMRecommendedQuestion(
                pregunta_id="p2", aplica=False, instrucciones_es="", instrucciones_en=""
            ),
        ],
    )
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock(message=MagicMock(parsed=fake_parsed))]

    with patch("app.llm.providers.openai_provider.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.parse.return_value = fake_completion
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider()
        result = provider.analyze_document("texto del documento", _catalog())

    assert result.clasificacion == "Chatbot de atención al cliente basado en LLM"
    assert len(result.preguntas_recomendadas) == 1
    assert result.preguntas_recomendadas[0].pregunta_id == "p1"
    assert result.preguntas_recomendadas[0].instrucciones_es == "Verificar X"

    # Verifica que se haya pedido salida estructurada con nuestro schema
    _, kwargs = mock_client.chat.completions.parse.call_args
    assert kwargs["response_format"] is _LLMAnalysisResponse
    # temperature=0 + seed fijo: acota la variabilidad entre corridas
    assert kwargs["temperature"] == 0
    assert kwargs["seed"] == 42


def test_analyze_document_raises_if_response_not_parsed(settings_with_key: None) -> None:
    from app.llm.providers.openai_provider import OpenAIProvider

    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock(message=MagicMock(parsed=None))]

    with patch("app.llm.providers.openai_provider.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.parse.return_value = fake_completion
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider()
        with pytest.raises(RuntimeError):
            provider.analyze_document("texto", _catalog())


def test_factory_returns_openai_provider(settings_with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.llm.factory import get_llm_provider
    from app.llm.providers.openai_provider import OpenAIProvider

    monkeypatch.setenv("AISEC_LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    try:
        with patch("app.llm.providers.openai_provider.OpenAI"):
            provider = get_llm_provider()
        assert isinstance(provider, OpenAIProvider)
    finally:
        get_settings.cache_clear()
