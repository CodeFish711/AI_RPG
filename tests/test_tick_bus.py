from __future__ import annotations

import pytest

from core.schemas import SimulationNode, TickEvent
from core.tick_bus import TickBus


def _event(event_type: str = "causal_impact") -> TickEvent:
    return TickEvent(event_type=event_type, source_id="seed-1")


def test_scheduled_event_fires_at_the_target_tick():
    bus = TickBus()
    event = _event()
    bus.schedule_event(event, fire_at_tick=3)

    assert bus.advance() == []
    assert bus.advance() == []
    assert bus.advance() == [event]
    assert bus.current_tick == 3


def test_multiple_events_on_same_tick_keep_insertion_order():
    bus = TickBus()
    first = _event("first")
    second = _event("second")
    bus.schedule_event(first, fire_at_tick=1)
    bus.schedule_event(second, fire_at_tick=1)

    assert bus.advance() == [first, second]


def test_pending_count_decreases_as_events_fire():
    bus = TickBus()
    bus.schedule_event(_event(), fire_at_tick=1)
    bus.schedule_event(_event(), fire_at_tick=2)
    assert bus.pending_count() == 2

    bus.advance()
    assert bus.pending_count() == 1
    bus.advance()
    assert bus.pending_count() == 0


def test_scheduling_into_the_past_raises():
    bus = TickBus()
    bus.advance()
    with pytest.raises(ValueError, match="past"):
        bus.schedule_event(_event(), fire_at_tick=1)
    with pytest.raises(ValueError, match="past"):
        bus.schedule_event(_event(), fire_at_tick=0)


def test_register_and_get_node():
    bus = TickBus()
    node = SimulationNode(id="region-north", node_type="region")
    bus.register_node(node)

    assert bus.get_node("region-north") is node
    assert bus.get_node("missing") is None
