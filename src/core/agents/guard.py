from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core._validators import SESSION_ID_PATTERN
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
    session_id: str = Field(min_length=1, pattern=SESSION_ID_PATTERN)


# 通用 default instruction:不含任何游戏域措辞(原 "Canon Guard / 复活死人 /
# 凭空物品" 已剔除)。game 层可通过 ConsistencyGuard(instruction=...) 注入
# 自己的 game-specific prompt template。
DEFAULT_GUARD_INSTRUCTION = (
    "你是一致性裁决 agent。根据'参考材料'与'硬性规则'判定'提案'是否合规,"
    "返回 GuardDecision JSON。"
    "accept = 提案与参考一致放行;"
    "revise = 提案存在可修复的小矛盾,必须给出 revised_payload(修订后的完整提案);"
    "reject = 提案存在不可修复的矛盾。"
)


class ConsistencyGuard:
    """通用 Guard:把 GuardInput 装进 AgentTask,调 AgentRuntime,返回 GuardDecision。

    `instruction` 参数允许 game 层注入 game-specific prompt template,
    None 时用 DEFAULT_GUARD_INSTRUCTION。
    """

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        profile: AgentProfile,
        instruction: str | None = None,
    ) -> None:
        self.runtime = runtime
        self.profile = profile
        self.instruction = instruction if instruction is not None else DEFAULT_GUARD_INSTRUCTION

    async def check(self, guard_input: GuardInput) -> GuardDecision:
        task = AgentTask(
            instruction=self.instruction,
            context=guard_input.model_dump(mode="json"),
            required_output="GuardDecision",
        )
        return await self.runtime.run_agent(self.profile, task, GuardDecision)
