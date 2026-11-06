"""
Analytics client — panggilan endpoint agregat apps/analytics dari gateway.

Identitas pengguna diteruskan apa adanya melalui header Cookie (hasil
passthrough X-Rcc-Cookie dari BFF); gateway tidak pernah membangun
identitas sendiri dan tidak pernah menyimpan / menebak isi cookie.

Tidak ada akses DB dari gateway — hanya katalog endpoint § 3.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import typing
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings

settings = get_settings()

_client: httpx.AsyncClient | None = None


class AnalyticsConfigError(Exception):
    """Konfigurasi ANALYTICS_URL tidak sah — gateway gagal cepat saat boot."""


class AnalyticsEndpointError(Exception):
    """Perilaku yang menyerupai gagal (network / HTTP >= 400 / JSON rusak)."""


def validate_analytics_url(raw_url: str) -> str:
    """
    Validasi ANALYTICS_URL (dijalankan saat boot bila tools aktif).

    Syarat: scheme http/https, host internal — IP literal harus private/
    loopback; hostname harus me-resolve ke alamat private/loopback.
    Salah konfigurasi → AnalyticsConfigError → gateway gagal cepat saat boot.
    """
    if not raw_url or not raw_url.strip():
        raise AnalyticsConfigError("ANALYTICS_URL wajib diisi saat AI_TOOLS aktif.")
    parsed = urlsplit(raw_url.strip())
    if parsed.scheme not in ("http", "https"):
        raise AnalyticsConfigError(
            f"ANALYTICS_URL scheme tidak sah ({parsed.scheme!r}); gunakan http."
        )
    host = parsed.hostname
    if not host:
        raise AnalyticsConfigError("ANALYTICS_URL tanpa host.")

    if _looks_local_name(host):
        return raw_url.strip()

    try:
        resolved = ipaddress.ip_address(host)
    except ValueError:
        resolved = None

    if resolved is not None:
        if resolved.is_private or resolved.is_loopback:
            return raw_url.strip()
        raise AnalyticsConfigError(
            f"ANALYTICS_URL host {host} bukan alamat internal."
        )

    try:
        infos = socket.getaddrinfo(host, parsed.port or None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise AnalyticsConfigError(
            f"ANALYTICS_URL host {host} tidak dapat di-resolve: {exc}"
        ) from exc
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not (addr.is_private or addr.is_loopback):
            raise AnalyticsConfigError(
                f"ANALYTICS_URL host {host} resolve ke alamat non-internal {addr}."
            )
    return raw_url.strip()


def _looks_local_name(host: str) -> bool:
    lowered = host.lower()
    return (
        lowered == "localhost"
        or lowered.endswith(".localhost")
        or lowered.endswith(".local")
        or lowered.endswith(".internal")
        or lowered.endswith(".svc")
    )


def get_client() -> httpx.AsyncClient:
    """Single shared AsyncClient menuju analytics (satu event loop FastAPI)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.analytics_url,
            timeout=httpx.Timeout(settings.tool_timeout, connect=5.0),
        )
    return _client


async def close_client() -> None:
    """Tutup client saat aplikasi berhenti."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


class EndpointResult(typing.NamedTuple):
    """Hasil satu panggilan endpoint analytics."""

    status_code: int | None
    data: dict | None          # sudah JSON-parsed bila status_code == 200
    error: str | None          # alasan singkat tanpa isi raw / tanpa cookie


async def call_endpoint(
    method: str,
    path: str,
    params: dict[str, str | int],
    cookie: str | None,
    timeout: float | None = None,
) -> EndpointResult:
    """
    Panggil endpoint analytics (GET) membawa cookie sesi pengguna.

    Timeout per tool dijaga httpx; kegagalan jaringan/HTTP >= 400/JSON rusak
    dilempar sebagai error singkat, bukan exception besar.
    """
    headers = {"Cookie": cookie} if cookie else {}
    try:
        client = get_client()
        response = await client.request(
            method,
            path,
            params=params,
            headers=headers,
            timeout=timeout or settings.tool_timeout,
        )
    except httpx.TimeoutException:
        return EndpointResult(status_code=None, data=None, error="analytics_timeout")
    except httpx.HTTPError as exc:
        return EndpointResult(status_code=None, data=None, error=f"analytics_unreachable: {exc.__class__.__name__} {exc}")

    if response.status_code != 200:
        return EndpointResult(
            status_code=response.status_code,
            data=None,
            error=f"analytics_http_{response.status_code}",
        )
    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError):
        return EndpointResult(
            status_code=200,
            data=None,
            error="analytics_invalid_json",
        )
    if not isinstance(data, dict):
        return EndpointResult(
            status_code=200,
            data=None,
            error="analytics_unexpected_payload",
        )
    return EndpointResult(status_code=200, data=data, error=None)
