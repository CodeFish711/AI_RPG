from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, Field

from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile, AgentTask
from core.schemas import RAGQueryResult, TurnInput


T = TypeVar("T", bound=BaseModel)


_NARRATIVE_INSTRUCTION = (
    "你是叙事生成 agent。基于玩家本轮输入与检索到的相关记忆,生成下一段叙事 JSON。"
    "如有新事实(角色/地点/事件/玩家状态),通过 output_schema 的相应字段返回。"
)


class NarrativeContext(BaseModel):
    player_input: TurnInput
    retrieved_memory: list[RAGQueryResult] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class NarrativeAgent:
    """单 agent 叙事生成的统一入口,output_schema 由 game 层指定。"""

    def __init__(self, *, runtime: AgentRuntime, profile: AgentProfile) -> None:
        self.runtime = runtime
        self.profile = profile

    async def run(self, *, context: NarrativeContext, output_schema: type[T]) -> T:
        task = AgentTask(
            instruction=_NARRATIVE_INSTRUCTION,
            context=context.model_dump(mode="json"),
            required_output=output_schema.__name__,
        )
        return await self.runtime.run_agent(self.profile, task, output_schema)
