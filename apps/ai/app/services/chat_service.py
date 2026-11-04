"""
Chat service — validasi input, pembentukan konteks, dan formatter SSE.
"""
import json
import typing

from app.core.config import get_settings
from app.providers import ollama_client

settings = get_settings()

ALLOWED_ROLES = ("user", "assistant")


class ChatValidationError(Exception):
    """Request chat tidak valid."""


def validate_messages(raw_messages: list[dict]) -> list[dict[str, str]]:
    """
    Validasi daftar pesan dari BFF.

    Pesan dari klien hanya menerima peran user/assistant. Pesan system yang
    mencoba ikut dari klien diabaikan karena system prompt ditetapkan
    gateway, bukan pengguna.
    """
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ChatValidationError("Field 'messages' wajib berupa daftar pesan non-kosong.")

    if len(raw_messages) > settings.llm_max_history_messages:
        raise ChatValidationError(
            f"Maksimal {settings.llm_max_history_messages} pesan riwayat."
        )

    cleaned: list[dict[str, str]] = []
    for message in raw_messages:
        role = message.get("role")
        content = message.get("content")
        if role not in ALLOWED_ROLES:
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        if len(content) > settings.llm_max_message_chars:
            raise ChatValidationError(
                f"Maksimal {settings.llm_max_message_chars} karakter per pesan."
            )
        cleaned.append({"role": role, "content": content.strip()})

    if not cleaned:
        raise ChatValidationError("Tidak ada pesan valid.")

    return cleaned


def build_context(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Gabungkan system prompt gateway dengan riwayat tervalidasi."""
    return [
        {"role": "system", "content": settings.llm_system_prompt},
        *messages,
    ]


def _sse_event(event: dict) -> str:
    """Format satu event SSE."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def stream_chat(
    messages: list[dict[str, str]],
    model: str | None = None,
) -> typing.AsyncGenerator[str, None]:
    """
    Jalankan chat streaming dan hasilkan string SSE.

    Error upstream dikirim sebagai event SSE `type: error`, lalu stream
    ditutup — tidak ada fallback ke path lain, konsisten dengan kebijakan
    internal-only.
    """
    try:
        context = build_context(messages)
    except ChatValidationError as exc:
        yield _sse_event({"type": "error", "message": str(exc)})
        return

    async for event in ollama_client.stream_chat_completions(context, model=model):
        yield _sse_event(event)
