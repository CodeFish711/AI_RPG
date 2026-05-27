from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from core.agents.guard import ConsistencyGuard, GuardDecision
from core.agents.narrative import NarrativeAgent
from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile
from core.rag_repository import InMemoryRAGRepository
from core.turn_store import Turn, TurnStore
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
