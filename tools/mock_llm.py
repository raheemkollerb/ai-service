import json
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Mock LLM - OpenAI compatible (RCC tests)")

_last_request: dict[str, object] = {}

# Marker observasi yang sisipkan gateway saat re-invoke untuk narasi akhir.
_OBSERVATION_TAG = "[OBSERVASI ANALYTICS"


@app.get("/v1/models")
async def models() -> dict:
    return {
        "object": "list",
        "data": [
            {"id": "qwen3:30b-a3b", "object": "model"},
            {"id": "qwen2.5-coder:14b", "object": "model"},
        ],
    }


@app.get("/debug/last-request")
async def last_request() -> JSONResponse:
    return JSONResponse(_last_request)


def _scripted_output(body: dict) -> str | None:
    """
    Output skripted untuk uji T9-T13 (gateway tools).

    - env MOCK_LLM_TOOL  : JSON marker {"tool": ..., "arguments": {...}};
      saat ada dan percakapan belum membawa observasi, mock mengirim marker.
    - env MOCK_LLM_NARRATION : narasi akhir setelah observasi tiba.
    env diacak per-request agar satu server bisa dipakai lintas uji.
    """
    tool_json = os.environ.get("MOCK_LLM_TOOL")
    if not tool_json:
        return None
    messages = body.get("messages", [])
    got_observation = any(
        _OBSERVATION_TAG in str(message.get("content", ""))
        for message in messages
        if isinstance(message, dict)
    )
    if got_observation:
        return os.environ.get("MOCK_LLM_NARRATION") or "Halo dari mock LLM."
    return tool_json


@app.post("/v1/chat/completions")
async def chat(request: Request) -> StreamingResponse:
    global _last_request
    body = await request.json()
    _last_request = body
    scripted = _scripted_output(body)
    if scripted is not None:
        chunks = [scripted]
    else:
        chunks = ["Halo", " dari", " mock", " LLM."]
    model = body.get("model", "mock")

    # MOCK_LLM_CHUNK_MODE=chars → setiap delta 1–2 char, meniru streaming
    # nyata qwen (marker terbelah lintas delta; uji T9b sliding window).
    if os.environ.get("MOCK_LLM_CHUNK_MODE") == "chars":
        chunks = list("".join(chunks))

    async def generate():
        base = {
            "id": "chatcmpl-mock",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
        }
        opening = dict(base)
        opening["choices"] = [
            {"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}
        ]
        yield f"data: {json.dumps(opening)}\n\n"
        for text in chunks:
            event = dict(base)
            event["choices"] = [
                {"index": 0, "delta": {"content": text}, "finish_reason": None}
            ]
            yield f"data: {json.dumps(event)}\n\n"
        closing = dict(base)
        closing["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        closing["usage"] = {
            "prompt_tokens": 10,
            "completion_tokens": len(chunks),
            "total_tokens": 10 + len(chunks),
        }
        yield f"data: {json.dumps(closing)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=11999, log_level="warning")
