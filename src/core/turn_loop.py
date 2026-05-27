"""TurnLoop 主路径 spec §6.1 时序。

已实现:accept / revise / reject 三分支(Task 4-5)。
留 Task 6:circuit-open 降级 + TurnTelemetry 记录。
留 Phase C:_build_references 完整顺序(spec §7.B)+ recent turns 摘要。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from core.agents.guard import (
    ConsistencyGuard,
    GuardDecision,
    GuardInput,
    ReferenceItem,
)
from core.agents.narrative import NarrativeAgent, NarrativeContext
from core.schemas import RAGQueryResult, TurnInput
from core.turn_store import Turn, TurnResult, TurnStore
from core.world_memory import MemoryQuery, WorldMemory


class TurnLoopConfig(BaseModel):
    """TurnLoop 行为配置。game 层通过它注入策略。"""

    model_config = {"arbitrary_types_allowed": True}

    narrative_output_schema: type[BaseModel]
    response_text_field: str = "narration"
    retrieval_kinds: list[str] = Field(default_factory=list)
    guard_rules: list[str] = Field(default_factory=list)
    recent_turns_count: int = Field(default=3, ge=0, le=10)
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    degradation_text: str = Field(
        default="<<画面有些模糊,试试换种方式描述你想做的事。>>",
        min_length=1,
    )


class TurnLoop:
    """spec §6.1 主路径编排器。

    Phase B Task 4-5 实现 accept / revise / reject 三分支。
    Task 6 加 circuit-open 降级与 TurnTelemetry。
    """

    def __init__(
        self,
        *,
        narrative_agent: NarrativeAgent,
        guard: ConsistencyGuard,
        world_memory: WorldMemory,
        turn_store: TurnStore,
        config: TurnLoopConfig,
    ) -> None:
        self.narrative_agent = narrative_agent
        self.guard = guard
        self.world_memory = world_memory
        self.turn_store = turn_store
        self.config = config

    async def run_turn(self, *, session_id: str, raw_text: str) -> TurnResult:
        # ① 构造 TurnInput;turn_index 只数 status=="ok" 的 turn(degraded/failed 不前进)
        existing = self.turn_store.load_session(session_id=session_id)
        turn_index = sum(1 for t in existing if t.status == "ok")
        input = TurnInput(
            raw_text=raw_text,
            turn_index=turn_index,
            session_id=session_id,
        )

        # ② Retrieve
        retrieved = self.world_memory.query(MemoryQuery(
            query_text=raw_text,
            session_id=session_id,
            kinds=self.config.retrieval_kinds or None,
            top_k=self.config.retrieval_top_k,
        ))

        # ③ Narrate
        narrative_beat = await self.narrative_agent.run(
            context=NarrativeContext(
                player_input=input,
                retrieved_memory=retrieved,
            ),
            output_schema=self.config.narrative_output_schema,
        )
        proposal = narrative_beat.model_dump(mode="json")

        # ④ Guard
        references = self._build_references(retrieved, existing)
        decision = await self.guard.check(GuardInput(
            proposal=proposal,
            references=references,
            rules=self.config.guard_rules,
            session_id=session_id,
        ))

        guard_retries = 0
        if decision.decision == "accept":
            final_payload = proposal
        elif decision.decision == "revise":
            # revise: 直接采用 revised_payload(不重跑 Narrate)
            # GuardDecision model_validator 已强制 revise 必有 revised_payload,理论不可能为 None。
            # 用 RuntimeError 而非 assert,保证 python -O 下也触发(与 turn_store._path_for 一致 convention)。
            if decision.revised_payload is None:
                raise RuntimeError(
                    "GuardDecision.decision=='revise' but revised_payload is None; "
                    "model_validator should have prevented this — possible schema regression"
                )
            final_payload = decision.revised_payload
            guard_retries = 1
        else:
            # reject: 走降级
            return self._build_degraded_result(
                input=input,
                retrieved=retrieved,
                proposal=proposal,
                decision=decision,
            )

        # ⑤ Curate(Phase B 暂不沉淀,留 Phase D MemoryCurator)
        curated: list = []

        # ⑥ Persist + ⑦ Return
        response_text = self._extract_response_text_from_payload(final_payload)
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=final_payload,
            guard_decision=decision,
            curated_records=curated,
            response_text=response_text,
            status="ok",
        )
        self.turn_store.save(turn)
        return TurnResult(turn=turn, response_text=response_text, guard_retries=guard_retries)

    def _build_degraded_result(
        self,
        *,
        input: TurnInput,
        retrieved: list[RAGQueryResult],
        proposal: dict[str, Any],
        decision: GuardDecision,
    ) -> TurnResult:
        """Guard reject → 安全降级。存盘但不沉淀 curate,status=degraded,
        response_text=固定文案,turn_index 在下次 run_turn 中不计入(因只数 status==ok)。"""
        degradation_text = self.config.degradation_text
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=proposal,
            guard_decision=decision,
            curated_records=[],  # 降级不沉淀
            response_text=degradation_text,
            status="degraded",
            metadata={
                "guard_rejection": {
                    "decision": decision.decision,
                    "findings": [f.model_dump() for f in decision.findings],
                },
            },
        )
        self.turn_store.save(turn)
        return TurnResult(turn=turn, response_text=degradation_text, guard_retries=0)

    def _build_references(
        self,
        retrieved: list[RAGQueryResult],
        recent_turns: list[Turn],
    ) -> list[ReferenceItem]:
        """组装 GuardInput.references。Task 4 简化版:把 retrieved_memory 转 ReferenceItem。
        Task 5+ 会补"最近 N 轮 turn"。spec §7.B 完整顺序留 Phase C。"""
        refs: list[ReferenceItem] = []
        for r in retrieved:
            refs.append(ReferenceItem(
                label=r.fragment.metadata.get("kind", "memory"),
                content=r.fragment.content,
                score=r.score,
            ))
        return refs

    def _extract_response_text_from_payload(self, payload: dict[str, Any]) -> str:
        """从 narrative payload(可能是原 beat,也可能是 revised_payload)取 response_text。"""
        value = payload.get(self.config.response_text_field)
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"narrative payload[{self.config.response_text_field!r}] must be non-empty str; "
                f"got {type(value).__name__}: {value!r}"
            )
        return value
