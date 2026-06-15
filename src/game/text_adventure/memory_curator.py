"""text_adventure MemoryCurator — 契约 4。

实施 spec §7.C 四道闸 + 中文分词预处理:
1. Schema 闸(Pydantic 已挡 statement 空 / confidence 越界)
2. Confidence 闸:>=0.8 直入,0.5-0.8 MVP 简化为丢弃(v2 实现 pending),<0.5 丢弃
3. 去重闸:WorldMemory.find_similar 阈值 0.92
4. 冲突闸:MVP 不实现,留 v2

中文分词:statement 含连续中文时用 jieba 分词后再入库,
确保 RAG 检索能命中(参 extending-the-engine.md ⚠ 章节)。
"""

from __future__ import annotations

from core.world_memory import MemoryRecord, WorldMemory

from game.text_adventure.schemas import NarrativeBeat, NewFact
from game.text_adventure.tokenize import tokenize_chinese


_HIGH_CONFIDENCE_THRESHOLD = 0.8
_LOW_CONFIDENCE_THRESHOLD = 0.5
_DEDUP_SIMILARITY_THRESHOLD = 0.92


class TextAdventureCurator:
    """从 NarrativeBeat 提取要进 WorldMemory 的 MemoryRecord。"""

    def __init__(self, *, world_memory: WorldMemory) -> None:
        self.world_memory = world_memory

    def curate(
        self,
        *,
        beat: NarrativeBeat,
        session_id: str,
        turn_index: int,
    ) -> list[MemoryRecord]:
        """对 beat.new_facts 过 4 道闸,过的 fact 转 MemoryRecord 并写入 WorldMemory。
        返回实际入库的 records(供 telemetry / debug)。"""
        accepted: list[MemoryRecord] = []
        for fact in beat.new_facts:
            record = self._curate_fact(fact, session_id=session_id, turn_index=turn_index)
            if record is None:
                continue
            self.world_memory.upsert(record)
            accepted.append(record)
        return accepted

    def _curate_fact(
        self,
        fact: NewFact,
        *,
        session_id: str,
        turn_index: int,
    ) -> MemoryRecord | None:
        # 闸 1:Schema(Pydantic 已挡)

        # 闸 2:Confidence
        if fact.confidence < _HIGH_CONFIDENCE_THRESHOLD:
            # < 0.5:直接丢
            # 0.5-0.8:MVP 简化为丢弃(v2 实现 pending,下轮被引用时正式入库)
            return None

        # 中文分词预处理(在去重检查之前 — 用同样形式比对相似度)
        content = tokenize_chinese(fact.statement)

        # 闸 3:去重
        existing = self.world_memory.find_similar(
            content=content,
            session_id=session_id,
            threshold=_DEDUP_SIMILARITY_THRESHOLD,
        )
        if existing is not None:
            return None

        # 闸 4:冲突(MVP 不实现,直接通过)

        return MemoryRecord(
            kind=fact.kind.value,
            content=content,
            source=f"turn:{turn_index}",
            session_id=session_id,
            confidence=fact.confidence,
        )
