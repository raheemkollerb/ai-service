"""
Chat API — endpoint streaming SSE untuk BFF Express.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import verify_service_key
from app.providers import ollama_client
from app.providers.ollama_client import UpstreamUnavailable
from app.services import chat_service
from app.services.chat_service import ChatValidationError

settings = get_settings()
router = APIRouter(
    prefix="/ai",
    tags=["ai"],
    dependencies=[Depends(verify_service_key)],
)


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn] = Field(default_factory=list)
    model: str | None = None


class HealthUpstream(BaseModel):
    llm_base_url: str
    model: str
    available: bool
    models: list[str] | None = None
    detail: str | None = None


@router.post(
    "/chat",
    summary="Chat streaming terhadap LLM lokal (SSE)",
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def chat(request: Request, chat_request: ChatRequest) -> StreamingResponse:
    """
    Terima riwayat percakapan dari BFF, streaming balasan LLM lokal.

    Protokol SSE:
      data: {"type": "delta", "text": "..."}
      data: {"type": "tool_call", "call_id": "c1", "name": "...", "arguments": {...}}
      data: {"type": "tool_result", "call_id": "c1", "name": "...",
             "status": "ok|error|denied|timeout", "elapsed_ms": 148}
      data: {"type": "done", "finish_reason": "...", "usage": {...}}
      data: {"type": "error", "message": "..."}

    Header X-Rcc-Cookie (raw cookie sesi dari BFF) diteruskan verbatim ke
    analytics saat tool dijalankan — tidak pernah di-log.
    """
    try:
        messages = chat_service.validate_messages(
            [message.model_dump() for message in chat_request.messages]
        )
    except ChatValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    requested_model = chat_request.model
    if requested_model != settings.llm_model:
        # Whitelist sederhana: hanya model yang ter-set di konfigurasi diizinkan.
        requested_model = None

    # Passthrough mentah cookie sesi (X-Rcc-Cookie dari BFF) — tidak di-log.
    raw_cookie = request.headers.get("x-rcc-cookie")
    rcc_cookie = raw_cookie if raw_cookie else None

    return StreamingResponse(
        chat_service.stream_chat(messages, model=requested_model, rcc_cookie=rcc_cookie),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health/upstream", response_model=HealthUpstream)
async def health_upstream() -> JSONResponse:
    """
    Cek ketersediaan runtime LLM lokal di HPC (dedicated endpoint).

    Runtime hidup -> 200 {available: true, models: [...]}.
    Runtime mati  -> 503 yang tetap berbentuk HealthUpstream (flat), bukan
    dibungkus {"detail": {...}}, agar passthrough BFF tetap kontrak.
    """
    try:
        models = await ollama_client.list_models()
    except UpstreamUnavailable as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthUpstream(
                llm_base_url=settings.llm_base_url,
                model=settings.llm_model,
                available=False,
                detail=str(exc),
            ).model_dump(),
        )
    return JSONResponse(
        content=HealthUpstream(
            llm_base_url=settings.llm_base_url,
            model=settings.llm_model,
            available=True,
            models=models,
        ).model_dump(),
    )
