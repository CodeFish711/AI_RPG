from __future__ import annotations

import pytest
from pydantic import ValidationError

from game.world_init.schemas import CausalImpact
from game.world_sim.schemas import NodeTickOutcome, TickRecord, WorldTickResult


def test_node_tick_outcome_defaults_changes_and_impacts_to_empty():
    outcome = NodeTickOutcome(node_id="region-north", tick=2, narrative="A drought begins.")

    assert outcome.proposed_changes == []
    assert outcome.new_impacts == []


def test_node_tick_outcome_requires_non_empty_narrative():
    with pytest.raises(ValidationError):
        NodeTickOutcome(node_id="region-north", tick=1, narrative="")


def test_node_tick_outcome_rejects_negative_tick():
    with pytest.raises(ValidationError):
        NodeTickOutcome(node_id="region-north", tick=-1, narrative="Something.")


def test_world_tick_result_carries_records():
    outcome = NodeTickOutcome(
        node_id="region-north",
        tick=1,
        narrative="Tension rises.",
        new_impacts=[
            CausalImpact(
                target_type="region",
                target_hint="northern villages",
                impact_summary="Migration pressure builds.",
                intensity=0.5,
                delay_ticks=2,
            )
        ],
    )
    result = WorldTickResult(
        world_seed_id="seed-1",
        final_tick=1,
        records=[TickRecord(tick=1, event_ids=["e1"], outcomes=[outcome])],
    )

    assert result.records[0].outcomes[0].new_impacts[0].delay_ticks == 2
