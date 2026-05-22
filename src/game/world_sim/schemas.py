from __future__ import annotations

from pydantic import BaseModel, Field

from core.agents.schemas import ProposedChange
from game.world_init.schemas import CausalImpact


class NodeTickOutcome(BaseModel):
    node_id: str = Field(min_length=1)
    tick: int = Field(ge=0)
    narrative: str = Field(min_length=1)
    proposed_changes: list[ProposedChange] = Field(default_factory=list)
    new_impacts: list[CausalImpact] = Field(default_factory=list)


class TickRecord(BaseModel):
    tick: int = Field(ge=0)
    event_ids: list[str] = Field(default_factory=list)
    outcomes: list[NodeTickOutcome] = Field(default_factory=list)


class WorldTickResult(BaseModel):
    world_seed_id: str = Field(min_length=1)
    final_tick: int = Field(ge=0)
    records: list[TickRecord] = Field(default_factory=list)
