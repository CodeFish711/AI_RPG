from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from core.agents.guard import ConsistencyGuard, GuardDecision
from core.agents.narrative import NarrativeAgent
from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile
from core.rag_repository import InMemoryRAGRepository
from core.turn_store import TurnStore
from core.world_memory import WorldMemory
from tests._fakes import FakeStructuredGateway


class _Beat(BaseModel):
    narration: str = Field(min_length=1)
    new_facts: list[str] = Field(default_factory=list)


def _build_components(*, gateway: FakeStructuredGateway, tmp_path: Path):
    runtime = AgentRuntime(gateway=gateway)
    narrative = NarrativeAgent(
        runtime=runtime,
        profile=AgentProfile(id="n", name="N", role="narrator", objective="o"),
    )
    guard = ConsistencyGuard(
        runtime=runtime,
        profile=AgentProfile(id="g", name="G", role="guard", objective="o"),
    )
    world_memory = WorldMemory(repository=InMemoryRAGRepository())
    turn_store = TurnStore(data_dir=tmp_path)
    return narrative, guard, world_memory, turn_store


@pytest.mark.asyncio
async def test_turn_loop_run_turn_happy_accept(tmp_path: Path):
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    # 2 次 LLM 响应:Narrative beat → Guard accept
    gateway.queue_response(_Beat, _Beat(narration="你站在森林边缘。"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=["world_law"],
            guard_rules=["rule1"],
        ),
    )

    result = await loop.run_turn(session_id="sess_01", raw_text="环顾四周")

    assert result.response_text == "你站在森林边缘。"
    assert result.guard_retries == 0
    assert result.turn.status == "ok"
    assert result.turn.input.raw_text == "环顾四周"
    assert result.turn.input.turn_index == 0
    assert result.turn.guard_decision is not None
    assert result.turn.guard_decision.decision == "accept"
    saved = store.load_session(session_id="sess_01")
    assert len(saved) == 1
    assert saved[0].id == result.turn.id


@pytest.mark.asyncio
async def test_turn_loop_run_turn_increments_turn_index_across_calls(tmp_path: Path):
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    for i in range(2):
        gateway.queue_response(_Beat, _Beat(narration=f"narration_{i}"))
        gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=["world_law"],
            guard_rules=[],
        ),
    )
    result0 = await loop.run_turn(session_id="sess_02", raw_text="行动 0")
    result1 = await loop.run_turn(session_id="sess_02", raw_text="行动 1")

    assert result0.turn.input.turn_index == 0
    assert result1.turn.input.turn_index == 1
    saved = store.load_session(session_id="sess_02")
    assert len(saved) == 2


@pytest.mark.asyncio
async def test_turn_loop_run_turn_passes_retrieved_memory_into_narrative(tmp_path: Path):
    """retrieve → narrative 链路:已写入 WorldMemory 的记录会作为 retrieved_memory 进 narrative context。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig
    from core.world_memory import MemoryRecord

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="response"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    # 预先写入 world_law,query "blood" 时应捞到
    wm.upsert(MemoryRecord(
        kind="world_law", content="magic requires blood",
        source="seed", session_id="sess_03",
    ))

    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=["world_law"],
            guard_rules=[],
        ),
    )
    result = await loop.run_turn(session_id="sess_03", raw_text="blood ritual")

    # Narrative agent 收到的 user message 应包含 retrieved 中的 "magic requires blood"
    narrative_user_msg = gateway.invocations[0].messages[1]
    assert "magic requires blood" in narrative_user_msg.content
    assert result.turn.retrieved_memory  # 非空


@pytest.mark.asyncio
async def test_turn_loop_guard_revise_adopts_revised_payload(tmp_path: Path):
    """revise: 不重跑 Narrate,直接采用 revised_payload,guard_retries=1,status=ok。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="原始叙述,有矛盾"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="revise",
            findings=[],
            revised_payload={"narration": "修订后的叙述", "new_facts": []},
        ),
    )

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            guard_rules=[],
        ),
    )
    result = await loop.run_turn(session_id="sess_rv", raw_text="test")

    # response_text 来自 revised_payload,而非原始 narrative
    assert result.response_text == "修订后的叙述"
    assert result.guard_retries == 1
    assert result.turn.status == "ok"  # revise 算合规
    # 只调 2 次 LLM(Narrate + Guard),没重跑 Narrate
    assert len(gateway.invocations) == 2


