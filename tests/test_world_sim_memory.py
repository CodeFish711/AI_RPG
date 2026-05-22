from __future__ import annotations

from core.agents.schemas import ProposedChange
from game.world_init.schemas import CausalImpact
from game.world_sim.memory import node_outcome_to_fragments
from game.world_sim.schemas import NodeTickOutcome


def test_node_outcome_produces_one_tick_outcome_fragment():
    outcome = NodeTickOutcome(node_id="region-north", tick=3, narrative="A drought spreads.")

    fragments = node_outcome_to_fragments(outcome, world_seed_id="seed-1")

    assert len(fragments) == 1
    fragment = fragments[0]
    assert fragment.metadata == {
        "kind": "tick_outcome",
        "world_seed_id": "seed-1",
        "node_id": "region-north",
        "tick": 3,
    }
    assert "A drought spreads." in fragment.content


def test_node_outcome_fragment_includes_changes_and_impacts():
    outcome = NodeTickOutcome(
        node_id="region-north",
        tick=3,
        narrative="Unrest grows.",
        proposed_changes=[
            ProposedChange(change_type="state", summary="Food stores drop.", confidence=0.7)
        ],
        new_impacts=[
            CausalImpact(
                target_type="group",
                target_hint="border militia",
                impact_summary="Militia recruitment rises.",
                intensity=0.6,
                delay_ticks=2,
            )
        ],
    )

    content = node_outcome_to_fragments(outcome, world_seed_id="seed-1")[0].content

    assert "Food stores drop." in content
    assert "border militia" in content
