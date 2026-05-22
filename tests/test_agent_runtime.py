from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile, AgentTask, ProposedChange
from core.schemas import LLMRequest, ThinkingPolicy


class AgentOutput(BaseModel):
    position: str


class FakeGateway:
    def __init__(self):
        self.seen_request: LLMRequest | None = None

    async def complete_and_parse(self, request: LLMRequest, output_schema: type[BaseModel]) -> BaseModel:
        self.seen_request = request
        return output_schema.model_validate({"position": "accepted"})


@pytest.mark.asyncio
async def test_agent_runtime_builds_schema_constrained_request_with_task_overrides():
    gateway = FakeGateway()
    runtime = AgentRuntime(gateway=gateway)
    profile = AgentProfile(
        id="critic",
        name="Critic",
        role="Find logical gaps",
        objective="Challenge weak assumptions",
        style_rules=["Be concise"],
        temperature=0.9,
        max_tokens=4096,
        thinking=ThinkingPolicy(type="enabled"),
    )
    task = AgentTask(
        instruction="Review this answer",
        context={"answer": "All power has a price"},
        required_output="Return an AgentOutput JSON object",
        thinking_override=ThinkingPolicy(type="disabled"),
        max_tokens_override=512,
    )

    result = await runtime.run_agent(profile, task, AgentOutput)

    assert result == AgentOutput(position="accepted")
    assert gateway.seen_request is not None
    assert gateway.seen_request.temperature == 0.9
    assert gateway.seen_request.max_tokens == 512
    assert gateway.seen_request.thinking.type == "disabled"
    assert gateway.seen_request.messages[0].role == "system"
    assert "Find logical gaps" in gateway.seen_request.messages[0].content
    assert "Review this answer" in gateway.seen_request.messages[1].content


def test_proposed_change_is_proposed_by_default_and_bounds_confidence():
    change = ProposedChange(change_type="state_update", summary="Candidate update", confidence=0.8)

    assert change.status == "proposed"

    with pytest.raises(ValidationError):
        ProposedChange(change_type="bad", summary="Invalid", confidence=1.5)

