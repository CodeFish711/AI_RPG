from __future__ import annotations

from core.agents.schemas import AgentTask
from core.schemas import MemoryFragment, SimulationNode, TickEvent


def build_node_tick_task(
    node: SimulationNode,
    event: TickEvent,
    context_fragments: list[MemoryFragment],
) -> AgentTask:
    return AgentTask(
        instruction=(
            "Advance this simulation node by one tick. The incoming event is a delayed "
            "causal impact that has just landed. Decide what concretely happens to the node, "
            "staying consistent with the retrieved world memory."
        ),
        context={
            "node": node.model_dump(),
            "incoming_event": event.model_dump(mode="json"),
            "retrieved_memory": [fragment.model_dump() for fragment in context_fragments],
        },
        required_output=(
            "Return a NodeTickOutcome JSON object with node_id, tick, narrative, "
            "proposed_changes, and new_impacts. Each new impact must include target_type, "
            "target_hint, impact_summary, intensity, and delay_ticks, and only point at an "
            "abstract target hint — do not assume the target entity already exists."
        ),
    )
