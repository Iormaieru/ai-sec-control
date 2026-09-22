import pytest

from app.core.config import Settings, get_settings
from app.llm.factory import UnknownLLMProvider, get_llm_provider
from app.llm.providers.mock_provider import MockProvider


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_default_llm_provider_is_mock() -> None:
    # _env_file=None: ignora backend/.env a propósito (en este repo tiene
    # AISEC_LLM_PROVIDER=openai para desarrollo local) para poder probar el
    # default de la clase Settings en sí, no lo que hay configurado acá.
    assert Settings(_env_file=None).llm_provider == "mock"


def test_explicit_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AISEC_LLM_PROVIDER", "mock")

    assert isinstance(get_llm_provider(), MockProvider)


def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AISEC_LLM_PROVIDER", "not-a-real-provider")

    with pytest.raises(UnknownLLMProvider):
        get_llm_provider()
