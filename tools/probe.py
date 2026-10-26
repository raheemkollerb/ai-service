import argparse
import json
import sys
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--num-predict", type=int, default=16)
    parser.add_argument("--stream", default="false")
    args = parser.parse_args()

    body = {
        "model": args.model,
        "prompt": args.prompt,
        "stream": args.stream.lower() == "true",
        "options": {"num_predict": args.num_predict},
    }
    start = time.time()
    try:
        with httpx.Client(timeout=300.0) as client:
            if body["stream"]:
                total = 0
                first = None
                with client.stream("POST", f"{args.host}/api/generate", json=body) as resp:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        event = json.loads(line)
                        if "error" in event:
                            print("ERROR:", event["error"])
                            return 1
                        if event.get("response"):
                            if first is None:
                                first = time.time()
                            total += 1
                        if event.get("done"):
                            payload = event.get("eval_count"), event.get("eval_duration")
                            print("DONE count/duration:", payload)
                now = time.time()
                if first and total:
                    gen = (now - first) / max(total - 1, 1) * 1000
                    print(f"tokens={total} first_ttft={first - start:.2f}s approx_ms_per_tok={gen:.1f}")
                    print(f"approx_tok_s={1000 / gen:.1f}")
            else:
                resp = client.post(f"{args.host}/api/generate", json=body)
                if resp.status_code != 200:
                    print(f"HTTP {resp.status_code}:", resp.text[:300])
                    return 1
                data = resp.json()
                if "error" in data:
                    print("ERROR:", data["error"])
                    return 1
                print("OUTPUT:", data.get("response", "").strip()[:400])
                stats = {
                    "load_ms": data.get("load_duration"),
                    "prompt_eval_ms": data.get("prompt_eval_duration"),
                    "eval_ms": data.get("eval_duration"),
                    "eval_count": data.get("eval_count"),
                }
                print("STATS:", json.dumps(stats))
                if data.get("eval_duration") and data.get("eval_count"):
                    rate = data["eval_count"] / (data["eval_duration"] / 1e9)
                    print(f"TOK_S: {rate:.1f}")
                print(f"WALL: {time.time() - start:.2f}s")
    except httpx.HTTPError as exc:
        print("CLIENT ERROR:", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
