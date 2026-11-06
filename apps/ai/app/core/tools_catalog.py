"""
Katalog tool analytics Tahap 2 (spec tahap-2-analytics-tools.md § 3).

Semua tool memanggil endpoint agregat yang sudah ada di apps/analytics —
tidak dibuat tabel atau kueri SQL baru. Gateway hanya memvalidasi parameter
(§ 3.5) lalu meneruskan ke endpoint dengan identitas sesi pengguna (§ 6).
"""
from __future__ import annotations

import datetime
import typing


# Skema parameter per tool: type, batas angka, panjang maksimum, optional.
# Angka batas (§ 3.5): tahun 2015–sekarang, limit 1–20 (clamp dari 1–100),
# string ≤ 100 karakter.
PARAM_RULES = {
    "type": ("int", "str", "date"),
}


class ToolSpec(typing.NamedTuple):
    name: str
    method: str
    path: str
    description: str
    params: dict[str, dict[str, typing.Any]]
    notes: str = ""


TOOL_SPECS: dict[str, ToolSpec] = {
    "get_ringkasan_stats": ToolSpec(
        name="get_ringkasan_stats",
        method="GET",
        path="/datamart/ringkasan/stats",
        params={
            "tahun": {"type": "int", "min": 2015, "max": None, "maxlen": None, "required": False},
            "organisasi": {"type": "str", "maxlen": 100, "required": False},
            "fokus_riset": {"type": "str", "maxlen": 100, "required": False},
            "q": {"type": "str", "maxlen": 100, "required": False},
        },
        description=(
            "KPI ringkasan riset platform: total_periset, total_kegiatan, "
            "kegiatan_aktif, total_keluaran, keluaran_published, pct_published, "
            "logbook_hari_ini. Parameter: tahun (2015–sekarang), organisasi "
            "(filter hanya berlaku untuk role global; kepala_or/kepala_pr "
            "otomatis ter-scope), fokus_riset, q (kata kunci judul)."
        ),
    ),
    "get_keluaran_stats": ToolSpec(
        name="get_keluaran_stats",
        method="GET",
        path="/datamart/keluaran/stats",
        params={
            "tahun": {"type": "str", "maxlen": 100, "required": False},
            "kategori_keluaran": {"type": "str", "maxlen": 100, "required": False},
            "fokus_clustering": {"type": "str", "maxlen": 100, "required": False},
        },
        notes=(
            "Cakupan data keluaran global — tabel belum memiliki kolom satker; "
            "sebut cakupan 'global' dalam jawaban."
        ),
        description=(
            "KPI keluaran riset: total_keluaran, total_ki, total_publikasi, "
            "total_granted. Parameter: tahun (contoh '2026'), kategori_keluaran, "
            "fokus_clustering."
        ),
    ),
    "get_outcome_stats": ToolSpec(
        name="get_outcome_stats",
        method="GET",
        path="/datamart/outcome/stats",
        params={
            "tahun_lisensi": {"type": "str", "maxlen": 100, "required": False},
            "status_lisensi": {"type": "str", "maxlen": 100, "required": False},
        },
        description=(
            "KPI outcome hilirisasi: total_outcome, lisensi_aktif, total_pnbp, "
            "jumlah_mitra. Parameter: tahun_lisensi (contoh '2024'), "
            "status_lisensi."
        ),
    ),
    "get_logbook_harian": ToolSpec(
        name="get_logbook_harian",
        method="GET",
        path="/datamart/laporan-harian/logbook",
        params={
            "tanggal": {"type": "date", "maxlen": 10, "required": True},
            "limit": {"type": "int", "min": 1, "max": 20, "maxlen": None, "required": False},
            "offset": {"type": "int", "min": 0, "max": None, "maxlen": None, "required": False},
        },
        notes=(
            "'tanggal' wajib format YYYY-MM-DD; limit tool maksimal 20 agar "
            "konteks model ringkas."
        ),
        description=(
            "Daftar logbook aktivitas periset per tanggal, berhalaman. "
            "Parameter: tanggal (wajib, YYYY-MM-DD), limit (1–20), offset (≥ 0)."
        ),
    ),
}


def parse_allowed_tools(ai_tools_csv: str) -> tuple[str, ...]:
    """Parse allowlist env AI_TOOLS. Kosong = tools mati (deny-by-default)."""
    if not ai_tools_csv or not ai_tools_csv.strip():
        return ()
    allowed: list[str] = []
    for raw in ai_tools_csv.split(","):
        name = raw.strip()
        if name and name in TOOL_SPECS and name not in allowed:
            allowed.append(name)
    return tuple(allowed)


def catalog_directive(allowed: typing.Sequence[str]) -> str:
    """
    System-prompt tambahan saat tools aktif: kontrak marker JSON resmi
    (model-agnostic), daftar tool, dan larangan mengarang angka.
    """
    if not allowed:
        return ""
    tool_lines: list[str] = []
    for name in allowed:
        spec = TOOL_SPECS[name]
        params = ", ".join(
            f"{param_name}:{_param_label(rule)}"
            for param_name, rule in spec.params.items()
        )
        line = f"- {spec.name} — {spec.description} Param: {params or 'tanpa parameter'}."
        if spec.notes:
            line += f" Catatan: {spec.notes}"
        tool_lines.append(line)

    year_max = datetime.date.today().year
    return (
        "\n\nALAT DATA ANALYTICS (aktif):\n"
        "Bila (dan hanya bila) jawaban Anda membutuhkan angka platform yang "
        "belum ada di percakapan, balas HANYA dengan satu objek JSON resmi "
        "tanpa kalimat lain dan tanpa tanda baca tambahan:\n"
        '{"tool": "<nama_tool>", "arguments": {...}}\n'
        "Tool yang tersedia (gunakan nama persis, semua endpoint agregat "
        "platform):\n" + "\n".join(tool_lines) + "\n"
        f"Aturan: gunakan argumen minimal yang diperlukan; tahun berlaku "
        f"{2015}–{year_max}; tanggal format YYYY-MM-DD; jangan pernah "
        "mengarang angka, nama, atau ketentuan; angka akan tersedia melalui "
        "observasi hasil tool yang dikirim sistem. Setelah observasi tiba, "
        "jawab langsung berbasis data itu (sebut periode, definisi indikator, "
        "dan cakupan) tanpa mengirim JSON baru — hanya satu putaran. Bila "
        "pertanyaan tidak membutuhkan data platform, jawab narasi biasa tanpa JSON."
    )


def _param_label(rule: dict[str, typing.Any]) -> str:
    param_type = rule["type"]
    label = {"int": "int", "str": "str", "date": "date YYYY-MM-DD"}[param_type]
    if param_type == "int":
        bounds = []
        if rule.get("min") is not None:
            bounds.append(str(rule["min"]))
        else:
            bounds.append("≥0")
        if rule.get("max") is not None:
            bounds.append(str(rule["max"]))
        else:
            bounds.append("∞")
        label = f"int {bounds[0]}–{bounds[1]}"
    elif param_type == "str" and rule.get("maxlen"):
        label = f"str ≤{rule['maxlen']}"
    if rule.get("required"):
        label += ", wajib"
    else:
        label += ", opsional"
    return label
