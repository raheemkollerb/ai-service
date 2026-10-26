from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router
from app.core.config import get_settings
from app.models import HealthResponse
from app.providers.ollama_client import close_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="RCC - AI Gateway",
        version="0.1.0",
        openapi_url="/openapi.json" if settings.is_development else None,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-Service-Key", "Content-Type"],
    )
    application.include_router(router)

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.get("/")
    async def root() -> dict:
        return {
            "service": "RCC - AI Gateway",
            "environment": settings.environment,
            "llm_model": settings.llm_model,
        }

    return application


app = create_app()
