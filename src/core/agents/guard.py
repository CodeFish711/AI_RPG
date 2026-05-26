from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile, AgentTask


class GuardFinding(BaseModel):
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1)
    path: str | None = None


class GuardDecision(BaseModel):
    decision: Literal["accept", "revise", "reject"]
    findings: list[GuardFinding] = Field(default_factory=list)
    revised_payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _revise_requires_payload(self) -> "GuardDecision":
        if self.decision == "revise" and self.revised_payload is None:
            raise ValueError("revised_payload is required when decision='revise'")
        return self


class ReferenceItem(BaseModel):
    label: str = Field(min_length=1)
    content: str = Field(min_length=1)
    score: float | None = None


class GuardInput(BaseModel):
    proposal: dict[str, Any]
    references: list[ReferenceItem] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    session_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_\-]+$")


_GUARD_INSTRUCTION = (
    "你是 Canon Guard。判断'提案'是否违反'参考材料',返回 GuardDecision JSON。"
    "accept = 一致放行;revise = 可修复小矛盾,必须给 revised_payload;"
    "reject = 不可修复矛盾(违反法则/复活死人/凭空物品)。"
)


class ConsistencyGuard:
    """通用 Guard:把 GuardInput 装进 AgentTask,调 AgentRuntime,返回 GuardDecision。"""

    def __init__(self, *, runtime: AgentRuntime, profile: AgentProfile) -> None:
        self.runtime = runtime
        self.profile = profile

    async def check(self, guard_input: GuardInput) -> GuardDecision:
        task = AgentTask(
            instruction=_GUARD_INSTRUCTION,
            context=guard_input.model_dump(mode="json"),
            required_output="GuardDecision",
        )
        return await self.runtime.run_agent(self.profile, task, GuardDecision)
