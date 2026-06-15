from __future__ import annotations

import pytest
from pydantic import BaseModel

from game.world_init.debate import DebateTurn
from core.agents.schemas import AgentProfile, AgentTask
from core.rag_repository import InMemoryRAGRepository
from game.world_init.schemas import CausalImpact, CausalImpactPacket, WorldLaw, WorldSeedCandidate
from main import run_world_init_mvp


class FakeRuntime:
    async def run_agent(self, profile: AgentProfile, task: AgentTask, output_schema: type[BaseModel]) -> BaseModel:
        if output_schema is DebateTurn:
            return DebateTurn(agent_id=profile.id, position="position", claims=["claim"])
        if output_schema is WorldSeedCandidate:
            return WorldSeedCandidate(
                premise="Power costs memory.",
                laws=[WorldLaw(name="Memory Price", statement="Power consumes memory.")],
                tensions=["Power erodes identity."],
                source_summary="Synthesized.",
            )
        if output_schema.__name__ == "GuardDecision":
            return output_schema(decision="accept", findings=[])
        if output_schema is CausalImpactPacket:
            return CausalImpactPacket(
                source_world_seed_id="pending",
                trigger_summary="Memory price changes future incentives.",
                impacts=[
                    CausalImpact(
                        target_type="rule",
                        target_hint="memory escalation",
                        impact_summary="Repeated use adds pressure.",
                        intensity=0.6,
                        delay_ticks=1,
                    )
                ],
            )
        raise AssertionError(output_schema)


@pytest.mark.asyncio
async def test_run_world_init_mvp_writes_seed_law_and_causal_fragments():
    repository = InMemoryRAGRepository()

    result = await run_world_init_mvp(
        answer_text="每一次使用都会失去一段真实记忆。",
        runtime=FakeRuntime(),
        repository=repository,
    )

    assert repository.count() == 3
    assert len(result.fragment_ids) == 3
    assert result.workflow_result.world_seed.premise == "Power costs memory."
    assert repository.hybrid_search("", metadata_filter={"kind": "world_seed"})
    assert repository.hybrid_search("", metadata_filter={"kind": "causal_seed"})

