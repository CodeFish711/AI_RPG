from __future__ import annotations

import pytest
from pydantic import BaseModel

from core.agents.schemas import AgentProfile, AgentTask, ProposedChange
from core.rag_repository import InMemoryRAGRepository
from core.schemas import MemoryFragment
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


class RecordingRuntime:
    """Captures the retrieved_memory passed to each prompt and returns a plain outcome."""

    def __init__(self, *, loop_on_same_node: bool = False):
        self.calls = 0
        self.retrieved_memory_per_call: list[list[dict]] = []
        self.loop_on_same_node = loop_on_same_node

    async def run_agent(self, profile: AgentProfile, task: AgentTask, output_schema: type[BaseModel]) -> BaseModel:
        self.calls += 1
        self.retrieved_memory_per_call.append(task.context["retrieved_memory"])
        node_id = task.context["node"]["id"]
        proposed = [
            ProposedChange(change_type="state", summary=f"State change {self.calls}", confidence=0.6)
        ]
        new_impacts = []
        if self.loop_on_same_node and self.calls == 1:
            new_impacts = [_impact("north", delay=0)]  # same hint -> same node
        return NodeTickOutcome(
            node_id=node_id,
            tick=task.context["node"]["last_tick"] + 1,
            narrative=f"Narrative {self.calls}",
            proposed_changes=proposed,
            new_impacts=new_impacts,
        )


@pytest.mark.asyncio
async def test_node_metadata_accumulates_narratives_and_advances_last_tick():
    runtime = RecordingRuntime(loop_on_same_node=True)
    workflow = WorldTickWorkflow(runtime=runtime, repository=InMemoryRAGRepository())

    await workflow.run(_packet(_impact("north", delay=0)), "seed-1")

    node = workflow.bus.get_node("region:north")
    assert node.last_tick == workflow.bus.current_tick
    assert node.metadata["recent_narratives"] == ["Narrative 1", "Narrative 2"]
    assert node.metadata["change_log"] == ["State change 1", "State change 2"]


@pytest.mark.asyncio
async def test_history_window_caps_recent_narratives():
    class AlwaysSameNodeRuntime(RecordingRuntime):
        async def run_agent(self, profile, task, output_schema):
            outcome = await super().run_agent(profile, task, output_schema)
            return outcome.model_copy(update={"new_impacts": [_impact("north", delay=0)]})

    runtime = AlwaysSameNodeRuntime()
    workflow = WorldTickWorkflow(
        runtime=runtime, repository=InMemoryRAGRepository(), max_ticks=5, history_window=2
    )

    await workflow.run(_packet(_impact("north", delay=0)), "seed-1")

    node = workflow.bus.get_node("region:north")
    assert node.metadata["recent_narratives"] == ["Narrative 4", "Narrative 5"]


@pytest.mark.asyncio
async def test_retrieval_always_includes_world_laws_from_canon():
    repository = InMemoryRAGRepository()
    repository.upsert(
        MemoryFragment(
            id="law-1",
            content="World law Memory Price: every act consumes a true memory.",
            metadata={"kind": "world_law", "world_seed_id": "seed-1"},
        )
    )
    runtime = RecordingRuntime()
    workflow = WorldTickWorkflow(runtime=runtime, repository=repository)

    await workflow.run(_packet(_impact("north", delay=0)), "seed-1")

    retrieved_ids = [fragment["id"] for fragment in runtime.retrieved_memory_per_call[0]]
    assert "law-1" in retrieved_ids


@pytest.mark.asyncio
async def test_retrieval_ranks_relevant_outcomes_above_unrelated_ones():
    repository = InMemoryRAGRepository()
    repository.upsert(
        MemoryFragment(
            id="related",
            content="A previous tick: northern villages faced migration pressure.",
            metadata={"kind": "tick_outcome", "world_seed_id": "seed-1"},
        )
    )
    repository.upsert(
        MemoryFragment(
            id="unrelated",
            content="Maritime trade flourished in southern ports.",
            metadata={"kind": "tick_outcome", "world_seed_id": "seed-1"},
        )
    )
    runtime = RecordingRuntime()
    workflow = WorldTickWorkflow(
        runtime=runtime, repository=repository, retrieval_top_k=1
    )

    await workflow.run(
        _packet(_impact("northern villages", delay=0)),
        "seed-1",
    )

    retrieved_ids = [fragment["id"] for fragment in runtime.retrieved_memory_per_call[0]]
    assert "related" in retrieved_ids
    assert "unrelated" not in retrieved_ids
