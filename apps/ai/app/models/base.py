from typing import Literal, Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: Optional[str] = None


class HealthResponse(BaseModel):
    status: str


class UpstreamHealth(BaseModel):
    llm_base_url: str
    model: str
    available: bool
    models: Optional[list[str]] = None
    error: Optional[str] = None
