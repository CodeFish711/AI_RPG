from __future__ import annotations

from core.schemas import SimulationNode, TickEvent


class TickBus:
    """Deterministic discrete-event scheduler. Knows only nodes, events, and ticks."""

    def __init__(self):
        self.current_tick: int = 0
        self._nodes: dict[str, SimulationNode] = {}
        self._scheduled: dict[int, list[TickEvent]] = {}

    def register_node(self, node: SimulationNode) -> None:
        self._nodes[node.id] = node

    def get_node(self, node_id: str) -> SimulationNode | None:
        return self._nodes.get(node_id)

    def schedule_event(self, event: TickEvent, fire_at_tick: int) -> None:
        if fire_at_tick <= self.current_tick:
            raise ValueError(
                f"Cannot schedule into the past: fire_at_tick={fire_at_tick} <= current_tick={self.current_tick}"
            )
        self._scheduled.setdefault(fire_at_tick, []).append(event)

    def advance(self) -> list[TickEvent]:
        self.current_tick += 1
        return self._scheduled.pop(self.current_tick, [])

    def pending_count(self) -> int:
        return sum(len(events) for events in self._scheduled.values())
