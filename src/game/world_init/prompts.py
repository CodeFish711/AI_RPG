from __future__ import annotations

from core.agents.debate import DebateSessionResult
from core.agents.schemas import AgentTask
from game.world_init.schemas import PlayerWorldAnswer, WorldSeed, WorldSeedCandidate


def build_debate_task(answer: PlayerWorldAnswer) -> AgentTask:
    return AgentTask(
        instruction=(
            "Debate the player's world-building answer and return one structured debate turn. "
            "Focus on durable rules, contradictions, costs, and long-term play pressure."
        ),
        context={"player_answer": answer.model_dump()},
        required_output=(
            "Return a DebateTurn JSON object with agent_id, position, claims, concerns, "
            "and proposed_changes. Do not include prose outside JSON."
        ),
    )


def build_synthesis_task(answer: PlayerWorldAnswer, debate: DebateSessionResult) -> AgentTask:
    return AgentTask(
        instruction=(
            "Synthesize the debate into a coherent world seed candidate. "
            "Preserve the player's answer as canon, choose concrete world laws, and keep future tensions playable."
        ),
        context={
            "player_answer": answer.model_dump(),
            "debate": debate.model_dump(),
        },
        required_output=(
            "Return a WorldSeedCandidate JSON object with premise, laws, tensions, "
            "open_questions, and source_summary. Each law should be specific enough to constrain later simulation."
        ),
    )


def build_guard_task(answer: PlayerWorldAnswer, candidate: WorldSeedCandidate) -> AgentTask:
    return AgentTask(
        instruction=(
            "Judge whether this world seed candidate is internally consistent and respects the player answer. "
            "Accept only if it can seed later simulation without contradicting itself."
        ),
        context={
            "player_answer": answer.model_dump(),
            "candidate": candidate.model_dump(),
        },
        required_output=(
            "Return a GuardDecision JSON object. Use decision='accept' for usable candidates, "
            "decision='revise' for fixable issues, or decision='reject' for contradictions."
        ),
    )


def build_causality_task(answer: PlayerWorldAnswer, world_seed: WorldSeed, debate_tensions: list[str]) -> AgentTask:
    return AgentTask(
        instruction=(
            "Create delayed causal impacts from the accepted world seed. "
            "Impacts are seeds for future simulation, not direct state mutations."
        ),
        context={
            "player_answer": answer.model_dump(),
            "world_seed": world_seed.model_dump(),
            "debate_tensions": debate_tensions,
        },
        required_output=(
            "Return a CausalImpactPacket JSON object. Each impact must include target_type, "
            "target_hint, impact_summary, intensity, and delay_ticks."
        ),
    )

