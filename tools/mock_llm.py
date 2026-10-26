import json
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Mock LLM - OpenAI compatible (RCC tests)")

_last_request: dict[str, object] = {}


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


@app.post("/v1/chat/completions")
async def chat(request: Request) -> StreamingResponse:
    global _last_request
    body = await request.json()
    _last_request = body
    chunks = ["Halo", " dari", " mock", " LLM."]
    model = body.get("model", "mock")

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
