from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.agents.debate import DebateSession, DebateSessionResult
from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentTask
from game.world_init.agents import (
    build_causality_analyzer_profile,
    build_canon_guard_profile,
    build_debate_profiles,
    build_synthesizer_profile,
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
    def __init__(self, *, runtime: AgentRuntime):
        self.runtime = runtime
        self.debate_session = DebateSession(runtime=runtime)

    async def run(self, answer: PlayerWorldAnswer) -> WorldInitResult:
        debate = await self.debate_session.run(
            build_debate_profiles(),
            AgentTask(
                instruction="Debate the player's world-building answer and return one structured debate turn.",
                context={"player_answer": answer.model_dump()},
                required_output="Return a DebateTurn JSON object.",
            ),
        )

        candidate = await self.runtime.run_agent(
            build_synthesizer_profile(),
            AgentTask(
                instruction="Synthesize the debate into a coherent world seed candidate.",
                context={
                    "player_answer": answer.model_dump(),
                    "debate": debate.model_dump(),
                },
                required_output="Return a WorldSeedCandidate JSON object.",
            ),
            WorldSeedCandidate,
        )

        guard_decision = await self.runtime.run_agent(
            build_canon_guard_profile(),
            AgentTask(
                instruction="Judge whether this world seed candidate is internally consistent and respects the player answer.",
                context={
                    "player_answer": answer.model_dump(),
                    "candidate": candidate.model_dump(),
                },
                required_output="Return a GuardDecision JSON object.",
            ),
            GuardDecision,
        )
        if guard_decision.decision == "reject":
            raise ValueError(f"World seed candidate rejected: {guard_decision.findings}")
        if guard_decision.decision == "revise":
            raise ValueError(f"World seed candidate revision requested but not implemented in MVP: {guard_decision.findings}")

        world_seed = WorldSeed(
            premise=candidate.premise,
            laws=candidate.laws,
            tensions=candidate.tensions,
            accepted_sources=[f"question:{answer.question_id}", "debate:world_init"],
        )

        causal_packet = await self.runtime.run_agent(
            build_causality_analyzer_profile(),
            AgentTask(
                instruction="Create delayed causal impacts from the accepted world seed.",
                context={
                    "player_answer": answer.model_dump(),
                    "world_seed": world_seed.model_dump(),
                    "debate_tensions": debate.unresolved_tensions,
                },
                required_output="Return a CausalImpactPacket JSON object.",
            ),
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

