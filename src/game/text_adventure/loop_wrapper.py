"""TurnLoop + Curator 集成 wrapper — 契约 4 接入 core TurnLoop。

extending-the-engine.md 给出的方案:函数式 wrapper。
- status=ok:NarrativeBeat 通过 Curator,records 入 WorldMemory
- status != ok:跳过 Curator(避免污染 WorldMemory)
- turn.metadata["curated_count"] 记录实际入库 record 数(供 MVP 验收统计)

注意:loop.run_turn 内部已经 turn_store.save(turn) 过一次。本 wrapper
在改 turn.metadata 后再 save 一次 — JSONL 会有 2 行重复条目(同 turn id)。
MVP 可接受,Phase E 视情况优化为 save_or_update。
"""

from __future__ import annotations

from core.turn_loop import TurnLoop
from core.turn_store import TurnResult

from game.text_adventure.memory_curator import TextAdventureCurator
from game.text_adventure.schemas import NarrativeBeat


async def run_turn_with_curator(
    *,
    loop: TurnLoop,
    curator: TextAdventureCurator,
    session_id: str,
    raw_text: str,
) -> TurnResult:
    """跑一轮 TurnLoop,accept 时把 NarrativeBeat 交给 Curator 沉淀。"""
    result = await loop.run_turn(session_id=session_id, raw_text=raw_text)

    if result.turn.status != "ok" or not result.turn.narrative_draft:
        result.turn.metadata["curated_count"] = 0
        loop.turn_store.save(result.turn)  # 更新存盘(JSONL 追加,会有重复行)
        return result

    beat = NarrativeBeat.model_validate(result.turn.narrative_draft)
    curated = curator.curate(
        beat=beat,
        session_id=session_id,
        turn_index=result.turn.input.turn_index,
    )
    result.turn.metadata["curated_count"] = len(curated)
    loop.turn_store.save(result.turn)
    return result
