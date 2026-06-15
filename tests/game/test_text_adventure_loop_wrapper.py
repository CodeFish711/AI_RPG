from pathlib import Path

import pytest

from core.agents.guard import GuardDecision, GuardFinding
from core.agents.runtime import AgentRuntime
from core.rag_repository import InMemoryRAGRepository
from core.turn_loop import TurnLoop, TurnLoopConfig
from core.turn_store import TurnStore
from core.world_memory import MemoryQuery, WorldMemory
from tests._fakes import FakeStructuredGateway

from game.text_adventure.memory_curator import TextAdventureCurator
from game.text_adventure.narrative_agent import build_guard, build_narrative_agent
from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind


def _build_wrapper_components(*, gateway: FakeStructuredGateway, tmp_path: Path):
    runtime = AgentRuntime(gateway=gateway)
    wm = WorldMemory(repository=InMemoryRAGRepository())
    store = TurnStore(data_dir=tmp_path)
    loop = TurnLoop(
        narrative_agent=build_narrative_agent(runtime=runtime),
        guard=build_guard(runtime=runtime),
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=NarrativeBeat,
            response_text_field="narration",
            retrieval_kinds=[k.value for k in TextAdventureMemoryKind],
            references_priority_kinds=[k.value for k in TextAdventureMemoryKind],
            guard_rules=[],
        ),
    )
    curator = TextAdventureCurator(world_memory=wm)
    return loop, curator, wm


@pytest.mark.asyncio
async def test_loop_wrapper_curates_when_status_ok(tmp_path: Path):
    """status=ok 时 Curator 接收 beat,通过的 fact 入 WorldMemory。"""
    from game.text_adventure.loop_wrapper import run_turn_with_curator

    gateway = FakeStructuredGateway()
    gateway.queue_response(
        NarrativeBeat,
        NarrativeBeat(
            narration="你站在森林。",
            new_facts=[
                NewFact(kind=TextAdventureMemoryKind.LOCATION, statement="森林深处", confidence=0.9),
            ],
        ),
    )
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    loop, curator, wm = _build_wrapper_components(gateway=gateway, tmp_path=tmp_path)
    result = await run_turn_with_curator(
        loop=loop, curator=curator, session_id="s_ok", raw_text="环顾",
    )

    assert result.turn.status == "ok"
    # WorldMemory 应已写入 "森林" 相关
    found = wm.query(MemoryQuery(query_text="森林 深处", session_id="s_ok", top_k=5))
    assert len(found) >= 1


@pytest.mark.asyncio
async def test_loop_wrapper_skips_curate_when_status_degraded(tmp_path: Path):
    """status=degraded(Guard reject)时 Curator 不运行,WorldMemory 不被污染。"""
    from game.text_adventure.loop_wrapper import run_turn_with_curator

    gateway = FakeStructuredGateway()
    gateway.queue_response(
        NarrativeBeat,
        NarrativeBeat(
            narration="违反法则。",
            new_facts=[
                NewFact(kind=TextAdventureMemoryKind.WORLD_LAW, statement="violation", confidence=0.95),
            ],
        ),
    )
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(severity="error", message="violates law")],
        ),
    )

    loop, curator, wm = _build_wrapper_components(gateway=gateway, tmp_path=tmp_path)
    result = await run_turn_with_curator(
        loop=loop, curator=curator, session_id="s_deg", raw_text="x",
    )

    assert result.turn.status == "degraded"
    # WorldMemory 应保持空,reject 不沉淀
    found = wm.query(MemoryQuery(query_text="violation", session_id="s_deg", top_k=5))
    assert found == []


@pytest.mark.asyncio
async def test_loop_wrapper_records_curated_count_in_turn_metadata(tmp_path: Path):
    """wrapper 应把 curated 数量记录到 turn.metadata["curated_count"]。"""
    from game.text_adventure.loop_wrapper import run_turn_with_curator

    gateway = FakeStructuredGateway()
    gateway.queue_response(
        NarrativeBeat,
        NarrativeBeat(
            narration="x",
            new_facts=[
                NewFact(kind=TextAdventureMemoryKind.EVENT, statement="高置信事件", confidence=0.9),
                NewFact(kind=TextAdventureMemoryKind.EVENT, statement="低置信", confidence=0.3),  # 丢
            ],
        ),
    )
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    loop, curator, wm = _build_wrapper_components(gateway=gateway, tmp_path=tmp_path)
    result = await run_turn_with_curator(
        loop=loop, curator=curator, session_id="s_count", raw_text="x",
    )

    assert result.turn.metadata.get("curated_count") == 1  # 只 1 个通过四道闸


@pytest.mark.asyncio
async def test_loop_wrapper_records_curated_count_zero_on_degraded(tmp_path: Path):
    """status=degraded 时也应记录 curated_count=0(防下游 .get 返 None)。"""
    from game.text_adventure.loop_wrapper import run_turn_with_curator

    gateway = FakeStructuredGateway()
    gateway.queue_response(
        NarrativeBeat,
        NarrativeBeat(narration="违反", new_facts=[]),
    )
    gateway.queue_response(GuardDecision, GuardDecision(decision="reject", findings=[]))

    loop, curator, wm = _build_wrapper_components(gateway=gateway, tmp_path=tmp_path)
    result = await run_turn_with_curator(
        loop=loop, curator=curator, session_id="s_zero", raw_text="x",
    )

    assert result.turn.metadata.get("curated_count") == 0
