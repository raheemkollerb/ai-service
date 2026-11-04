"""
Ollama client — adapter ke runtime LLM lokal via protokol OpenAI-compatible.

Dipilih protokol /v1 agar runtime dapat diganti (Ollama -> vLLM / llama.cpp)
tanpa mengubah kode di atas adapter ini.
"""
import json
import typing

import httpx

from app.core.config import get_settings

settings = get_settings()

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Single shared AsyncClient (satu event loop FastAPI)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=httpx.Timeout(settings.llm_timeout, connect=10.0),
        )
    return _client


async def close_client() -> None:
    """Tutup client saat aplikasi berhenti."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


class UpstreamUnavailable(Exception):
    """LLM runtime tidak dapat dihubungi."""


async def list_models() -> list[str]:
    """Daftar model yang tersedia di runtime lokal (untuk health check)."""
    try:
        response = await get_client().get("/models", timeout=10.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise UpstreamUnavailable(str(exc)) from exc
    return [item["id"] for item in payload.get("data", [])]


async def stream_chat_completions(
    messages: list[dict[str, str]],
    model: str | None = None,
) -> typing.AsyncGenerator[dict, None]:
    """
    Streaming chat completions.

    Menghasilkan event dict:
      {"type": "delta", "text": str}
      {"type": "done", "finish_reason": str | None, "usage": dict | None}
      {"type": "error", "message": str}
    """
    payload = {
        "model": model or settings.llm_model,
        "messages": messages,
        "stream": True,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }

    try:
        async with get_client().stream(
            "POST",
            "/chat/completions",
            json=payload,
        ) as response:
            if response.status_code >= 400:
                body = await response.aread()
                detail = body.decode("utf-8", errors="replace")
                yield {
                    "type": "error",
                    "message": (
                        "LLM runtime menolak permintaan "
                        f"(HTTP {response.status_code}): {detail[:500]}"
                    ),
                }
                return
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if text:
                    yield {"type": "delta", "text": text}
                finish_reason = choice.get("finish_reason")
                if finish_reason is not None:
                    yield {
                        "type": "done",
                        "finish_reason": finish_reason,
                        "usage": chunk.get("usage"),
                    }
    except httpx.HTTPError as exc:
        yield {
            "type": "error",
            "message": f"LLM runtime tidak dapat dihubungi: {exc}",
        }
