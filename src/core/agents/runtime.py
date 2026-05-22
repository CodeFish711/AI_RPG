from __future__ import annotations

import json
from typing import Protocol, TypeVar

from pydantic import BaseModel

from core.agents.schemas import AgentProfile, AgentTask
from core.schemas import LLMRequest, Message


T = TypeVar("T", bound=BaseModel)


class StructuredGateway(Protocol):
    async def complete_and_parse(self, request: LLMRequest, output_schema: type[T]) -> T:
        ...


class AgentRuntime:
    def __init__(self, *, gateway: StructuredGateway):
        self.gateway = gateway

    async def run_agent(self, profile: AgentProfile, task: AgentTask, output_schema: type[T]) -> T:
        request = self._build_request(profile, task, output_schema)
        return await self.gateway.complete_and_parse(request, output_schema)

    def _build_request(self, profile: AgentProfile, task: AgentTask, output_schema: type[BaseModel]) -> LLMRequest:
        system = self._build_system_message(profile, output_schema)
        user = self._build_user_message(task)
        return LLMRequest(
            messages=[system, user],
            temperature=profile.temperature,
            max_tokens=task.max_tokens_override or profile.max_tokens,
            thinking=task.thinking_override or profile.thinking,
        )

    @staticmethod
    def _build_system_message(profile: AgentProfile, output_schema: type[BaseModel]) -> Message:
        schema_json = json.dumps(output_schema.model_json_schema(), ensure_ascii=False)
        style = "\n".join(f"- {rule}" for rule in profile.style_rules) or "- No extra style rules."
        return Message(
            role="system",
            content=(
                f"Agent name: {profile.name}\n"
                f"Agent role: {profile.role}\n"
                f"Objective: {profile.objective}\n"
                f"Style rules:\n{style}\n\n"
                "You must return only valid JSON matching this schema:\n"
                f"{schema_json}"
            ),
        )

    @staticmethod
    def _build_user_message(task: AgentTask) -> Message:
        context_json = json.dumps(task.context, ensure_ascii=False, sort_keys=True)
        return Message(
            role="user",
            content=(
                f"Instruction:\n{task.instruction}\n\n"
                f"Context JSON:\n{context_json}\n\n"
                f"Required output:\n{task.required_output}"
            ),
        )

