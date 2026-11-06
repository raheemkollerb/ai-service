"""
Tool service — guardrail § 5, validasi parameter § 3.5, deteksi marker JSON,
dan clamp observasi (spec tahap-2-analytics-tools.md).

Semua kegagalan tool tidak menghentikan stream: hasil gagal diberi tahu ke
model lalu narasi dilanjutkan. Identitas pengguna selalu dari cookie sesi —
tidak pernah dari output model.
"""
from __future__ import annotations

import datetime
import json
import re
import typing

from app.core.config import get_settings
from app.core.tools_catalog import TOOL_SPECS, ToolSpec

settings = get_settings()

MARKER_KEY = "tool"
MARKER_ARGS_KEY = "arguments"

# Awal kandidat marker: {"tool" :  ... (satu-satunya pattern walau ada spasi)
_MARKER_START = re.compile(r"\{\s*\"tool\"\s*:")

_STATUS_OK = "ok"
_STATUS_ERROR = "error"
_STATUS_DENIED = "denied"
_STATUS_TIMEOUT = "timeout"


class ToolArgsError(Exception):
    """Parameter marker tidak sah (§ 3.5) — gagal lokal, tanpa request keluar."""


class ToolCallDecision(typing.NamedTuple):
    """Keputusan satu marker yang ditangkap dari stream."""

    name: str
    arguments: dict[str, typing.Any]
    allowed: bool                # di allowlist & budget tersedia
    reason: str | None           # not_allowed / tool_limit
    args_valid: bool             # hasil validasi parameter (hanya saat allowed)
    args_error: str | None
    cleaned_params: dict[str, str | int] | None


