"""Live LLM smoke test — opt-in,需 MIMO_API_KEY env var。

跑 `pytest -m live` 才会执行。默认 / CI 跑 `pytest -m "not live"` 跳过。

每个 smoke 单次成本约 < $0.01(thinking=disabled / max_tokens 短)。
不验内容质量(那要更多轮 + Phase E 5 个 demo 实测),只验整链路能跑通。
"""

import os
from pathlib import Path

import pytest

from core.agents.runtime import AgentRuntime
from core.llm_gateway import LLMGateway
from core.rag_repository import InMemoryRAGRepository
from core.schemas import ThinkingPolicy
from core.turn_loop import TurnLoop, TurnLoopConfig
from core.turn_store import TurnStore
from core.world_memory import WorldMemory

from game.text_adventure.loop_wrapper import run_turn_with_curator
from game.text_adventure.memory_curator import TextAdventureCurator
from game.text_adventure.narrative_agent import build_guard, build_narrative_agent
from game.text_adventure.schemas import NarrativeBeat, TextAdventureMemoryKind


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("MIMO_API_KEY"), reason="needs MIMO_API_KEY")
@pytest.mark.asyncio
async def test_live_one_turn_smoke(tmp_path: Path):
    """跑 1 个真实 Turn,验证 NarrativeBeat 能 parse + Guard 有决策。
    不验内容质量(那要更多轮)。"""
    gateway = LLMGateway(
        api_key=os.environ["MIMO_API_KEY"],
        default_thinking=ThinkingPolicy(type="disabled"),  # smoke 控成本
    )
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
            references_priority_kinds=[
                TextAdventureMemoryKind.WORLD_LAW.value,
                TextAdventureMemoryKind.LOCATION.value,
                TextAdventureMemoryKind.CHARACTER.value,
                TextAdventureMemoryKind.EVENT.value,
            ],
            guard_rules=[],
        ),
    )
    curator = TextAdventureCurator(world_memory=wm)

    result = await run_turn_with_curator(
        loop=loop, curator=curator, session_id="live_smoke", raw_text="环顾四周,描述我看到什么",
    )

    # 基本不变量
    assert result.response_text
    assert result.turn.status in {"ok", "degraded"}  # circuit_open 不接受
    assert result.turn.metadata.get("telemetry") is not None
