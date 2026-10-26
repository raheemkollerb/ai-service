import json
from typing import AsyncIterator

from app.core.config import get_settings


class ChatValidationError(Exception):
    pass


def validate_messages(raw_messages: list[dict]) -> list[dict]:
    settings = get_settings()
    sanitized: list[dict] = []
    for message in raw_messages:
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        stripped = content.strip()
        if not stripped:
            continue
        if len(stripped) > settings.llm_max_message_chars:
            raise ChatValidationError(
                f"Pesan terlalu panjang (maksimum {settings.llm_max_message_chars} karakter)."
            )
        sanitized.append({"role": role, "content": stripped})
    if not sanitized:
        raise ChatValidationError("Tidak ada pesan yang valid untuk dikirim ke model.")
    if len(sanitized) > settings.llm_max_history_messages:
        raise ChatValidationError(
            f"Riwayat percakapan terlalu panjang (maksimum {settings.llm_max_history_messages} pesan)."
        )
    return sanitized


def build_context(messages: list[dict]) -> list[dict]:
    settings = get_settings()
    return [{"role": "system", "content": settings.llm_system_prompt}, *messages]


def format_sse_frame(event: dict) -> str:
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
