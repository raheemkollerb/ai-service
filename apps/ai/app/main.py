"""
FastAPI AI Gateway — jembatan BFF Express platform RCC ke runtime LLM lokal
di HPC (Mode B: gateway berjalan sebagai container Docker bersama Ollama).
"""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat
from app.core.config import get_settings
from app.providers.ollama_client import close_client
from app.models import HealthResponse

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_client()


app = FastAPI(
    title="Research Control Center - AI Gateway",
    description="Pintu terkontrol menuju LLM lokal (HPC) untuk asisten AI platform.",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.environment == "development" else None,
    lifespan=lifespan,
)

_cors_origins = [
    origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*", "X-Service-Key"],
)

app.include_router(chat.router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Public health endpoint untuk container checks (ringan, tanpa probe LLM)."""
    return HealthResponse(
        status="healthy",
        service="ai-gateway",
        timestamp=datetime.utcnow(),
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Research Control Center - AI Gateway",
        "version": "0.1.0",
        "status": "running",
        "llm_model": settings.llm_model,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
    )
