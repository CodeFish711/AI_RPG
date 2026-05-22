from __future__ import annotations

from datetime import UTC, datetime
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


class TickEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    tick_id: str | None = None
    event_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SimulationNode(BaseModel):
    id: str = Field(min_length=1)
    node_type: str = Field(min_length=1)
    active: bool = True
    last_tick: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

