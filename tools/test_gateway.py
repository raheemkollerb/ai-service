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
SABOTAGE = "SABOTASE-MARKER-jangan-leak"

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


def spawn_gateway(port: int, base_url: str) -> subprocess.Popen:
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
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
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
            f"status={status} last_frame_type={last_type} (errorevent + tanpa 5xx)",
        )

        health = httpx.get("http://127.0.0.1:8102/health", timeout=10.0)
        record(
            "T7",
            health.status_code == 200 and health.json().get("status") == "ok",
            f"status={health.status_code} body={health.json() if health.status_code == 200 else None}",
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


def main() -> int:
    mock = spawn_mock()
    try:
        run_tests()
    finally:
        if mock.poll() is None:
            mock.terminate()
    header = "Acceptance T1-T8 (mock LLM :11999 - gateway :8101 / dead-upstream :8102)"
    print(header)
    print("-" * len(header))
    for test_id, verdict, note in results:
        print(f"{test_id}  {verdict:<4} | {note}")
    failed = [t for t, v, _ in results if v == "FAIL"]
    if failed:
        print(f"TES GAGAL: {','.join(failed)}")
    else:
        print("SEMUA 8 TES PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
