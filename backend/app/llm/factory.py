from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.providers.mock_provider import MockProvider


class UnknownLLMProvider(Exception):
    pass


def get_llm_provider() -> LLMProvider:
    settings = get_settings()

    if settings.llm_provider == "mock":
        return MockProvider()

    if settings.llm_provider == "openai":
        from app.llm.providers.openai_provider import OpenAIProvider  # import diferido

        return OpenAIProvider()

    raise UnknownLLMProvider(f"Proveedor LLM desconocido: {settings.llm_provider!r}")
