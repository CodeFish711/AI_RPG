from __future__ import annotations

from core.schemas import MemoryFragment
from game.world_init.schemas import CausalImpactPacket, WorldSeed


def world_seed_to_fragments(seed: WorldSeed, *, question_id: str) -> list[MemoryFragment]:
    fragments = [
        MemoryFragment(
            content=(
                f"World seed {seed.id}: {seed.premise}\n"
                f"Tensions: {'; '.join(seed.tensions)}"
            ),
            metadata={
                "kind": "world_seed",
                "world_seed_id": seed.id,
                "question_id": question_id,
                "version": seed.version,
            },
        )
    ]

    for law in seed.laws:
        fragments.append(
            MemoryFragment(
                content=(
                    f"World law {law.name}: {law.statement}\n"
                    f"Cost: {law.cost or 'unspecified'}\n"
                    f"Limitation: {law.limitation or 'unspecified'}\n"
                    f"Tags: {', '.join(law.tags)}"
                ),
                metadata={
                    "kind": "world_law",
                    "world_seed_id": seed.id,
                    "world_law_id": law.id,
                    "question_id": question_id,
                },
            )
        )

    return fragments


def causal_packet_to_fragments(packet: CausalImpactPacket) -> list[MemoryFragment]:
    impact_lines = [
        (
            f"- target={impact.target_type}:{impact.target_hint}; "
            f"delay_ticks={impact.delay_ticks}; intensity={impact.intensity}; "
            f"{impact.impact_summary}"
        )
        for impact in packet.impacts
    ]
    return [
        MemoryFragment(
            content=(
                f"Causal impact seed for world seed {packet.source_world_seed_id}: "
                f"{packet.trigger_summary}\n"
                + "\n".join(impact_lines)
            ),
            metadata={
                "kind": "causal_seed",
                "world_seed_id": packet.source_world_seed_id,
            },
        )
    ]

