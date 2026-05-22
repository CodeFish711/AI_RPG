from __future__ import annotations

from core.schemas import MemoryFragment, SimulationNode, TickEvent
from game.world_sim.agents import build_node_agent_profile
from game.world_sim.prompts import build_node_tick_task


def test_node_agent_profile_enables_thinking():
    profile = build_node_agent_profile()

    assert profile.id == "node_simulator"
    assert profile.thinking.type == "enabled"


def test_build_node_tick_task_carries_node_event_and_memory():
    node = SimulationNode(id="region-north", node_type="region")
    event = TickEvent(event_type="causal_impact", source_id="seed-1", target_ids=["region-north"])
    fragments = [MemoryFragment(content="World law: power costs memory.", metadata={"kind": "world_law"})]

    task = build_node_tick_task(node, event, fragments)

    assert task.context["node"]["id"] == "region-north"
    assert task.context["incoming_event"]["event_type"] == "causal_impact"
    assert task.context["retrieved_memory"][0]["content"].startswith("World law")
    assert "NodeTickOutcome" in task.required_output


def test_build_node_tick_task_handles_empty_memory():
    node = SimulationNode(id="region-north", node_type="region")
    event = TickEvent(event_type="causal_impact", source_id="seed-1")

    task = build_node_tick_task(node, event, [])

    assert task.context["retrieved_memory"] == []
