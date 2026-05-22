from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class PlayerWorldAnswer(BaseModel):
    question_id: str = Field(min_length=1)
    question_text: str = Field(min_length=1)
    answer_text: str = Field(min_length=1)


class WorldLaw(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    cost: str | None = None
    limitation: str | None = None
    contradiction_risks: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class WorldSeedCandidate(BaseModel):
    premise: str = Field(min_length=1)
    laws: list[WorldLaw] = Field(min_length=1)
    tensions: list[str] = Field(min_length=1)
    open_questions: list[str] = Field(default_factory=list)
    source_summary: str = Field(min_length=1)


class WorldSeed(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    version: int = Field(default=1, ge=1)
    premise: str = Field(min_length=1)
    laws: list[WorldLaw] = Field(min_length=1)
    tensions: list[str] = Field(min_length=1)
    accepted_sources: list[str] = Field(default_factory=list)


class CausalImpact(BaseModel):
    target_type: Literal["node", "group", "region", "rule", "unknown"]
    target_hint: str = Field(min_length=1)
    impact_summary: str = Field(min_length=1)
    intensity: float = Field(ge=0.0, le=1.0)
    delay_ticks: int = Field(ge=0)
    tags: list[str] = Field(default_factory=list)


class CausalImpactPacket(BaseModel):
    source_world_seed_id: str = Field(min_length=1)
    trigger_summary: str = Field(min_length=1)
    impacts: list[CausalImpact] = Field(min_length=1)

