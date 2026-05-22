from core.agents.debate import DebateSessionResult, DebateTurn
from game.world_init.prompts import (
    build_causality_task,
    build_debate_task,
    build_guard_task,
    build_revision_task,
    build_synthesis_task,
)
from game.world_init.schemas import PlayerWorldAnswer, WorldLaw, WorldSeed, WorldSeedCandidate


def _answer() -> PlayerWorldAnswer:
    return PlayerWorldAnswer(
        question_id="magic_cost",
        question_text="这个世界的超凡力量代价是什么？",
        answer_text="每一次使用都会失去一段真实记忆。",
    )


def test_build_debate_task_preserves_player_answer_in_context():
    task = build_debate_task(_answer())

    assert "world-building answer" in task.instruction
    assert task.context["player_answer"]["answer_text"] == "每一次使用都会失去一段真实记忆。"
    assert "DebateTurn" in task.required_output


def test_build_synthesis_task_includes_debate_turns():
    debate = DebateSessionResult(
        turns=[DebateTurn(agent_id="critic", position="Risky", claims=["Memory loss creates identity pressure."])]
    )

    task = build_synthesis_task(_answer(), debate)

    assert "WorldSeedCandidate" in task.required_output
    assert task.context["debate"]["turns"][0]["agent_id"] == "critic"


def test_build_guard_and_causality_tasks_keep_structured_context():
    candidate = WorldSeedCandidate(
        premise="Power costs memory.",
        laws=[WorldLaw(name="Memory Price", statement="Every act consumes a true memory.")],
        tensions=["Power erodes identity."],
        source_summary="Synthesized.",
    )
    seed = WorldSeed(
        id="seed-1",
        premise=candidate.premise,
        laws=candidate.laws,
        tensions=candidate.tensions,
    )

    guard_task = build_guard_task(_answer(), candidate)
    causal_task = build_causality_task(_answer(), seed, ["Power erodes identity."])

    assert "GuardDecision" in guard_task.required_output
    assert guard_task.context["candidate"]["premise"] == "Power costs memory."
    assert "CausalImpactPacket" in causal_task.required_output
    assert causal_task.context["world_seed"]["id"] == "seed-1"


def test_build_revision_task_includes_guard_findings_and_previous_candidate():
    debate = DebateSessionResult(
        turns=[DebateTurn(agent_id="critic", position="Needs specificity", claims=["Define recovery methods."])]
    )
    candidate = WorldSeedCandidate(
        premise="Power costs memory.",
        laws=[WorldLaw(name="Memory Price", statement="Every act consumes a true memory.")],
        tensions=["Power erodes identity."],
        source_summary="Synthesized.",
    )

    task = build_revision_task(_answer(), debate, candidate, ["Define memory tiers objectively."])

    assert "revise" in task.instruction.lower()
    assert task.context["guard_findings"] == ["Define memory tiers objectively."]
    assert task.context["previous_candidate"]["premise"] == "Power costs memory."
