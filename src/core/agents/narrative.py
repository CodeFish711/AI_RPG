from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, Field

from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile, AgentTask
from core.schemas import RAGQueryResult, TurnInput


T = TypeVar("T", bound=BaseModel)


# 通用 default instruction:不含游戏域措辞(原"角色/地点/事件/玩家状态"已剔除)。
# game 层可通过 NarrativeAgent(instruction=...) 注入自己的 game-specific prompt。
DEFAULT_NARRATIVE_INSTRUCTION = (
    "你是叙事生成 agent。基于玩家本轮输入与检索到的相关记忆,"
    "生成符合 output_schema 的下一段叙事 JSON。"
    "如有新事实需要记录,通过 output_schema 的相应字段返回。"
)


class NarrativeContext(BaseModel):
    player_input: TurnInput
    retrieved_memory: list[RAGQueryResult] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class NarrativeAgent:
    """单 agent 叙事生成的统一入口,output_schema 由 game 层指定。

    `instruction` 参数允许 game 层注入 game-specific prompt template,
    None 时用 DEFAULT_NARRATIVE_INSTRUCTION。
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
        self.instruction = instruction if instruction is not None else DEFAULT_NARRATIVE_INSTRUCTION

    async def run(self, *, context: NarrativeContext, output_schema: type[T]) -> T:
        task = AgentTask(
            instruction=self.instruction,
            context=context.model_dump(mode="json"),
            required_output=output_schema.__name__,
        )
        return await self.runtime.run_agent(self.profile, task, output_schema)
