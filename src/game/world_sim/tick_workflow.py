from __future__ import annotations

import re

from core.agents.runtime import AgentRuntime
from core.rag_repository import UniversalRAGRepository
from core.schemas import SimulationNode, TickEvent
from core.tick_bus import TickBus
from game.world_init.schemas import CausalImpact, CausalImpactPacket
from game.world_sim.agents import build_node_agent_profile
from game.world_sim.memory import node_outcome_to_fragments
from game.world_sim.prompts import build_node_tick_task
from game.world_sim.schemas import NodeTickOutcome, TickRecord, WorldTickResult


def _slug(text: str) -> str:
    slug = re.sub(r"[^\w]+", "-", text.strip().lower()).strip("-")
    return slug or "node"


class WorldTickWorkflow:
    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        repository: UniversalRAGRepository,
        bus: TickBus | None = None,
        max_ticks: int = 8,
    ):
        self.runtime = runtime
        self.repository = repository
        self.bus = bus or TickBus()
        self.max_ticks = max_ticks

    def bootstrap(self, causal_packet: CausalImpactPacket, world_seed_id: str) -> None:
        for impact in causal_packet.impacts:
            self._schedule_impact(impact, world_seed_id)

    async def run(self, causal_packet: CausalImpactPacket, world_seed_id: str) -> WorldTickResult:
        self.bootstrap(causal_packet, world_seed_id)
        profile = build_node_agent_profile()
        records: list[TickRecord] = []

        for _ in range(self.max_ticks):
            if self.bus.pending_count() == 0:
                break
            due = self.bus.advance()
            if not due:
                continue

            outcomes: list[NodeTickOutcome] = []
            for event in due:
                outcome = await self._run_node_tick(event, profile, world_seed_id)
                self.repository.upsert_batch(node_outcome_to_fragments(outcome, world_seed_id=world_seed_id))
                for impact in outcome.new_impacts:
                    self._schedule_impact(impact, world_seed_id)
                outcomes.append(outcome)

            records.append(
                TickRecord(tick=self.bus.current_tick, event_ids=[event.id for event in due], outcomes=outcomes)
            )

        return WorldTickResult(world_seed_id=world_seed_id, final_tick=self.bus.current_tick, records=records)

    async def _run_node_tick(self, event: TickEvent, profile, world_seed_id: str) -> NodeTickOutcome:
        node = self.bus.get_node(event.target_ids[0])
        context = self.repository.hybrid_search("", metadata_filter={"world_seed_id": world_seed_id})
        task = build_node_tick_task(node, event, [result.fragment for result in context])
        return await self.runtime.run_agent(profile, task, NodeTickOutcome)

    def _schedule_impact(self, impact: CausalImpact, world_seed_id: str) -> None:
        node = self._node_from_impact(impact)
        if self.bus.get_node(node.id) is None:
            self.bus.register_node(node)
        event = TickEvent(
            event_type="causal_impact",
            source_id=world_seed_id,
            target_ids=[node.id],
            payload=impact.model_dump(),
        )
        self.bus.schedule_event(event, self.bus.current_tick + 1 + impact.delay_ticks)

    @staticmethod
    def _node_from_impact(impact: CausalImpact) -> SimulationNode:
        return SimulationNode(id=f"{impact.target_type}:{_slug(impact.target_hint)}", node_type=impact.target_type)