def detect_marker_candidates(text: str) -> list[tuple[int, int]]:
    """
    Cari seluruh selang kandidat marker JSON di satu teks (termasuk varian
    berpagar ```json ... ```). Mengembalikan daftar (start, end) inklusif
    pada substring JSON.
    """
    candidates: list[tuple[int, int]] = []
    for match in _MARKER_START.finditer(text):
        candidate = _balanced_json_span(text, match.start())
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _balanced_json_span(text: str, start: int) -> tuple[int, int] | None:
    """Selang kandidat JSON dari posisi `{` hingga kurung kurawal penutup yang seimbang."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return start, index
    return None  # belum lengkap / tidak seimbang


def parse_marker_json(span_text: str) -> tuple[str, dict] | None:
    """
    Uji satu teks kandidat sebagai marker resmi.
    Toleran pagar kode ``` / ```json yang menyertai (model kadang menulisnya).
    """
    cleaned = span_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    name = payload.get(MARKER_KEY)
    if not isinstance(name, str) or not name:
        return None
    arguments = payload.get(MARKER_ARGS_KEY)
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return None
    return name, arguments


def decide_tool_call(
    name: str,
    arguments: dict[str, typing.Any],
    allowed_tools: typing.Sequence[str],
    budget_left: bool,
) -> ToolCallDecision:
    """
    Terapkan guardrail § 5 + validasi § 3.5 untuk satu call.

    - nama di luar allowlist → denied (not_allowed), tanpa request analytics
    - budget habis → denied (tool_limit)
    - parameter di luar skema diabaikan; salah tipe/rentang → error lokal
    """
    if name not in allowed_tools:
        return ToolCallDecision(
            name=name,
            arguments=arguments,
            allowed=False,
            reason="not_allowed",
            args_valid=False,
            args_error=None,
            cleaned_params=None,
        )
    if not budget_left:
        return ToolCallDecision(
            name=name,
            arguments=arguments,
            allowed=False,
            reason="tool_limit",
            args_valid=False,
            args_error=None,
            cleaned_params=None,
        )
    try:
        cleaned = validate_tool_arguments(name, arguments)
    except ToolArgsError as exc:
        return ToolCallDecision(
            name=name,
            arguments=arguments,
            allowed=True,
            reason=None,
            args_valid=False,
            args_error=str(exc),
            cleaned_params=None,
        )
    return ToolCallDecision(
        name=name,
        arguments=arguments,
        allowed=True,
        reason=None,
        args_valid=True,
        args_error=None,
        cleaned_params=cleaned,
    )


def validate_tool_arguments(name: str, arguments: dict[str, typing.Any]) -> dict[str, str | int]:
    """
    Validasi parameter terhadap skema § 3.5; parameter wajib dilepas di sini
    (tidak diteruskan ke analytics), nilai luar rentang/ruang memicu error.
    """
    spec = TOOL_SPECS[name]
    cleaned: dict[str, str | int] = {}
    for param, rule in spec.params.items():
        if param not in arguments or arguments[param] is None or (
            isinstance(arguments[param], str) and not arguments[param].strip()
        ):
            if rule.get("required"):
                raise ToolArgsError(f"Parameter '{param}' wajib diisi.")
            continue
        value = arguments[param]
        param_type = rule["type"]
        if param_type == "int":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ToolArgsError(f"Parameter '{param}' wajib bilangan.")
            int_value = int(value)
            if int_value != value:
                raise ToolArgsError(f"Parameter '{param}' wajib bilangan bulat.")
            min_bound = rule.get("min")
            max_bound = rule.get("max") or (
                datetime.date.today().year if param == "tahun" else None
            )
            if min_bound is not None and int_value < min_bound:
                raise ToolArgsError(
                    f"Parameter '{param}' minimal {min_bound}."
                )
            if max_bound is not None and int_value > max_bound:
                raise ToolArgsError(
                    f"Parameter '{param}' maksimal {max_bound}."
                )
            cleaned[param] = int_value
        elif param_type == "str":
            if not isinstance(value, str):
                raise ToolArgsError(f"Parameter '{param}' wajib teks.")
            text = value.strip()
            maxlen = rule.get("maxlen")
            if maxlen and len(text) > maxlen:
                raise ToolArgsError(
                    f"Parameter '{param}' maksimal {maxlen} karakter."
                )
            cleaned[param] = text
        elif param_type == "date":
            if not isinstance(value, str):
                raise ToolArgsError("Parameter 'tanggal' wajib berformat YYYY-MM-DD.")
            text = value.strip()
            try:
                datetime.date.fromisoformat(text)
            except ValueError as exc:
                raise ToolArgsError(
                    "Parameter 'tanggal' wajib berformat YYYY-MM-DD."
                ) from exc
            cleaned[param] = text
    return cleaned


def clamp_observation(
    payload: typing.Any,
    max_chars: int | None = None,
) -> str:
    """
    Observasi untuk konteks model: JSON apa adanya, dipotong bila melewati
    TOOL_RESULT_MAX_CHARS (§ 5). Daftar dipangkas lebih dulu (item belakang
    terbuang); nilai angka / nama field tidak pernah diubah.
    """
    limit = max_chars or settings.tool_result_max_chars
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized) <= limit:
        return serialized

    # 1) potong daftar terbesar di peta teratas (respons daftar/logbook)
    if isinstance(payload, dict):
        list_keys = [k for k, v in payload.items() if isinstance(v, list)]
        trimmed = dict(payload)
        shrink_step = max(1, limit // 40)
        for key in sorted(list_keys, key=lambda k: len(json.dumps(payload.get(k), ensure_ascii=False)), reverse=True):
            while isinstance(trimmed.get(key), list) and trimmed[key]:
                # pangkas dahulu seluruh daftar bertingkat bila ada
                items = list(trimmed[key])
                reduced = max(0, len(items) - shrink_step)
                trimmed[key] = items[:reduced] if reduced > 0 else []
                candidate = json.dumps(trimmed, ensure_ascii=False)
                if len(candidate) <= limit - 30:
                    return candidate + " …[data dipotong]"
        # 2) terakhir: potong mentah string
        head = json.dumps(trimmed, ensure_ascii=False)[: limit - 16]
        return head + " …[data dipotong]"

    # payload non-dict (list/str) → potong mentah tingkat string
    return serialized[: limit - 16] + " …[data dipotong]"


def observation_message(
    name: str,
    call_id: str,
    status: str,
    observation: str | None,
    reason: str | None = None,
) -> dict[str, str]:
    """
    Susun pesan konteks hasil tool untuk re-invoke narasi (§ 8.3).
    Selalu berlabel eksplisit supaya model tidak mengira ini percakapan user.
    """
    if status == _STATUS_OK and observation:
        text = (
            f"[OBSERVASI ANALYTICS — {name} ({call_id}, status: ok)]\n"
            f"{observation}\n"
            "Gunakan angka tersebut dalam jawaban; sebut periode, definisi "
            "indikator, dan cakupan data sebagaimana tersedia pada observasi. "
            "Jika data tidak cukup, sampaikan batasannya."
        )
    else:
        detail = {
            "denied": f"Penggunaan tool ditolak: {reason or 'not_allowed'}.",
            "timeout": "Waktu tunggu tool terlampaui; data tidak tersedia.",
            "error": (
                f"Tool gagal dijalankan"
                f"{f' ({reason})' if reason else ''}; data tidak tersedia."
            ),
        }[status]
        text = (
            f"[OBSERVASI ANALYTICS — {name} ({call_id}, status: {status})]\n"
            f"{detail}\n"
            "Jelaskan singkat, tanpa mengarang angka, bahwa data itu tidak "
            "bisa ditampilkan sekarang."
        )
    return {"role": "user", "content": text}
