import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.security import verify_service_key
from app.models.base import ChatRequest
from app.providers.ollama_client import UpstreamUnavailable, list_models, stream_chat_completions
from app.services.chat_service import (
    ChatValidationError,
    build_context,
    format_sse_frame,
    validate_messages,
)

router = APIRouter(prefix="/ai", dependencies=[Depends(verify_service_key)])


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    settings = get_settings()
    model = settings.llm_model
    if request.model and request.model == settings.llm_model:
        model = request.model
    try:
        messages = validate_messages([message.model_dump() for message in request.messages])
    except ChatValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    context = build_context(messages)
    return StreamingResponse(
        (
            format_sse_frame(event)
            async for event in stream_chat_completions(context, model)
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/health/upstream")
async def health_upstream() -> dict:
    settings = get_settings()
    try:
        models = await list_models()
    except (UpstreamUnavailable, httpx.HTTPError) as exc:
        return {
            "llm_base_url": settings.llm_base_url,
            "model": settings.llm_model,
            "available": False,
            "error": str(exc),
        }
    return {
        "llm_base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "available": True,
        "models": models,
    }
