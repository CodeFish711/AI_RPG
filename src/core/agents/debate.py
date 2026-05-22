from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from core.agents.schemas import AgentProfile, AgentTask, ProposedChange


class DebateTurn(BaseModel):
    agent_id: str
    position: str
    claims: list[str]
    concerns: list[str] = Field(default_factory=list)
    proposed_changes: list[ProposedChange] = Field(default_factory=list)


class DebateSessionResult(BaseModel):
    turns: list[DebateTurn]
    consensus_points: list[str] = Field(default_factory=list)
    unresolved_tensions: list[str] = Field(default_factory=list)


class DebateRuntime(Protocol):
    async def run_agent(self, profile: AgentProfile, task: AgentTask, output_schema: type[DebateTurn]) -> DebateTurn:
        ...


class DebateSession:
    def __init__(self, *, runtime: DebateRuntime):
        self.runtime = runtime

    async def run(self, profiles: list[AgentProfile], task: AgentTask) -> DebateSessionResult:
        if not profiles:
            raise ValueError("DebateSession requires at least one agent")

        turns: list[DebateTurn] = []
        for profile in profiles:
            turns.append(await self.runtime.run_agent(profile, task, DebateTurn))

        return DebateSessionResult(turns=turns)

