import pytest
from sqlalchemy.engine import make_url

from app.core.config import DEFAULT_JWT_SECRET, Settings

STRONG_SECRET = "x" * 40


def test_development_permite_el_secreto_por_defecto() -> None:
    settings = Settings(_env_file=None, environment="development", jwt_secret=DEFAULT_JWT_SECRET)

    assert settings.jwt_secret == DEFAULT_JWT_SECRET


def test_produccion_rechaza_el_secreto_por_defecto() -> None:
    with pytest.raises(ValueError, match="AISEC_JWT_SECRET"):
        Settings(_env_file=None, environment="production", jwt_secret=DEFAULT_JWT_SECRET)


def test_produccion_rechaza_un_secreto_corto() -> None:
    with pytest.raises(ValueError, match="AISEC_JWT_SECRET"):
        Settings(_env_file=None, environment="production", jwt_secret="corto")


def test_produccion_acepta_un_secreto_fuerte() -> None:
    settings = Settings(_env_file=None, environment="production", jwt_secret=STRONG_SECRET)

    assert settings.environment == "production"


def test_url_de_cloud_sql_por_socket_unix_se_interpreta_bien() -> None:
    """Cloud Run monta la instancia en /cloudsql/<conexión>; psycopg recibe
    ese path como `host`. Una contraseña con caracteres especiales va
    URL-encoded."""
    url = make_url(
        "postgresql+psycopg://aisec_app:p%40ss%2Fw0rd@/aisec"
        "?host=/cloudsql/mi-proyecto:southamerica-east1:aisec-db"
    )

    assert url.host is None
    assert url.query["host"] == "/cloudsql/mi-proyecto:southamerica-east1:aisec-db"
    assert url.password == "p@ss/w0rd"
    assert url.database == "aisec"


def test_pool_configurable_por_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AISEC_DB_POOL_SIZE", "3")
    monkeypatch.setenv("AISEC_DB_MAX_OVERFLOW", "1")

    settings = Settings(_env_file=None)

    assert (settings.db_pool_size, settings.db_max_overflow) == (3, 1)
