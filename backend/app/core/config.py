from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRET = "change-me-in-production"
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AISEC_", extra="ignore")

    database_url: str = "postgresql+psycopg://aisec:aisec@localhost:5432/aisec"
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 8

    environment: str = "development"

    # Pool de conexiones por instancia del backend. En Cloud Run cada
    # instancia abre su propio pool y Cloud SQL limita las conexiones
    # totales (según el tier): pool_size * instancias máximas debe quedar
    # por debajo de ese límite.
    db_pool_size: int = 5
    db_max_overflow: int = 2

    # Logging. Los logs salen por stdout: Cloud Run los captura en Cloud
    # Logging y Dynatrace los toma desde ahí (integración con Google Cloud).
    log_level: str = "INFO"
    # "json" | "text". Sin definir: json fuera de development (lo que
    # espera Cloud Logging/Dynatrace) y text legible en desarrollo.
    log_format: str | None = None
    # Opcional: con el ID del proyecto se emite logging.googleapis.com/trace
    # para que Cloud Logging asocie cada log con la traza de su request.
    gcp_project_id: str | None = None

    @property
    def effective_log_format(self) -> str:
        if self.log_format:
            return self.log_format
        return "text" if self.environment == "development" else "json"

    @model_validator(mode="after")
    def _reject_weak_secrets_outside_development(self) -> "Settings":
        if self.environment != "development" and (
            self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < MIN_JWT_SECRET_LENGTH
        ):
            raise ValueError(
                "AISEC_JWT_SECRET es el valor por defecto o tiene menos de "
                f"{MIN_JWT_SECRET_LENGTH} caracteres, y AISEC_ENVIRONMENT no es 'development'. "
                "Definí un secreto propio (ej. desde Secret Manager)."
            )
        return self

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

    # Cuestionarios por email (app/cuestionarios). "console" por default: no
    # envía nada, loguea el aviso y la API devuelve el enlace para copiarlo
    # a mano. Con AISEC_EMAIL_BACKEND=smtp sale por el relay configurado.
    email_backend: str = "console"
    email_from: str = "ai-sec-control@localhost"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    # URL pública del frontend: base de los enlaces que reciben los contactos.
    frontend_base_url: str = "http://localhost:5173"
    cuestionario_validez_dias: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()
