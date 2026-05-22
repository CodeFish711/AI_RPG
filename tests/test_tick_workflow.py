from __future__ import annotations

import pytest
from pydantic import BaseModel

from core.agents.schemas import AgentProfile, AgentTask
from core.rag_repository import InMemoryRAGRepository
from game.world_init.schemas import CausalImpact, CausalImpactPacket
from game.world_sim.schemas import NodeTickOutcome
from game.world_sim.tick_workflow import WorldTickWorkflow


def _packet(*impacts: CausalImpact) -> CausalImpactPacket:
    return CausalImpactPacket(
        source_world_seed_id="seed-1",
        trigger_summary="Memory price reshapes incentives.",
        impacts=list(impacts),
    )


def _impact(hint: str, *, delay: int = 0, target_type: str = "region") -> CausalImpact:
    return CausalImpact(
        target_type=target_type,
        target_hint=hint,
        impact_summary=f"Pressure builds around {hint}.",
        intensity=0.6,
        delay_ticks=delay,
    )


class FakeNodeRuntime:
    """Returns a plain outcome per node tick; optionally seeds one new impact once."""

    def __init__(self, *, seed_new_impact_on_call: int | None = None):
        self.calls = 0
        self.seed_new_impact_on_call = seed_new_impact_on_call

    async def run_agent(self, profile: AgentProfile, task: AgentTask, output_schema: type[BaseModel]) -> BaseModel:
        self.calls += 1
        node_id = task.context["node"]["id"]
        new_impacts = []
        if self.seed_new_impact_on_call == self.calls:
            new_impacts = [_impact("downstream effect", delay=0, target_type="group")]
        return NodeTickOutcome(
            node_id=node_id,
            tick=task.context["incoming_event"].get("tick_id") or 0,
            narrative=f"Node {node_id} reacts on call {self.calls}.",
            new_impacts=new_impacts,
        )


@pytest.mark.asyncio
async def test_bootstrap_schedules_one_event_per_impact():
    workflow = WorldTickWorkflow(runtime=FakeNodeRuntime(), repository=InMemoryRAGRepository())
    workflow.bootstrap(_packet(_impact("north"), _impact("south")), "seed-1")

    assert workflow.bus.pending_count() == 2


@pytest.mark.asyncio
async def test_run_advances_ticks_and_writes_tick_outcome_fragments():
    repository = InMemoryRAGRepository()
    workflow = WorldTickWorkflow(runtime=FakeNodeRuntime(), repository=repository)

    result = await workflow.run(_packet(_impact("north", delay=0), _impact("south", delay=1)), "seed-1")

    assert result.world_seed_id == "seed-1"
    assert sum(len(record.outcomes) for record in result.records) == 2
    written = repository.hybrid_search("", metadata_filter={"kind": "tick_outcome"})
    assert len(written) == 2


@pytest.mark.asyncio
async def test_run_reschedules_new_impacts_from_node_outcomes():
    runtime = FakeNodeRuntime(seed_new_impact_on_call=1)
    workflow = WorldTickWorkflow(runtime=runtime, repository=InMemoryRAGRepository())

    result = await workflow.run(_packet(_impact("north", delay=0)), "seed-1")

    # one bootstrapped impact + one rescheduled downstream impact = 2 node ticks
    assert runtime.calls == 2
    processed_nodes = {outcome.node_id for record in result.records for outcome in record.outcomes}
    assert "group:downstream-effect" in processed_nodes


@pytest.mark.asyncio
async def test_run_stops_at_max_ticks_when_impacts_keep_regenerating():
    class AlwaysSpawningRuntime:
        def __init__(self):
            self.calls = 0

        async def run_agent(self, profile, task, output_schema):
            self.calls += 1
            node_id = task.context["node"]["id"]
            return NodeTickOutcome(
                node_id=node_id,
                tick=0,
                narrative="Endless ripple.",
                new_impacts=[_impact(f"ripple-{self.calls}", delay=0)],
            )

    workflow = WorldTickWorkflow(
        runtime=AlwaysSpawningRuntime(),
        repository=InMemoryRAGRepository(),
        max_ticks=3,
    )

    result = await workflow.run(_packet(_impact("north", delay=0)), "seed-1")

    assert result.final_tick == 3
    assert len(result.records) == 3


@pytest.mark.asyncio
async def test_run_stops_early_when_event_queue_empties():
    workflow = WorldTickWorkflow(runtime=FakeNodeRuntime(), repository=InMemoryRAGRepository(), max_ticks=20)

    result = await workflow.run(_packet(_impact("north", delay=0)), "seed-1")

    assert result.final_tick == 1
    assert len(result.records) == 1
