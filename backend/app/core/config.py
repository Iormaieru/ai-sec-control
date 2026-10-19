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

    # Integración con Jira Cloud (app/integraciones/jira + worker/). Apagada
    # por default: nada sale a la red (tests, ambientes sin credenciales). Los
    # casos igual se encolan, así que al prenderla el worker envía los pendientes.
    jira_enabled: bool = False
    jira_base_url: str = "https://bancomacro.atlassian.net"
    jira_email: str | None = None
    jira_api_token: str | None = None
    jira_project_key: str = "MDA"
    jira_issue_type_id: str = "11144"  # "Solicitudes" (Jira Service Management)
    jira_board_id: int = 12753  # tablero IA-SEC: su filtro define qué tickets son casos
    # Id -> nombre de los "Tipo de solicitud" (customfield_10067) que se
    # ofrecen al crear un caso; el primero es el default.
    jira_request_types: dict[str, str] = {
        "243": "Revisión Seguridad IA",
        "544": "Soporte a Implementaciones / Req. Menores IA",
    }
    jira_gdld_field: str = "customfield_13707"  # "Número de Tarjeta GDLD"
    jira_request_type_field: str = "customfield_10067"
    # Secreto que debe mandar la regla de Jira Automation en el header
    # X-Aisec-Secret (POST /integraciones/jira/webhook). Sin definir, el
    # endpoint responde 404.
    jira_webhook_secret: str | None = None
    # Worker (worker/): cada cuántos segundos trae los cambios de Jira. Los
    # cambios de la plataforma no esperan este intervalo: llegan por NOTIFY.
    jira_sync_intervalo_segundos: int = 120

    # Herramientas de pentesting (worker/aisec_worker/herramientas): revisión
    # del Catálogo y descubrimiento para el Radar. Token de GitHub de sólo
    # lectura pública (sin él, GitHub limita a 60 consultas por hora).
    github_token: str | None = None
    herramientas_revision_dias: int = 15

    # Alertas desde Netskope (app/alertas + worker/aisec_worker/alertas): el
    # worker consulta la API v2 con las reglas activas cada intervalo. La
    # demora cubre la ingesta de Netskope (los eventos tardan en aparecer).
    netskope_enabled: bool = False
    netskope_tenant_url: str = "https://bancomacro.goskope.com"
    netskope_api_token: str | None = None
    netskope_intervalo_segundos: int = 300
    netskope_demora_minutos: int = 10
    netskope_retrospectiva_dias: int = 7  # primera consulta de una regla nueva
    # Tenable Vulnerability Management (cloud): inventario por equipo para
    # correlacionar con Netskope. El worker lo actualiza cada N horas (la
    # exportación de ~11 mil equipos tarda varios minutos).
    tenable_enabled: bool = False
    tenable_base_url: str = "https://cloud.tenable.com"
    tenable_access_key: str | None = None
    tenable_secret_key: str | None = None
    tenable_intervalo_horas: int = 24

    # Coma-separado: casillas que reciben el resumen de alertas nuevas.
    alertas_email_destino: str | None = None

    @property
    def alertas_email_destino_list(self) -> list[str]:
        return [e.strip() for e in (self.alertas_email_destino or "").split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
