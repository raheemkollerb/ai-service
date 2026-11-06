"""
Mock analytics RCC (:12001) — tes acceptance gateway tools Tahap 2.

Server FastAPI minimal yang meniru endpoint agregat apps/analytics § 3
spec tahap-2-analytics-tools.md dengan respons fixture. Tanpa auth dan
tanpa DB — hanya alat uji jaringan internal.

Env opsional:
  MOCK_ANALYTICS_HANG=1   → endpoint tidur 60 detik (uji T12 timeout)
Port diambil dari MOCK_ANALYTICS_PORT (default 12001).

/debug/last-request → catatan request terakhir (method, path, query,
cookie) untuk memverifikasi passthrough cookie dan "tanpa request ke
analytics" pada skenario deny.
"""
import asyncio
import logging
import os

from fastapi import FastAPI, Request

logging.getLogger("uvicorn").setLevel(logging.ERROR)
logging.getLogger("uvicorn.access").setLevel(logging.ERROR)

app = FastAPI(title="Mock Analytics - RCC tests")

_last_request: dict[str, object] = {"seen": False}


def _mark(request: Request) -> None:
    global _last_request
    _last_request = {
        "seen": True,
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params.multi_items()),
        "cookie": request.headers.get("cookie"),
    }


async def _maybe_hang() -> None:
    if os.environ.get("MOCK_ANALYTICS_HANG") == "1":
        await asyncio.sleep(60)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/debug/last-request")
async def last_request() -> dict:
    return dict(_last_request)


@app.get("/debug/reset")
async def debug_reset() -> dict:
    global _last_request
    _last_request = {"seen": False}
    return {"reset": True}


@app.get("/datamart/ringkasan/stats")
async def ringkasan_stats(request: Request) -> dict:
    _mark(request)
    await _maybe_hang()
    return {
        "total_periset": 4321,
        "total_kegiatan": 987,
        "kegiatan_aktif": 512,
        "total_keluaran": 2345,
        "keluaran_published": 1122,
        "pct_published": 47.87,
        "logbook_hari_ini": 23,
    }


@app.get("/datamart/keluaran/stats")
async def keluaran_stats(request: Request) -> dict:
    _mark(request)
    await _maybe_hang()
    return {
        "total_keluaran": 2345,
        "total_ki": 789,
        "total_publikasi": 1234,
        "total_granted": 322,
    }


@app.get("/datamart/outcome/stats")
async def outcome_stats(request: Request) -> dict:
    _mark(request)
    await _maybe_hang()
    return {
        "total_outcome": 456,
        "lisensi_aktif": 210,
        "total_pnbp": 12345678.9,
        "jumlah_mitra": 87,
    }


def _logbook_items(limit: int) -> list[dict]:
    """Fixture logbook deterministik; count limit dikirim gateway (tool ≤ 20)."""
    items = []
    for index in range(limit):
        items.append(
            {
                "id_logbook": 1000 + index,
                "nip": f"1995010120240{index:03d}",
                "nama": f"Periset Fiksi #{index + 1}",
                "tanggal": "2026-11-05",
                "jam_mulai": "08:00",
                "jam_selesai": "12:30",
                "jenis_kegiatan": "Riset (Full Time Equivalent)",
                "kategori_kegiatan": "Penelitian",
                "subkategori_kegiatan": "Kajian Data Lama",
                "judul_kegiatan": (
                    "Penelitian fiksi nomor {index} mengenai pangan "
                    "dan biokonversi dalam kerangka proyek internal BRIN "
                    "untuk memenuhi kebutuhan uji payload besar gateway tools"
                ).format(index=index),
                "uraian": (
                    "Uraian kegiatan fiksi: pengolahan data percobaan, "
                    "verifikasi bukti kesaamaan, dan penyusunan draf logbook; "
                    "dipakai untuk uji standar panjang konteks model."
                ),
                "kendala": "Tidak ada",
                "kode_proposal_riset": f"PR-2026-{index:04d}",
                "unit_kerja_realisasi_es2": "Pusat Riset Fiksi",
                "unit_kerja_realisasi_es1": "OR Fiksi",
                "jabatan": "Peneliti",
                "jenjang_jf": "Ahli Madya",
                "nama_satker_eselon_2": "Pusat Riset Fiksi",
            }
        )
    return items


@app.get("/datamart/laporan-harian/logbook")
async def logbook_harian(request: Request, limit: int = 10, offset: int = 0) -> dict:
    _mark(request)
    await _maybe_hang()
    items = _logbook_items(limit)
    return {
        "tanggal": "2026-11-05",
        "items": items,
        "pagination": {
            "total": limit + offset,
            "limit": limit,
            "offset": offset,
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("MOCK_ANALYTICS_PORT", "12001"))
    uvicorn.run(
        "mock_analytics:app",
        host="127.0.0.1",
        port=port,
        log_level="error",
    )
