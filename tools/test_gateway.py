import json
import os
import subprocess
import sys
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AI_DIR = os.path.join(ROOT, "apps", "ai")
# Override path kode gateway saat uji berputar pada checkout lain
# (mis. monorepo platform sebelum mirror):
RCC_AI_DIR = os.environ.get("RCC_AI_DIR", AI_DIR)
PYTHON = sys.executable
SERVICE_KEY = "dev-test"
SABOTAGE = "SABOTASE-MARKER-jangan-leak"
TEST_COOKIE = "rcc_session=eval-test-cookie"

MOCK_LLM_PORT = 11999
MOCK_ANALYTICS_PORT = 12001

results: list[tuple[str, str, str]] = []


def record(test_id: str, ok: bool, note: str) -> None:
    results.append((test_id, "PASS" if ok else "FAIL", note))


def wait_ready(url: str, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.4)
    return False


def spawn_mock() -> subprocess.Popen:
    return subprocess.Popen(
        [PYTHON, os.path.join(HERE, "mock_llm.py")],
        cwd=HERE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def spawn_mock_llm_script(port: int, tool_json: str, narration: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["MOCK_LLM_TOOL"] = tool_json
    env["MOCK_LLM_NARRATION"] = narration
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "mock_llm:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=HERE,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    return proc


def spawn_mock_analytics(port: int, hang: bool = False) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("MOCK_ANALYTICS_PORT", str(port))
    env["MOCK_ANALYTICS_PORT"] = str(port)
    if hang:
        env["MOCK_ANALYTICS_HANG"] = "1"
    else:
        env.pop("MOCK_ANALYTICS_HANG", None)
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "mock_analytics:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=HERE,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def spawn_gateway(port: int, base_url: str, extra_env: dict | None = None) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(
        {
            "SERVICE_KEY": SERVICE_KEY,
            "LLM_BASE_URL": base_url,
            "HOST": "127.0.0.1",
            "PORT": str(port),
            "ENVIRONMENT": "development",
            "LLM_TIMEOUT": "20",
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=RCC_AI_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def read_sse(response: httpx.Response) -> list[dict]:
    frames: list[dict] = []
    for line in response.iter_lines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        try:
            frames.append(json.loads(payload))
        except ValueError:
            frames.append({"raw": payload})
    return frames


def chat_frames(url: str, headers: dict, messages: list[dict], timeout: float = 20.0):
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        with client.stream(
            "POST",
            f"{url}/ai/chat",
            headers=headers,
            json={"messages": messages},
        ) as response:
            status = response.status_code
            media = response.headers.get("content-type", "")
            frames = read_sse(response)
    return status, media, frames


def run_tests() -> None:
    if not wait_ready("http://127.0.0.1:11999/v1/models"):
        raise RuntimeError("mock LLM tidak siap pada :11999")

    live = spawn_gateway(8101, "http://127.0.0.1:11999/v1")
    dead = spawn_gateway(8102, "http://127.0.0.1:11998/v1")
    try:
        if not wait_ready("http://127.0.0.1:8101/health"):
            raise RuntimeError("gateway live (:8101) tidak siap")
        if not wait_ready("http://127.0.0.1:8102/health"):
            raise RuntimeError("gateway dead-upstream (:8102) tidak siap")
    except RuntimeError as exc:
        for proc in (live, dead):
            if proc.poll() is None:
                proc.terminate()
        raise

    try:
        wrong = httpx.post(
            "http://127.0.0.1:8101/ai/chat",
            headers={"X-Service-Key": "kunci-salah"},
            json={"messages": [{"role": "user", "content": "halo"}]},
            timeout=10.0,
        )
        missing = httpx.post(
            "http://127.0.0.1:8101/ai/chat",
            json={"messages": [{"role": "user", "content": "halo"}]},
            timeout=10.0,
        )
        record(
            "T1",
            wrong.status_code == 403 and missing.status_code == 403,
            f"kunci salah={wrong.status_code}, tanpa kunci={missing.status_code} (harap 403/403)",
        )

        status, _, frames = chat_frames("http://127.0.0.1:8101", {"X-Service-Key": SERVICE_KEY}, [])
        probe_detail = ""
        if status == 400:
            probe = httpx.post(
                "http://127.0.0.1:8101/ai/chat",
                headers={"X-Service-Key": SERVICE_KEY},
                json={"messages": []},
                timeout=10.0,
            )
            probe_detail = probe.json().get("detail", "")
        record("T2", status == 400 and bool(probe_detail), f"status={status} detail={probe_detail!r}")

        status, _, frames = chat_frames(
            "http://127.0.0.1:8101",
            {"X-Service-Key": SERVICE_KEY},
            [
                {"role": "system", "content": SABOTAGE},
                {"role": "user", "content": "sapa saya"},
            ],
        )
        text = "".join(frame.get("text", "") for frame in frames if frame.get("type") == "delta")
        leaked = httpx.get("http://127.0.0.1:11999/debug/last-request", timeout=5.0).json()
        serialized = json.dumps(leaked)
        system_count = sum(1 for m in leaked.get("messages", []) if m.get("role") == "system")
        record(
            "T3",
            status == 200
            and text == "Halo dari mock LLM."
            and SABOTAGE not in serialized
            and system_count == 1,
            f"status={status} delta={text!r} system_tersisa={system_count} leak={SABOTAGE in serialized}",
        )

        flood = [{"role": "user", "content": f"pesan polos ke-{i}"} for i in range(21)]
        status, _, _ = chat_frames("http://127.0.0.1:8101", {"X-Service-Key": SERVICE_KEY}, flood)
        record("T4", status == 400, f"status={status} (harap 400, maks 20 pesan)")

        multi = [
            {"role": "user", "content": "pertanyaan satu"},
            {"role": "assistant", "content": "jawaban satu"},
            {"role": "user", "content": "pertanyaan dua"},
            {"role": "assistant", "content": "jawaban dua"},
            {"role": "user", "content": "pertanyaan tiga"},
        ]
        status, media, frames = chat_frames(
            "http://127.0.0.1:8101", {"X-Service-Key": SERVICE_KEY}, multi
        )
        types = [frame.get("type") for frame in frames]
        done = next((frame for frame in frames if frame.get("type") == "done"), None)
        ok_sse = "text/event-stream" in media and "delta" in types and done is not None
        ok_done = (
            done is not None
            and done.get("finish_reason") == "stop"
            and isinstance(done.get("usage"), dict)
        )
        record("T5", status == 200 and ok_sse and ok_done, f"status={status} media={media} types={types} done={done}")

        status, _, frames = chat_frames(
            "http://127.0.0.1:8102", {"X-Service-Key": SERVICE_KEY}, [{"role": "user", "content": "halo"}]
        )
        had_error = any(frame.get("type") == "error" for frame in frames)
        last_type = frames[-1].get("type") if frames else None
        record(
            "T6",
            status < 500 and had_error and last_type == "error",
            f"status={status} last_frame_type={last_type} (error event + tanpa 5xx)",
        )

        health = httpx.get("http://127.0.0.1:8102/health", timeout=10.0)
        body = health.json() if health.status_code == 200 else {}
        record(
            "T7",
            health.status_code == 200 and body.get("status") == "healthy",
            f"status={health.status_code} body={body if body else None} (porting platform: status='healthy')",
        )

        upstream = httpx.get(
            "http://127.0.0.1:8101/ai/health/upstream",
            headers={"X-Service-Key": SERVICE_KEY},
            timeout=10.0,
        ).json()
        record(
            "T8",
            upstream.get("available") is True and "qwen3:30b-a3b" in (upstream.get("models") or []),
            f"available={upstream.get('available')} models={upstream.get('models')}",
        )
    finally:
        for proc in (live, dead):
            if proc.poll() is None:
                proc.terminate()


def _spawn_tool_gateways(spawns: list[tuple[str, int, str, dict]]) -> dict[str, subprocess.Popen]:
    """Spesifikasi (nama, port, base_url, env ekstra); me-raise bila gagal siap."""
    procs: dict[str, subprocess.Popen] = {}
    try:
        for name, port, base_url, extra_env in spawns:
            procs[name] = spawn_gateway(port, base_url, extra_env)
            if not wait_ready(f"http://127.0.0.1:{port}/health"):
                raise RuntimeError(f"gateway {name} (:{port}) tidak siap")
    except RuntimeError:
        for proc in procs.values():
            if proc.poll() is None:
                proc.terminate()
        raise
    return procs


def run_tool_tests(
    mock_llm_script_t9: subprocess.Popen,
    mock_llm_script_t10: subprocess.Popen,
    mock_llm_script_t13: subprocess.Popen,
) -> None:
    base_tools_env = {
        "ANALYTICS_URL": f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}",
        "AI_TOOLS": (
            "get_ringkasan_stats,get_keluaran_stats,get_outcome_stats,get_logbook_harian"
        ),
    }
    spawns = [
        ("t9", 8103, "http://127.0.0.1:11997/v1", base_tools_env),
        ("t10", 8105, "http://127.0.0.1:11995/v1", {
            "ANALYTICS_URL": f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}",
            "AI_TOOLS": "get_ringkasan_stats",
        }),
        ("t11", 8107, "http://127.0.0.1:11999/v1", {
            "ANALYTICS_URL": f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}",
            "AI_TOOLS": "",
        }),
        ("t12", 8104, "http://127.0.0.1:11997/v1", {
            "ANALYTICS_URL": "http://127.0.0.1:12002",
            "AI_TOOLS": "get_ringkasan_stats",
            "TOOL_TIMEOUT": "0.9",
        }),
        ("t13", 8106, "http://127.0.0.1:11996/v1", base_tools_env),
    ]
    procs = {}
    try:
        procs = _spawn_tool_gateways(spawns)
        white = {"X-Service-Key": SERVICE_KEY}

        httpx.get(f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}/debug/reset", timeout=5.0)

        # ── T9: prompt data → tool_call → tool_result ok → delta → done ──────
        status, media, frames = chat_frames(
            "http://127.0.0.1:8103",
            {**white, "X-Rcc-Cookie": TEST_COOKIE},
            [{"role": "user", "content": "berapa statistik riset tahun 2026?"}],
        )
        types = [frame.get("type") for frame in frames]
        order_ok = (
            "tool_call" in types
            and "tool_result" in types
            and types.index("tool_call") < types.index("tool_result") < len(frames) - 1
        )
        call = next((f for f in frames if f.get("type") == "tool_call"), None)
        result = next((f for f in frames if f.get("type") == "tool_result"), None)
        done = next((f for f in frames if f.get("type") == "done"), None)
        last_analytics = httpx.get(
            f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}/debug/last-request", timeout=5.0
        ).json()
        narrated = "".join(
            frame.get("text", "") for frame in frames if frame.get("type") == "delta"
        )
        record(
            "T9",
            status == 200
            and "text/event-stream" in media
            and order_ok
            and result is not None
            and result.get("status") == "ok"
            and call is not None
            and call.get("name") == "get_ringkasan_stats"
            and call.get("arguments") == {"tahun": 2026}
            and result.get("call_id") == (call or {}).get("call_id")
            and isinstance(result.get("elapsed_ms"), int)
            and done is not None
            and done.get("finish_reason") == "stop"
            and narrated == "Berdasarkan data analytics platform, tahun 2026 tercatat 4321 periset aktif dan 512 kegiatan didanai."
            and last_analytics.get("cookie") == TEST_COOKIE
            and last_analytics.get("path") == "/datamart/ringkasan/stats"
            and str(last_analytics.get("query", {}).get("tahun")) == "2026",
            f"status={status} types={types} result={result} last={last_analytics} narrated={narrated[:80]!r}",
        )

        # ── T10: tool di luar allowlist → denied tanpa request analytics ─────
        httpx.get(f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}/debug/reset", timeout=5.0)
        status, _, frames = chat_frames(
            "http://127.0.0.1:8105",
            white,
            [{"role": "user", "content": "statistik keluaran dong"}],
        )
        types = [frame.get("type") for frame in frames]
        result = next((f for f in frames if f.get("type") == "tool_result"), None)
        last_analytics = httpx.get(
            f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}/debug/last-request", timeout=5.0
        ).json()
        narrated = "".join(
            frame.get("text", "") for frame in frames if frame.get("type") == "delta"
        )
        record(
            "T10",
            status == 200
            and result is not None
            and result.get("status") == "denied"
            and result.get("reason") == "not_allowed"
            and order_pairs_ok(frames)
            and narrated == "statistik keluaran global: 2345 keluaran (mock)."
            and last_analytics.get("seen") is False,
            f"status={status} types={types} result={result} narrated={narrated[:80]!r} last={last_analytics}",
        )

        # ── T11: AI_TOOLS kosong → identik Tahap 1, tanpa tool_call ──────────
        status, _, frames = chat_frames(
            "http://127.0.0.1:8107",
            white,
            [{"role": "user", "content": "sapa saya"}],
        )
        types = [frame.get("type") for frame in frames]
        done = next((f for f in frames if f.get("type") == "done"), None)
        record(
            "T11",
            status == 200
            and "tool_call" not in types
            and "tool_result" not in types
            and "delta" in types
            and done is not None,
            f"status={status} types={types}",
        )

        # ── T12: analytics melempenebihi TOOL_TIMEOUT → timeout, stream lanjut
        started = time.perf_counter()
        status, _, frames = chat_frames(
            "http://127.0.0.1:8104",
            white,
            [{"role": "user", "content": "statistik ringkasan dulu"}],
        )
        elapsed = time.perf_counter() - started
        types = [frame.get("type") for frame in frames]
        result = next((f for f in frames if f.get("type") == "tool_result"), None)
        record(
            "T12",
            status == 200
            and result is not None
            and result.get("status") == "timeout"
            and order_pairs_ok(frames)
            and elapsed < 10,
            f"status={status} types={types} result={result} durasi={elapsed:.1f}s (<10s, mock hang 60s)",
        )

        # ── T13: respons besar → observasi ke model ter-clamp ────────────────
        status, _, frames = chat_frames(
            "http://127.0.0.1:8106",
            white,
            [{"role": "user", "content": "logbook hari ini, mohon datanya"}],
        )
        types = [frame.get("type") for frame in frames]
        result = next((f for f in frames if f.get("type") == "tool_result"), None)
        llm_last = httpx.get("http://127.0.0.1:11996/debug/last-request", timeout=5.0).json()
        observation = ""
        for message in (llm_last.get("messages") or []):
            content = message.get("content") or ""
            if "[OBSERVASI ANALYTICS" in content:
                observation = content.split("\n", 1)[1].split("\n[")[0]
        n_items = (observation or "").count('"id_logbook"')
        record(
            "T13",
            status == 200
            and result is not None
            and result.get("status") == "ok"
            and order_pairs_ok(frames)
            and 0 < len(observation)
            and len(observation) <= 4000 + 40
            and "data dipotong" in observation
            and n_items < 20,
            f"status={status} result={result} panjang_observasi={len(observation)} item_sisa={n_items}",
        )
    finally:
        for proc in procs.values():
            if proc.poll() is None:
                proc.terminate()


