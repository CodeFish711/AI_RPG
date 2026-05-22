from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from core.schemas import Message, ThinkingPolicy


class AgentProfile(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    style_rules: list[str] = Field(default_factory=list)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    thinking: ThinkingPolicy = Field(default_factory=ThinkingPolicy)
    output_schema_name: str | None = None


class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    instruction: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    required_output: str = Field(min_length=1)
    thinking_override: ThinkingPolicy | None = None
    max_tokens_override: int | None = Field(default=None, ge=1)


class AgentRunResult(BaseModel):
    agent_id: str
    task_id: str
    raw_content: str
    parsed: dict[str, Any] | None = None
    messages: list[Message] = Field(default_factory=list)


class ProposedChange(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    change_type: str = Field(min_length=1)
    subject_id: str | None = None
    summary: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    source_agent_ids: list[str] = Field(default_factory=list)
    status: Literal["proposed", "accepted", "rejected"] = "proposed"

