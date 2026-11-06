"""
Chat service — validasi input, pembentukan konteks, formatter SSE, dan
loop tool analytics Tahap 2 (spec tahap-2-analytics-tools.md § 4, § 5).

Kegagalan satu tool tidak menghentikan stream: model diberi tahu hasil
gagal melalui observasi lalu narasi dilanjutkan. Setiap event tool_call
wajib memiliki pasangan tool_result dengan call_id yang sama.
"""
from __future__ import annotations

import json
import time
import typing

from app.core.config import get_settings
from app.core.tools_catalog import TOOL_SPECS, catalog_directive, parse_allowed_tools
from app.providers import analytics_client, ollama_client
from app.services import tool_service

settings = get_settings()

ALLOWED_ROLES = ("user", "assistant")

# Satu putaran re-invoke per prompt setelah observasi tool (§ 5).
_MAX_TOOL_ROUNDS = 1


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


def build_context(
    messages: list[dict[str, str]], system_directive: str = ""
) -> list[dict[str, str]]:
    """Gabungkan system prompt gateway (plus direktif tool saat aktif)."""
    system_text = settings.llm_system_prompt + system_directive
    return [
        {"role": "system", "content": system_text},
        *messages,
    ]


def _sse_event(event: dict) -> str:
    """Format satu event SSE."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


class _StreamCapture:
    """Wadah tangkapan marker JSON dari satu pass stream provider."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []  # (nama_tool, arguments)
        self.done_event: dict | None = None


# Ukuran window slide: pola terpanjang {"tool": ditambah variasi whitespace
# model (spasi/tab/newline) — 64 char aman untuk praktik streaming.
_CAPTURE_WINDOW = 64


async def _stream_capture(
    context: list[dict[str, str]],
    model: str | None,
    capture: _StreamCapture,
) -> typing.AsyncGenerator[dict, None]:
    """
    Streaming passthrough sambil menangkap marker JSON.

    Delta yang diproduksi provider bisa sekecil satu-dua karakter, sehingga
    kandidat `{"tool":` tidak selalu utuh dalam satu event; karenanya teks
    ditampung window mengambang dan dipindai ulang tiap chunk. Bagian sebelum
    kandidat marker tetap dialirkan; teks sejak kandidat ditahan (tidak
    diteruskan ke klien). Bila parse berhasil, marker masuk capture.calls dan
    sisa pass tuntas diperiksa untuk marker kedua; bila parse gagal, teks
    ditahan dilepas sebagai delta biasa.
    """
    marker_open = False
    pending = ""  # teks setelah kandidat marker terbuka
    tail = ""     # window mengambang sebelum kandidat terdeteksi

    async for event in ollama_client.stream_chat_completions(context, model=model):
        event_type = event.get("type")
        if event_type != "delta":
            if event_type == "done":
                capture.done_event = event
            else:
                yield event  # error upstream passthrough
            continue

        incoming = event.get("text", "")
        if marker_open:
            pending += incoming
            continue

        tail += incoming
        match = tool_service._MARKER_START.search(tail)
        if match is not None:
            prefix = tail[: match.start()]
            if prefix:
                yield {"type": "delta", "text": prefix}
            marker_open = True
            pending = tail[match.start() :]
            tail = ""
            continue
        # Tanpa kandidat: lepas seluruh teks kecuali trailing window agar
        # potongan kandidat yang terbelah tetap tertampung untuk chunk berikut.
        flush_upto = max(0, len(tail) - _CAPTURE_WINDOW)
        if flush_upto:
            yield {"type": "delta", "text": tail[:flush_upto]}
            tail = tail[flush_upto:]

    # Stream provider selesai — proses sisa.
    if not marker_open:
        if tail.strip():
            yield {"type": "delta", "text": tail}
        return

    while pending:
        candidates = tool_service.detect_marker_candidates(pending)
        usable = None
        for start, end in candidates:
            parsed = tool_service.parse_marker_json(pending[start : end + 1])
            if parsed is not None:
                usable = (start, end, parsed)
                break

        if usable is None:
            # Bukan marker yang sah — lepaskan sebagai delta biasa.
            if pending.strip():
                yield {"type": "delta", "text": pending}
            return

        start, end, (name, arguments) = usable
        capture.calls.append((name, arguments))
        pending = pending[end + 1 :]

        if pending.strip() and tool_service._MARKER_START.search(pending):
            continue  # marker berikutnya dalam jawaban yang sama
        if pending.strip():
            yield {"type": "delta", "text": pending}  # narasi sisa setelah marker
        return


