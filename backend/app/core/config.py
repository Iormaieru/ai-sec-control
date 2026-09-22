from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AISEC_", extra="ignore")

    database_url: str = "postgresql+psycopg://aisec:aisec@localhost:5432/aisec"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 8

    environment: str = "development"

    # Coma-separado: orígenes del frontend autorizados a llamar a la API.
    cors_allowed_origins: str = "http://localhost:5173"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    # "mock" por default: un ambiente nuevo sin API key configurada no debe
    # romper al arrancar. Se pisa con AISEC_LLM_PROVIDER=openai (o el que
    # corresponda) una vez que hay una key real.
    llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()
