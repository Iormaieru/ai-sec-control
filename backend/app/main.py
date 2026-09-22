from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.casos.router import router as casos_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI-SEC Control", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(auth_router)
    app.include_router(casos_router)

    return app


app = create_app()
