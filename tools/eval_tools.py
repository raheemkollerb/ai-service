"""
Eval qwen3:30b-a3b untuk R3 (spec tahap-2-analytics-tools.md § 7).

Mengukur tiga criteria (dijalankan DI HPC bersama Ollama asli + mock
analytics fikstur, bukan analytics live platform):

  (a) presisi intent tool-call — tool & parameter tepat;
  (b) restraint — pertanyaan non-data TIDAK memanggil tool;
  (c) kualitas narasi — angka yang termuat berasal dari observasi tool
      (auto-proxy: angka fikstur muncul di jawaban) + teks lengkap
      ditampilkan untuk review manual (periode/definisi/sumber).

Cara pakai di HPC (repo ai-service):
  python tools/eval_tools.py                 # seluruh kasus
  python tools/eval_tools.py --case 1,4      # subset (nomor 1-based)

Ollama di HPC: LLM_BASE_URL default http://127.0.0.1:11434/v1.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AI_DIR = os.path.join(ROOT, "apps", "ai")
PYTHON = sys.executable
SERVICE_KEY = "dev-test"
GATEWAY_PORT = 8120
MOCK_ANALYTICS_PORT = 12001

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, note: str) -> None:
    results.append((name, "PASS" if ok else "FAIL", note))


def wait_ready(url: str, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2.0).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.4)
    return False


def spawn_mock_analytics(port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["MOCK_ANALYTICS_PORT"] = str(port)
    env.pop("MOCK_ANALYTICS_HANG", None)
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "mock_analytics:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=HERE,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def spawn_gateway() -> subprocess.Popen:
    env = os.environ.copy()
    env.update(
        {
            "SERVICE_KEY": SERVICE_KEY,
            "LLM_BASE_URL": os.environ.get("LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
            "HOST": "127.0.0.1",
            "PORT": str(GATEWAY_PORT),
            "ENVIRONMENT": "development",
            "ANALYTICS_URL": f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}",
            "AI_TOOLS": (
                "get_ringkasan_stats,get_keluaran_stats,get_outcome_stats,get_logbook_harian"
            ),
        }
    )
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(GATEWAY_PORT)],
        cwd=AI_DIR,
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


def run_case(case: dict) -> None:
    name = case["name"]
    calls = [f for f in case["frames"] if f.get("type") == "tool_call"]
    call_results = [f for f in case["frames"] if f.get("type") == "tool_result"]
    deltas = [f.get("text", "") for f in case["frames"] if f.get("type") == "delta"]
    final_text = "".join(deltas)

    if case.get("expect_tool") is None:
        # restraint: tanpa tool sama sekali
        ok = not calls
        note = "restasi: " + ("tanpa tool_call" if ok else f"tool terpanggil: {[c.get('name') for c in calls]}")
        record(name, ok, note)
        return

    tool_ok = bool(calls) and calls[0].get("name") == case["expect_tool"]
    args = (calls[0] or {}).get("arguments", {}) if calls else {}
    args_ok = all(args.get(k) == v for k, v in case.get("expect_args", {}).items())
    ok_ranges = all(
        (
            key != "limit"
            or (isinstance(value, int) and 1 <= value <= 20)
        )
        for key, value in args.items()
    )
    result_ok = (
        not call_results
        or all(r.get("status") in ("ok", "timeout") for r in call_results)
    ) and any(r.get("status") == "ok" for r in call_results)
    numbers_hit = not case.get("expect_number") or str(case["expect_number"]) in final_text
    ok = tool_ok and args_ok and ok_ranges and result_ok and numbers_hit
    notes = []
    if not tool_ok:
        notes.append(f"tool: {calls[0].get('name') if calls else 'TIDAK ADA'} ≠ {case['expect_tool']}")
    if not args_ok:
        notes.append(f"args: {args} ≠ {case.get('expect_args')}")
    if not ok_ranges:
        notes.append(f"range args tidak sah: {args}")
    if not result_ok:
        notes.append(f"tool_result: {[r.get('status') for r in call_results]}")
    if not numbers_hit:
        notes.append(f"angka {case.get('expect_number')} tidak ada dalam narasi")
    record(name, ok, "; ".join(notes) or "intent+args+angka fitur")

    # Laporan narasi lengkap untuk review manual (kriteria c)
    print(f"    jawaban[{name}]: {final_text.strip()[:600]}")


EVAL_CASES: list[dict] = [
    {
        "name": "E1",
        "prompt": "Berapa total periset aktif di platform tahun 2026?",
        "expect_tool": "get_ringkasan_stats",
        "expect_args": {"tahun": 2026},
        "expect_number": "4321",
        "frames": [],
    },
    {
        "name": "E2",
        "prompt": "Berapa jumlah keluaran riset yang sudah granted?",
        "expect_tool": "get_keluaran_stats",
        "expect_args": {},
        "expect_number": "322",
        "frames": [],
    },
    {
        "name": "E3",
        "prompt": "Berapa lisensi hilirisasi yang aktif?",
        "expect_tool": "get_outcome_stats",
        "expect_args": {},
        "expect_number": "210",
        "frames": [],
    },
    {
        "name": "E4",
        "prompt": "Tampilkan lima logbook aktivitas periset tanggal 2026-11-05.",
        "expect_tool": "get_logbook_harian",
        "expect_args": {"tanggal": "2026-11-05"},
        "limit_max": 20,
        "expect_number": None,
        "frames": [],
    },
    {
        "name": "E5",
        "prompt": "Sapa singkat: anda siapa ya?",
        "expect_tool": None,
    },
    {
        "name": "E6",
        "prompt": "Ini ragam pertanyaan non-data: apa itu keluaran riset menurut paham umum? Jawaban singkat, tanpa angka platform.",
        "expect_tool": None,
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="", help="nomor kasus 1-based, dipisah koma (mis. 1,4)")
    args = parser.parse_args()

    indices = list(range(1, len(EVAL_CASES) + 1))
    if args.case.strip():
        indices = [int(part) for part in args.case.split(",") if part.strip()]
    selected = [EVAL_CASES[i - 1] for i in indices]

    mock = spawn_mock_analytics(MOCK_ANALYTICS_PORT)
    gateway = spawn_gateway()
    try:
        if not wait_ready(f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}/health"):
            raise RuntimeError("mock analytics tidak siap")
        if not wait_ready(f"http://127.0.0.1:{GATEWAY_PORT}/health", timeout=40):
            raise RuntimeError("gateway (:8120) tidak siap")
        upstream = httpx.get(
            f"http://127.0.0.1:{GATEWAY_PORT}/ai/health/upstream",
            headers={"X-Service-Key": SERVICE_KEY},
            timeout=15.0,
        ).json()
        if not upstream.get("available"):
            raise RuntimeError(f"LLM runtime tidak hidup: {upstream.get('detail')}")

        print(f"eval {len(selected)} kasus, model={upstream.get('model')} — mohon tunggu (inferensi asli)")
        for case in selected:
            started = time.perf_counter()
            with httpx.Client(timeout=httpx.Timeout(150.0, connect=10.0)) as client:
                with client.stream(
                    "POST",
                    f"http://127.0.0.1:{GATEWAY_PORT}/ai/chat",
                    headers={"X-Service-Key": SERVICE_KEY},
                    json={"messages": [{"role": "user", "content": case["prompt"]}]},
                ) as response:
                    status = response.status_code
                    if status != 200:
                        raise RuntimeError(f"chat gagal status={status}")
                    frames = read_sse(response)
            case["frames"] = frames
            elapsed = time.perf_counter() - started
            run_case(case)
            print(f"    case {case['name']} selesai dalam {elapsed:.1f}s")
            httpx.get(f"http://127.0.0.1:{MOCK_ANALYTICS_PORT}/debug/reset", timeout=5.0)
    finally:
        for proc in (mock, gateway):
            if proc.poll() is None:
                proc.terminate()

    header = "Eval R3 — intent / restraint / narasi-analytics"
    print(header)
    print("-" * len(header))
    for name, verdict, note in results:
        print(f"{name}  {verdict:<4} | {note}")
    failed = [t for t, v, _ in results if v == "FAIL"]
    if failed:
        print(f"EVAL TIDAK LOLOS: {','.join(failed)}")
        return 1
    print("EVAL LOLOS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
