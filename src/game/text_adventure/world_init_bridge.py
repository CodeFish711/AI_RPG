"""Bridge: WorldSeed → MemoryRecord 列表,写入 WorldMemory 给 text_adventure 用。

--with-world-init 时 world_init 的 LLM 结果作为开局事实写入 WorldMemory,
后续 Turn 检索能召回。
"""

from __future__ import annotations

from core.world_memory import MemoryRecord

from game.text_adventure.tokenize import tokenize_chinese
from game.world_init.schemas import WorldSeed


def world_seed_to_memory_records(
    *,
    seed: WorldSeed,
    session_id: str,
) -> list[MemoryRecord]:
    """转 WorldSeed 为 MemoryRecord 列表。

    - 每条 law → kind=world_law(name + statement 拼接)
    - 每条 tension → kind=event
    - 中文 content 经 tokenize_chinese 预处理"""
    records: list[MemoryRecord] = []

    for law in seed.laws:
        content = tokenize_chinese(f"{law.name}: {law.statement}")
        records.append(MemoryRecord(
            kind="world_law",
            content=content,
            source="world_init",
            session_id=session_id,
            confidence=1.0,
        ))

    for tension in seed.tensions:
        records.append(MemoryRecord(
            kind="event",
            content=tokenize_chinese(tension),
            source="world_init",
            session_id=session_id,
            confidence=0.9,
        ))

    return records
