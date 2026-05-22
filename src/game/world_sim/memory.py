from __future__ import annotations

from core.schemas import MemoryFragment
from game.world_sim.schemas import NodeTickOutcome


def node_outcome_to_fragments(outcome: NodeTickOutcome, *, world_seed_id: str) -> list[MemoryFragment]:
    change_lines = [f"- {change.change_type}: {change.summary}" for change in outcome.proposed_changes]
    impact_lines = [
        (
            f"- target={impact.target_type}:{impact.target_hint}; "
            f"delay_ticks={impact.delay_ticks}; intensity={impact.intensity}; "
            f"{impact.impact_summary}"
        )
        for impact in outcome.new_impacts
    ]
    sections = [f"Tick {outcome.tick} outcome for node {outcome.node_id}: {outcome.narrative}"]
    if change_lines:
        sections.append("Proposed changes:\n" + "\n".join(change_lines))
    if impact_lines:
        sections.append("New causal impacts:\n" + "\n".join(impact_lines))

    return [
        MemoryFragment(
            content="\n".join(sections),
            metadata={
                "kind": "tick_outcome",
                "world_seed_id": world_seed_id,
                "node_id": outcome.node_id,
                "tick": outcome.tick,
            },
        )
    ]
