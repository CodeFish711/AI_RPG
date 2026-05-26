from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ThinkingPolicy(BaseModel):
    type: Literal["disabled", "auto", "enabled"] = "auto"


class LLMRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    model: str = "mimo-v2.5-pro"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    thinking: ThinkingPolicy = Field(default_factory=ThinkingPolicy)
    extra: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: dict[str, Any] = Field(default_factory=dict)
    finish_reason: str | None = None
    cached: bool = False


class MemoryFragment(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class RAGQueryResult(BaseModel):
    fragment: MemoryFragment
    score: float


class TurnInput(BaseModel):
    raw_text: str = Field(min_length=1)
    intent_hint: str | None = None
    turn_index: int = Field(ge=0)
    session_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_\-]+$")


class TurnResult(BaseModel):
    # Turn 类放在 core.turn_store(Task 5),避免循环引用。
    # TurnResult 在 Phase A 只声明字段;run_turn 方法签名 in Phase B 才完整使用。
    turn_id: str = Field(min_length=1)
    response_text: str = Field(min_length=1)
    guard_retries: int = Field(default=0, ge=0)
