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
