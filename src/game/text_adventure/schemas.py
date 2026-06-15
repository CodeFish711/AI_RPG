"""text_adventure game 域 schemas — 契约 1+2(NarrativeBeat / MemoryKind)。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TextAdventureMemoryKind(str, Enum):
    """game 域定义的合法 memory kind。core/ 用 kind: str 不限制具体值,
    但 game 内部用这个 Enum 保证一致。"""

    WORLD_LAW = "world_law"
    LOCATION = "location"
    CHARACTER = "character"
    EVENT = "event"
    PLAYER_STATE = "player_state"
    RELATION = "relation"


class NewFact(BaseModel):
    """NarrativeAgent 在 NarrativeBeat 中提名的新事实,Curator 决定是否入 WorldMemory。"""

    kind: TextAdventureMemoryKind
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class NarrativeBeat(BaseModel):
    """NarrativeAgent.run 的 output_schema。response_text_field 指向 narration。"""

    narration: str = Field(min_length=1)
    new_facts: list[NewFact] = Field(default_factory=list)
    follow_up_hooks: list[str] = Field(default_factory=list)
