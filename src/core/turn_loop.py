"""TurnLoop 主路径 spec §6.1 时序。

已实现:accept / revise / reject 三分支(Task 4-5)+ circuit-open 降级
(Task 6)+ TurnTelemetry 记录(Task 6)。
留 Phase C:_build_references 完整顺序(spec §7.B)+ recent turns 摘要。
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.agents.guard import (
    ConsistencyGuard,
    GuardDecision,
    GuardInput,
    ReferenceItem,
)
from core.agents.narrative import NarrativeAgent, NarrativeContext
from core.llm_gateway import GatewayCircuitOpen
from core.schemas import RAGQueryResult, TurnInput
from core.turn_store import Turn, TurnResult, TurnStore
from core.world_memory import MemoryQuery, WorldMemory


class TurnTelemetry(BaseModel):
    """每轮 TurnLoop 的可观测性指标(spec §7.F)。写入 turn.metadata["telemetry"]。"""

    retrieval_hit_count: int = Field(ge=0)
    retrieval_top_score: float = Field(ge=0.0)
    guard_decision: Literal["accept", "revise", "reject", "circuit_open"]
    guard_findings_count: int = Field(ge=0)
    guard_retries: int = Field(ge=0)
    llm_call_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


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
        start_ns = time.monotonic_ns()
        llm_call_count = 0

        # ① 构造 TurnInput(turn_index 只数 status=="ok",degraded/failed 不前进)
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
        retrieval_hit_count = len(retrieved)
        retrieval_top_score = retrieved[0].score if retrieved else 0.0

        # ③ Narrate(可能抛 GatewayCircuitOpen)
        try:
            narrative_beat = await self.narrative_agent.run(
                context=NarrativeContext(
                    player_input=input,
                    retrieved_memory=retrieved,
                ),
                output_schema=self.config.narrative_output_schema,
            )
            llm_call_count += 1
        except GatewayCircuitOpen:
            return self._build_circuit_open_result(
                input=input,
                retrieved=retrieved,
                start_ns=start_ns,
                llm_call_count=llm_call_count,
                retrieval_hit_count=retrieval_hit_count,
                retrieval_top_score=retrieval_top_score,
            )

        proposal = narrative_beat.model_dump(mode="json")

        # ④ Guard(可能抛 GatewayCircuitOpen)
        references = self._build_references(retrieved, existing)
        try:
            decision = await self.guard.check(GuardInput(
                proposal=proposal,
                references=references,
                rules=self.config.guard_rules,
                session_id=session_id,
            ))
            llm_call_count += 1
        except GatewayCircuitOpen:
            return self._build_circuit_open_result(
                input=input,
                retrieved=retrieved,
                start_ns=start_ns,
                llm_call_count=llm_call_count,
                retrieval_hit_count=retrieval_hit_count,
                retrieval_top_score=retrieval_top_score,
                partial_proposal=proposal,
            )

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
                start_ns=start_ns,
                llm_call_count=llm_call_count,
                retrieval_hit_count=retrieval_hit_count,
                retrieval_top_score=retrieval_top_score,
            )

        # ⑤-⑦ 正常路径(accept / revise)
        response_text = self._extract_response_text_from_payload(final_payload)
        telemetry = TurnTelemetry(
            retrieval_hit_count=retrieval_hit_count,
            retrieval_top_score=retrieval_top_score,
            guard_decision=decision.decision,
            guard_findings_count=len(decision.findings),
            guard_retries=guard_retries,
            llm_call_count=llm_call_count,
            duration_ms=_elapsed_ms(start_ns),
        )
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=final_payload,
            guard_decision=decision,
            curated_records=[],  # Phase B 不沉淀,Phase D MemoryCurator 接
            response_text=response_text,
            status="ok",
            metadata={"telemetry": telemetry.model_dump()},
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
        start_ns: int,
        llm_call_count: int,
        retrieval_hit_count: int,
        retrieval_top_score: float,
    ) -> TurnResult:
        """Guard reject → 安全降级。存盘但不沉淀 curate,status=degraded。

        turn_index 由 run_turn ① 通过 `status=='ok'` 计数,degraded turn 不前进 —
        下次同 session 的 run_turn 将复用相同的 turn_index。
        """
        telemetry = TurnTelemetry(
            retrieval_hit_count=retrieval_hit_count,
            retrieval_top_score=retrieval_top_score,
            guard_decision=decision.decision,
            guard_findings_count=len(decision.findings),
            guard_retries=0,
            llm_call_count=llm_call_count,
            duration_ms=_elapsed_ms(start_ns),
        )
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=proposal,
            guard_decision=decision,
            curated_records=[],
            response_text=self.config.degradation_text,
            status="degraded",
            metadata={
                "guard_rejection": {
                    "decision": decision.decision,
                    "findings": [f.model_dump() for f in decision.findings],
                },
                "telemetry": telemetry.model_dump(),
            },
        )
        self.turn_store.save(turn)
        return TurnResult(turn=turn, response_text=self.config.degradation_text, guard_retries=0)

    def _build_circuit_open_result(
        self,
        *,
        input: TurnInput,
        retrieved: list[RAGQueryResult],
        start_ns: int,
        llm_call_count: int,
        retrieval_hit_count: int,
        retrieval_top_score: float,
        partial_proposal: dict[str, Any] | None = None,
    ) -> TurnResult:
        """LLM Gateway circuit open → 系统级降级。status=failed,与 reject(degraded)区分。

        turn_index 由 run_turn ① 通过 `status=='ok'` 计数,failed turn 不前进 —
        下次同 session 的 run_turn 将复用相同的 turn_index。
        """
        telemetry = TurnTelemetry(
            retrieval_hit_count=retrieval_hit_count,
            retrieval_top_score=retrieval_top_score,
            guard_decision="circuit_open",
            guard_findings_count=0,
            guard_retries=0,
            llm_call_count=llm_call_count,
            duration_ms=_elapsed_ms(start_ns),
        )
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=partial_proposal,
            guard_decision=None,
            curated_records=[],
            response_text=self.config.degradation_text,
            status="failed",
            metadata={
                "circuit_open": True,
                "telemetry": telemetry.model_dump(),
            },
        )
        self.turn_store.save(turn)
        return TurnResult(turn=turn, response_text=self.config.degradation_text, guard_retries=0)

    def _build_references(
        self,
        retrieved: list[RAGQueryResult],
        recent_turns: list[Turn],
    ) -> list[ReferenceItem]:
        """组装 GuardInput.references。Phase B 简化版:只 retrieved_memory → ReferenceItem。
        Phase C 实现完整 §7.B 顺序(rules > world_law > recent_turns > characters > events)。"""
        refs: list[ReferenceItem] = []
        for r in retrieved:
            refs.append(ReferenceItem(
                label=r.fragment.metadata.get("kind", "memory"),
                content=r.fragment.content,
                score=r.score,
            ))
        return refs

    def _extract_response_text_from_payload(self, payload: dict[str, Any]) -> str:
        """从 narrative payload(原 beat 或 revised_payload)取 response_text。"""
        value = payload.get(self.config.response_text_field)
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"narrative payload[{self.config.response_text_field!r}] must be non-empty str; "
                f"got {type(value).__name__}: {value!r}"
            )
        return value


def _elapsed_ms(start_ns: int) -> int:
    return max(0, (time.monotonic_ns() - start_ns) // 1_000_000)