@pytest.mark.asyncio
async def test_turn_loop_guard_reject_degrades(tmp_path: Path):
    """reject: response_text=degradation_text, status=degraded, turn.metadata 记录 findings。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="违反法则的内容"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(decision="reject", findings=[]),
    )

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            guard_rules=[],
            degradation_text="<<降级文案>>",
        ),
    )
    result = await loop.run_turn(session_id="sess_rj", raw_text="test")

    assert result.response_text == "<<降级文案>>"
    assert result.turn.status == "degraded"
    assert result.turn.metadata.get("guard_rejection") is not None
    assert result.turn.metadata["guard_rejection"]["decision"] == "reject"


@pytest.mark.asyncio
async def test_turn_loop_reject_does_not_advance_turn_index(tmp_path: Path):
    """连续两次 reject 后,turn_index 仍是 0(degraded turn 不计入)。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    for _ in range(2):
        gateway.queue_response(_Beat, _Beat(narration="违反"))
        gateway.queue_response(GuardDecision, GuardDecision(decision="reject", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            guard_rules=[],
        ),
    )
    r0 = await loop.run_turn(session_id="sess_nx", raw_text="试 1")
    r1 = await loop.run_turn(session_id="sess_nx", raw_text="试 2")

    assert r0.turn.input.turn_index == 0
    assert r1.turn.input.turn_index == 0  # 仍是 0,degraded 不计入
    saved = store.load_session(session_id="sess_nx")
    assert len(saved) == 2
    assert all(t.status == "degraded" for t in saved)


@pytest.mark.asyncio
async def test_turn_loop_circuit_open_degrades_as_failed(tmp_path: Path):
    """LLM Gateway 抛 GatewayCircuitOpen → 降级 status=failed,不向上抛。"""
    from core.llm_gateway import GatewayCircuitOpen
    from core.turn_loop import TurnLoop, TurnLoopConfig

    class _CircuitOpenGateway:
        def __init__(self):
            self.invocations = []

        async def complete_and_parse(self, request, output_schema):
            self.invocations.append(request)
            raise GatewayCircuitOpen("circuit open")

    gateway = _CircuitOpenGateway()
    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            guard_rules=[],
        ),
    )
    result = await loop.run_turn(session_id="sess_co", raw_text="test")

    # 基本断言
    assert result.turn.status == "failed"
    assert result.response_text  # 非空 — degradation_text
    assert result.turn.metadata.get("circuit_open") is True

    # Narrate 第一次就抛 → narrative_draft 应为 None,llm_call_count == 0
    assert result.turn.narrative_draft is None
    telemetry = result.turn.metadata["telemetry"]
    assert telemetry["guard_decision"] == "circuit_open"
    assert telemetry["llm_call_count"] == 0
    assert telemetry["guard_findings_count"] == 0
    assert telemetry["guard_retries"] == 0


@pytest.mark.asyncio
async def test_turn_loop_circuit_open_at_guard_stage_keeps_partial_proposal(tmp_path: Path):
    """Guard 阶段(而非 Narrate 阶段)抛 GatewayCircuitOpen → narrative_draft 保留 partial,llm_call_count=1。"""
    from core.llm_gateway import GatewayCircuitOpen
    from core.turn_loop import TurnLoop, TurnLoopConfig

    class _PartialFailGateway:
        """第 1 次(Narrate)成功返回 _Beat,第 2 次(Guard)抛 GatewayCircuitOpen。"""
        def __init__(self):
            self.invocations = []
            self._call_count = 0

        async def complete_and_parse(self, request, output_schema):
            self.invocations.append(request)
            self._call_count += 1
            if self._call_count == 1:
                return _Beat(narration="partial narrative")
            raise GatewayCircuitOpen("circuit open during guard")

    gateway = _PartialFailGateway()
    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            guard_rules=[],
        ),
    )
    result = await loop.run_turn(session_id="sess_co2", raw_text="test")

    assert result.turn.status == "failed"
    assert result.turn.metadata.get("circuit_open") is True
    # Narrate 成功 → narrative_draft 保留(非 None)
    assert result.turn.narrative_draft is not None
    assert result.turn.narrative_draft.get("narration") == "partial narrative"
    # llm_call_count == 1(Narrate 成功 + Guard 失败前 +1)
    telemetry = result.turn.metadata["telemetry"]
    assert telemetry["llm_call_count"] == 1
    assert telemetry["guard_decision"] == "circuit_open"


