from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.agents.debate import DebateSession, DebateSessionResult
from core.agents.runtime import AgentRuntime
from game.world_init.agents import (
    build_causality_analyzer_profile,
    build_canon_guard_profile,
    build_debate_profiles,
    build_synthesizer_profile,
)
from game.world_init.prompts import (
    build_causality_task,
    build_debate_task,
    build_guard_task,
    build_revision_task,
    build_synthesis_task,
)
from game.world_init.schemas import CausalImpactPacket, PlayerWorldAnswer, WorldSeed, WorldSeedCandidate


class GuardDecision(BaseModel):
    decision: Literal["accept", "revise", "reject"]
    findings: list[str] = Field(default_factory=list)


class WorldInitResult(BaseModel):
    answer: PlayerWorldAnswer
    debate: DebateSessionResult
    candidate: WorldSeedCandidate
    guard_decision: GuardDecision
    world_seed: WorldSeed
    causal_packet: CausalImpactPacket


class WorldInitWorkflow:
    def __init__(self, *, runtime: AgentRuntime, max_revisions: int = 1):
        self.runtime = runtime
        self.max_revisions = max_revisions
        self.debate_session = DebateSession(runtime=runtime)

    async def run(self, answer: PlayerWorldAnswer) -> WorldInitResult:
        debate = await self.debate_session.run(
            build_debate_profiles(),
            build_debate_task(answer),
        )

        candidate = await self.runtime.run_agent(
            build_synthesizer_profile(),
            build_synthesis_task(answer, debate),
            WorldSeedCandidate,
        )

        guard_decision = await self.runtime.run_agent(
            build_canon_guard_profile(),
            build_guard_task(answer, candidate),
            GuardDecision,
        )

        revisions = 0
        while guard_decision.decision == "revise" and revisions < self.max_revisions:
            revisions += 1
            candidate = await self.runtime.run_agent(
                build_synthesizer_profile(),
                build_revision_task(answer, debate, candidate, guard_decision.findings),
                WorldSeedCandidate,
            )
            guard_decision = await self.runtime.run_agent(
                build_canon_guard_profile(),
                build_guard_task(answer, candidate),
                GuardDecision,
            )

        if guard_decision.decision == "reject":
            raise ValueError(f"World seed candidate rejected: {guard_decision.findings}")
        if guard_decision.decision == "revise":
            raise ValueError(
                f"World seed candidate still needs revision after {revisions} attempt(s): {guard_decision.findings}"
            )

        world_seed = WorldSeed(
            premise=candidate.premise,
            laws=candidate.laws,
            tensions=candidate.tensions,
            accepted_sources=[f"question:{answer.question_id}", "debate:world_init"],
        )

        causal_packet = await self.runtime.run_agent(
            build_causality_analyzer_profile(),
            build_causality_task(answer, world_seed, debate.unresolved_tensions),
            CausalImpactPacket,
        )
        causal_packet = causal_packet.model_copy(update={"source_world_seed_id": world_seed.id})

        return WorldInitResult(
            answer=answer,
            debate=debate,
            candidate=candidate,
            guard_decision=guard_decision,
            world_seed=world_seed,
            causal_packet=causal_packet,
        )
