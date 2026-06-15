from game.world_init.memory import causal_packet_to_fragments, world_seed_to_fragments
from game.world_init.schemas import CausalImpact, CausalImpactPacket, WorldLaw, WorldSeed


def test_world_seed_to_fragments_creates_seed_and_law_memories():
    seed = WorldSeed(
        id="seed-1",
        premise="Power costs memory.",
        laws=[
            WorldLaw(
                id="law-1",
                name="Memory Price",
                statement="Every extraordinary act consumes a true memory.",
                cost="A true memory is lost.",
                limitation="False memories cannot pay the price.",
                tags=["memory"],
            )
        ],
        tensions=["Power erodes identity."],
    )

    fragments = world_seed_to_fragments(seed, question_id="magic_cost")

    assert [fragment.metadata["kind"] for fragment in fragments] == ["world_seed", "world_law"]
    assert fragments[0].metadata["world_seed_id"] == "seed-1"
    assert fragments[1].metadata["world_law_id"] == "law-1"
    assert "Power costs memory" in fragments[0].content
    assert "Memory Price" in fragments[1].content


def test_causal_packet_to_fragments_creates_causal_seed_memory():
    packet = CausalImpactPacket(
        source_world_seed_id="seed-1",
        trigger_summary="Memory price changes future incentives.",
        impacts=[
            CausalImpact(
                target_hint="memory escalation",
                impact_summary="Costs should grow over repeated use.",
                intensity=0.7,
            )
        ],
    )

    fragments = causal_packet_to_fragments(packet)

    assert len(fragments) == 1
    assert fragments[0].metadata["kind"] == "causal_seed"
    assert fragments[0].metadata["world_seed_id"] == "seed-1"
    assert "memory escalation" in fragments[0].content