def order_pairs_ok(frames: list[dict]) -> bool:
    """Setiap tool_call wajib berpasangan tool_result dengan call_id sama,
    urutan call sebelum result."""
    last_call: dict | None = None
    for frame in frames:
        if frame.get("type") == "tool_call":
            last_call = frame
        elif frame.get("type") == "tool_result":
            if last_call is None or last_call.get("call_id") != frame.get("call_id"):
                return False
            last_call = None
    return last_call is None


def main() -> int:
    mock = spawn_mock()
    mock_llm_t9 = spawn_mock_llm_script(
        11997,
        '{"tool": "get_ringkasan_stats", "arguments": {"tahun": 2026}}',
        "Berdasarkan data analytics platform, tahun 2026 tercatat 4321 periset "
        "aktif dan 512 kegiatan didanai.",
    )
    mock_llm_t10 = spawn_mock_llm_script(
        11995,
        '{"tool": "get_keluaran_stats", "arguments": {}}',
        "statistik keluaran global: 2345 keluaran (mock).",
    )
    mock_llm_t13 = spawn_mock_llm_script(
        11996,
        '{"tool": "get_logbook_harian", "arguments": {"tanggal": "2026-11-05", "limit": 20}}',
        "Logbook sukses diproses (mock).",
    )
    mock_analytics_default = spawn_mock_analytics(MOCK_ANALYTICS_PORT)
    mock_analytics_hang = spawn_mock_analytics(12002, hang=True)
    procs = (mock, mock_llm_t9, mock_llm_t10, mock_llm_t13, mock_analytics_default, mock_analytics_hang)
    try:
        if not wait_ready(f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}/health"):
            raise RuntimeError("mock analytics tidak siap")
        if not wait_ready("http://127.0.0.1:12002/health"):
            raise RuntimeError("mock analytics hang (:12002) tidak siap")
        if not wait_ready("http://127.0.0.1:11997/v1/models"):
            raise RuntimeError("mock LLM skripted (:11997) tidak siap")
        if not wait_ready("http://127.0.0.1:11995/v1/models"):
            raise RuntimeError("mock LLM skripted (:11995) tidak siap")
        if not wait_ready("http://127.0.0.1:11996/v1/models"):
            raise RuntimeError("mock LLM skripted (:11996) tidak siap")
        run_tests()
        run_tool_tests(mock_llm_t9, mock_llm_t10, mock_llm_t13)
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
    header = "Acceptance T1-T13 (mock LLM/analytics; altern-Alur: :11999 base + :11997/:11995/:11996 skripted)"
    print(header)
    print("-" * len(header))
    for test_id, verdict, note in results:
        print(f"{test_id}  {verdict:<4} | {note}")
    failed = [t for t, v, _ in results if v == "FAIL"]
    if failed:
        print(f"TES GAGAL: {','.join(failed)}")
    else:
        print("SEMUA 13 TES PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
