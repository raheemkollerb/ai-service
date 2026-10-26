import json
from typing import AsyncIterator

import httpx

from app.core.config import get_settings

_client: httpx.AsyncClient | None = None


class UpstreamUnavailable(Exception):
    pass


def _normalized_base_url() -> str:
    return get_settings().llm_base_url.rstrip("/") + "/"


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = httpx.AsyncClient(
            base_url=_normalized_base_url(),
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=httpx.Timeout(settings.llm_timeout, connect=10.0),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def list_models() -> list[str]:
    try:
        response = await get_client().get("models")
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise UpstreamUnavailable(str(exc)) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstreamUnavailable(f"respons tidak valid dari LLM runtime: {exc}") from exc
    return [item["id"] for item in payload.get("data", []) if isinstance(item, dict) and item.get("id")]


async def stream_chat_completions(
    messages: list[dict], model: str
) -> AsyncIterator[dict]:
    settings = get_settings()
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }
    try:
        async with get_client().stream("POST", "chat/completions", json=payload) as response:
            if response.status_code >= 400:
                detail = (await response.aread()).decode("utf-8", "replace")
                yield {
                    "type": "error",
                    "message": f"LLM runtime menolak permintaan (HTTP {response.status_code}): {detail[:500]}",
                }
                return
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                chunk_text = line[len("data:"):].strip()
                if chunk_text == "[DONE]":
                    break
                try:
                    chunk = json.loads(chunk_text)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if content:
                    yield {"type": "delta", "text": content}
                finish_reason = choice.get("finish_reason")
                if finish_reason is not None:
                    done_event: dict = {"type": "done", "finish_reason": finish_reason}
                    usage = chunk.get("usage")
                    if usage is not None:
                        done_event["usage"] = usage
                    yield done_event
    except httpx.HTTPError as exc:
        yield {"type": "error", "message": f"LLM runtime tidak dapat dihubungi: {exc}"}
