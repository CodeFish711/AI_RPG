from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from core.rag_repository import UniversalRAGRepository
from core.schemas import MemoryFragment, RAGQueryResult


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryQuery(BaseModel):
    query_text: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    kinds: list[str] | None = None
    top_k: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class WorldMemory:
    """RAG 之上的语义化记忆门面。core 暴露这个接口,Repository 是实现细节。

    metadata 约定:
      - session_id: 会话隔离
      - kind: game 层自定义类别
      - source: 来源标记(turn:N / world_init / manual)
      - confidence: 0.0-1.0
      - record_id: MemoryRecord.id(便于反查)
    """

    def __init__(self, *, repository: UniversalRAGRepository) -> None:
        self.repository = repository

    def upsert(self, record: MemoryRecord) -> str:
        fragment = self._record_to_fragment(record)
        return self.repository.upsert(fragment)

    def upsert_many(self, records: list[MemoryRecord]) -> list[str]:
        fragments = [self._record_to_fragment(r) for r in records]
        return self.repository.upsert_batch(fragments)

    def query(self, q: MemoryQuery) -> list[RAGQueryResult]:
        # InMemoryRAGRepository.metadata_filter 是精确等值,不支持 IN 多值。
        # 多 kinds 的情况下,先按 session_id 过滤,后在 Python 侧按 kinds 过滤。
        metadata_filter: dict[str, Any] = {"session_id": q.session_id}
        if q.kinds and len(q.kinds) == 1:
            metadata_filter["kind"] = q.kinds[0]

        raw = self.repository.hybrid_search(
            query=q.query_text,
            top_k=q.top_k * 4 if q.kinds and len(q.kinds) > 1 else q.top_k,
            metadata_filter=metadata_filter,
        )

        if q.kinds and len(q.kinds) > 1:
            allowed = set(q.kinds)
            raw = [r for r in raw if r.fragment.metadata.get("kind") in allowed]

        if q.min_score > 0.0:
            raw = [r for r in raw if r.score >= q.min_score]

        return raw[: q.top_k]

    def find_similar(
        self, content: str, session_id: str, threshold: float = 0.92
    ) -> MemoryRecord | None:
        """MVP 用现有 hybrid_search,Phase B 视情况换 embedding。"""
        results = self.repository.hybrid_search(
            query=content,
            top_k=1,
            metadata_filter={"session_id": session_id},
        )
        if not results or results[0].score < threshold:
            return None
        return self._fragment_to_record(results[0].fragment)

    @staticmethod
    def _record_to_fragment(record: MemoryRecord) -> MemoryFragment:
        return MemoryFragment(
            id=record.id,
            content=record.content,
            metadata={
                "kind": record.kind,
                "source": record.source,
                "session_id": record.session_id,
                "confidence": record.confidence,
                "created_at": record.created_at.isoformat(),
                "record_id": record.id,
                **record.metadata,
            },
        )

    @staticmethod
    def _fragment_to_record(fragment: MemoryFragment) -> MemoryRecord:
        meta = fragment.metadata
        return MemoryRecord(
            id=meta.get("record_id", fragment.id),
            kind=meta.get("kind", "unknown"),
            content=fragment.content,
            source=meta.get("source", "unknown"),
            session_id=meta.get("session_id", "unknown"),
            confidence=float(meta.get("confidence", 1.0)),
            created_at=datetime.fromisoformat(meta["created_at"])
            if "created_at" in meta
            else datetime.now(UTC),
            metadata={
                k: v
                for k, v in meta.items()
                if k not in {"kind", "source", "session_id", "confidence", "created_at", "record_id"}
            },
        )