@pytest.mark.asyncio
async def test_turn_loop_records_telemetry_to_turn_metadata(tmp_path: Path):
    """每轮记录 TurnTelemetry 到 turn.metadata["telemetry"]。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig
    from core.world_memory import MemoryRecord

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="ok"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    # 预先写入,使 retrieval_hit_count > 0
    wm.upsert(MemoryRecord(kind="world_law", content="foo", source="s", session_id="sess_t"))

    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=["world_law"],
            guard_rules=[],
        ),
    )
    result = await loop.run_turn(session_id="sess_t", raw_text="foo")

    telemetry = result.turn.metadata.get("telemetry")
    assert telemetry is not None
    assert telemetry["retrieval_hit_count"] >= 1
    assert telemetry["guard_decision"] == "accept"
    assert telemetry["guard_findings_count"] == 0
    assert telemetry["guard_retries"] == 0
    assert telemetry["llm_call_count"] == 2  # Narrate + Guard
    assert telemetry["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_turn_loop_build_references_orders_by_priority_kinds(tmp_path: Path):
    """references_priority_kinds 决定 kind 类记忆的输出顺序。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig
    from core.world_memory import MemoryRecord

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="ok"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    # 写入 3 个 kind 的记忆,query 含 "shared" 让全部召回
    wm.upsert(MemoryRecord(kind="world_law", content="shared world law text", source="s", session_id="sess_pri"))
    wm.upsert(MemoryRecord(kind="character", content="shared character text", source="s", session_id="sess_pri"))
    wm.upsert(MemoryRecord(kind="event", content="shared event text", source="s", session_id="sess_pri"))

    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=["world_law", "character", "event"],
            references_priority_kinds=["world_law", "character", "event"],
            guard_rules=[],
        ),
    )
    await loop.run_turn(session_id="sess_pri", raw_text="shared query")

    # Guard 收到的 user message 含 references JSON,按 priority 顺序出现
    guard_msg = gateway.invocations[1].messages[1]
    world_law_idx = guard_msg.content.find("shared world law text")
    character_idx = guard_msg.content.find("shared character text")
    event_idx = guard_msg.content.find("shared event text")
    assert 0 <= world_law_idx < character_idx < event_idx, (
        f"references 顺序错: world_law@{world_law_idx} character@{character_idx} event@{event_idx}"
    )


@pytest.mark.asyncio
async def test_turn_loop_build_references_includes_recent_turns_summary(tmp_path: Path):
    """recent_turns 摘要应进入 Guard references(label='recent_turn:N')。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    for i in range(2):
        gateway.queue_response(_Beat, _Beat(narration=f"narration_{i}_unique_token"))
        gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            references_priority_kinds=[],
            guard_rules=[],
            recent_turns_count=3,
        ),
    )

    await loop.run_turn(session_id="sess_recent", raw_text="action 0")
    await loop.run_turn(session_id="sess_recent", raw_text="action 1")

    # 第 2 轮 Guard 应见到第 1 轮的 raw_text 或 response_text
    second_guard_msg = gateway.invocations[3].messages[1]
    assert "action 0" in second_guard_msg.content or "narration_0_unique_token" in second_guard_msg.content


@pytest.mark.asyncio
async def test_turn_loop_build_references_first_turn_has_no_recent_turns(tmp_path: Path):
    """第 1 轮 references 不含 'recent_turn:' label。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="ok"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            references_priority_kinds=[],
            guard_rules=[],
        ),
    )
    await loop.run_turn(session_id="sess_first", raw_text="first turn")

    guard_msg = gateway.invocations[1].messages[1]
    assert "recent_turn:" not in guard_msg.content