async def _execute_tool_call(
    decision: tool_service.ToolCallDecision,
    call_id: str,
    rcc_cookie: str | None,
) -> tuple[dict, dict[str, str]]:
    """
    Eksekusi satu tool call: emit tool_result (tanpa raw data) dan sisipkan
    pasangan pesan konteks (assistant marker + observasi) untuk re-invoke.
    """
    name = decision.name
    spec = TOOL_SPECS[name]
    started = time.perf_counter()

    if not decision.allowed:
        status, reason = "denied", decision.reason
        observation = None
    elif not decision.args_valid:
        status, reason = "error", "invalid_parameters"
        observation = None
    else:
        endpoint_result = await analytics_client.call_endpoint(
            spec.method,
            spec.path,
            decision.cleaned_params or {},
            rcc_cookie,
            timeout=settings.tool_timeout,
        )
        if endpoint_result.data is not None:
            status, reason = "ok", None
            observation = tool_service.clamp_observation(endpoint_result.data)
        elif endpoint_result.error == "analytics_timeout":
            status, reason = "timeout", None
            observation = None
        else:
            status, reason = "error", endpoint_result.error
            observation = None

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    result_event = {
        "type": "tool_result",
        "call_id": call_id,
        "name": name,
        "status": status,
        "elapsed_ms": elapsed_ms,
    }
    if reason:
        result_event["reason"] = reason

    messages = [
        {
            "role": "assistant",
            "content": json.dumps(
                {"tool": name, "arguments": decision.arguments}, ensure_ascii=False
            ),
        },
        tool_service.observation_message(
            name, call_id, status, observation, reason
        ),
    ]
    return result_event, messages


async def stream_chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    rcc_cookie: str | None = None,
) -> typing.AsyncGenerator[str, None]:
    """
    Jalankan chat streaming dan hasilkan string SSE.

    Error upstream dikirim sebagai event SSE `type: error`, lalu stream
    ditutup — tidak ada fallback ke path lain, konsisten dengan kebijakan
    internal-only. Saat tools aktif, marker JSON dari ditangkap gateway,
    dieksekusi, lalu model di-invoke ulang untuk narasi berbasis angka.
    """
    try:
        cleaned_messages = validate_messages(messages)
    except ChatValidationError as exc:
        yield _sse_event({"type": "error", "message": str(exc)})
        return

    allowed = (
        parse_allowed_tools(settings.ai_tools) if settings.analytics_url else ()
    )

    if not allowed:
        context = build_context(cleaned_messages)
        async for event in ollama_client.stream_chat_completions(context, model=model):
            yield _sse_event(event)
        return

    context_state = build_context(cleaned_messages, catalog_directive(allowed))
    executed_calls = 0
    rounds_used = 0
    next_call_id = 1

    while True:
        capture = _StreamCapture()
        async for event in _stream_capture(context_state, model, capture):
            yield _sse_event(event)

        if not capture.calls:
            if capture.done_event is not None:
                yield _sse_event(capture.done_event)
            return

        context_pairs: list[dict[str, str]] = []
        for name, arguments in capture.calls:
            decision = tool_service.decide_tool_call(
                name,
                arguments,
                allowed,
                budget_left=(
                    rounds_used == 0 and executed_calls < settings.tool_max_calls
                ),
            )
            call_id = f"c{next_call_id}"
            next_call_id += 1
            yield _sse_event(
                {
                    "type": "tool_call",
                    "call_id": call_id,
                    "name": name,
                    "arguments": decision.cleaned_params
                    if decision.cleaned_params is not None
                    else decision.arguments,
                }
            )

            result_event, pair_messages = await _execute_tool_call(
                decision, call_id, rcc_cookie
            )
            yield _sse_event(result_event)
            executed_calls += 1 if decision.allowed else 0
            context_pairs.extend(pair_messages)

        if rounds_used >= _MAX_TOOL_ROUNDS:
            # Pass ini sudah final invocation — marker tersisa ditolak
            # (tool_limit) dan stream ditutup tanpa re-invoke baru (§ 5).
            if capture.done_event is not None:
                yield _sse_event(capture.done_event)
            return

        context_state = context_state + context_pairs
        rounds_used += 1
