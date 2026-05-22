import pytest
from pydantic import ValidationError

from game.world_init.schemas import (
    CausalImpact,
    CausalImpactPacket,
    PlayerWorldAnswer,
    WorldLaw,
    WorldSeed,
    WorldSeedCandidate,
)


def test_player_world_answer_requires_non_empty_answer():
    answer = PlayerWorldAnswer(
        question_id="magic_cost",
        question_text="这个世界的超凡力量代价是什么？",
        answer_text="每一次使用都会失去一段真实记忆。",
    )

    assert answer.question_id == "magic_cost"

    with pytest.raises(ValidationError):
        PlayerWorldAnswer(question_id="q", question_text="Question", answer_text="")


def test_world_seed_candidate_requires_at_least_one_law_and_tension():
    candidate = WorldSeedCandidate(
        premise="Power is paid for with memory.",
        laws=[
            WorldLaw(
                name="Memory Cost",
                statement="Every extraordinary act removes a true memory.",
                cost="A true memory is lost.",
                limitation="Fabricated memories cannot be used as payment.",
                tags=["memory", "price"],
            )
        ],
        tensions=["Powerful actors become less certain of who they are."],
        open_questions=["Who records lost memories?"],
        source_summary="Derived from the player's answer.",
    )

    assert candidate.laws[0].cost == "A true memory is lost."

    with pytest.raises(ValidationError):
        WorldSeedCandidate(
            premise="No rules yet.",
            laws=[],
            tensions=[],
            open_questions=[],
            source_summary="Invalid",
        )


def test_world_seed_and_causal_packet_validate_impact_bounds():
    law = WorldLaw(name="Bound Price", statement="Power has a price.")
    seed = WorldSeed(
        premise="Power is bounded.",
        laws=[law],
        tensions=["Every choice has a delayed consequence."],
        accepted_sources=["debate:test"],
    )
    packet = CausalImpactPacket(
        source_world_seed_id=seed.id,
        trigger_summary="The accepted law changes future choices.",
        impacts=[
            CausalImpact(
                target_type="rule",
                target_hint="future price escalation",
                impact_summary="Future powerful actions should become more costly.",
                intensity=0.7,
                delay_ticks=3,
            )
        ],
    )

    assert packet.impacts[0].target_type == "rule"

    with pytest.raises(ValidationError):
        CausalImpact(
            target_type="rule",
            target_hint="bad intensity",
            impact_summary="Invalid",
            intensity=2.0,
            delay_ticks=0,
        )

