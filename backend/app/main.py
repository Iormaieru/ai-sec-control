from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.casos.router import router as casos_router
from app.catalog.router import router as catalog_router
from app.core.config import get_settings
from app.threat_model.router import router as threat_model_router
from app.threat_model.router import score_router as threat_model_score_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI-SEC Control", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(auth_router)
    app.include_router(casos_router)
    app.include_router(catalog_router)
    app.include_router(threat_model_router)
    app.include_router(threat_model_score_router)

    return app


app = create_app()
