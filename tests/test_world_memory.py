import pytest
from pydantic import ValidationError


def test_memory_record_requires_non_empty_fields():
    from core.world_memory import MemoryRecord

    MemoryRecord(kind="world_law", content="x", source="t:1", session_id="s")
    with pytest.raises(ValidationError):
        MemoryRecord(kind="", content="x", source="t:1", session_id="s")
    with pytest.raises(ValidationError):
        MemoryRecord(kind="k", content="", source="t:1", session_id="s")
    with pytest.raises(ValidationError):
        MemoryRecord(kind="k", content="x", source="", session_id="s")
    with pytest.raises(ValidationError):
        MemoryRecord(kind="k", content="x", source="t:1", session_id="")


def test_memory_record_confidence_in_range():
    from core.world_memory import MemoryRecord

    MemoryRecord(kind="k", content="x", source="s", session_id="x", confidence=0.0)
    MemoryRecord(kind="k", content="x", source="s", session_id="x", confidence=1.0)
    with pytest.raises(ValidationError):
        MemoryRecord(kind="k", content="x", source="s", session_id="x", confidence=1.5)


def test_memory_query_top_k_and_score_bounds():
    from core.world_memory import MemoryQuery

    MemoryQuery(query_text="q", session_id="s", top_k=1)
    MemoryQuery(query_text="q", session_id="s", top_k=50)
    with pytest.raises(ValidationError):
        MemoryQuery(query_text="q", session_id="s", top_k=0)
    with pytest.raises(ValidationError):
        MemoryQuery(query_text="q", session_id="s", top_k=51)
    with pytest.raises(ValidationError):
        MemoryQuery(query_text="q", session_id="s", min_score=-0.1)
    with pytest.raises(ValidationError):
        MemoryQuery(query_text="q", session_id="s", min_score=1.1)


def test_world_memory_upsert_and_query_round_trip():
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import MemoryQuery, MemoryRecord, WorldMemory

    wm = WorldMemory(repository=InMemoryRAGRepository())
    rec = MemoryRecord(
        kind="world_law",
        content="magic requires blood",
        source="turn:0",
        session_id="s1",
    )
    wm.upsert(rec)

    results = wm.query(MemoryQuery(query_text="blood", session_id="s1", top_k=5))
    assert len(results) == 1
    assert results[0].fragment.content == "magic requires blood"


def test_world_memory_query_filters_by_session_id():
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import MemoryQuery, MemoryRecord, WorldMemory

    wm = WorldMemory(repository=InMemoryRAGRepository())
    wm.upsert(MemoryRecord(kind="k", content="alpha", source="t", session_id="s1"))
    wm.upsert(MemoryRecord(kind="k", content="alpha", source="t", session_id="s2"))

    results = wm.query(MemoryQuery(query_text="alpha", session_id="s1", top_k=10))
    assert len(results) == 1
    assert results[0].fragment.metadata["session_id"] == "s1"


def test_world_memory_query_filters_by_kinds():
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import MemoryQuery, MemoryRecord, WorldMemory

    wm = WorldMemory(repository=InMemoryRAGRepository())
    wm.upsert(MemoryRecord(kind="world_law", content="alpha law", source="t", session_id="s"))
    wm.upsert(MemoryRecord(kind="character", content="alpha char", source="t", session_id="s"))

    results = wm.query(
        MemoryQuery(query_text="alpha", session_id="s", kinds=["world_law"], top_k=10)
    )
    assert len(results) == 1
    assert results[0].fragment.metadata["kind"] == "world_law"


def test_world_memory_min_score_threshold():
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import MemoryQuery, MemoryRecord, WorldMemory

    wm = WorldMemory(repository=InMemoryRAGRepository())
    wm.upsert(MemoryRecord(kind="k", content="alpha beta", source="t", session_id="s"))
    wm.upsert(MemoryRecord(kind="k", content="completely unrelated", source="t", session_id="s"))

    # min_score=0.5 时,完全不相关的应被过滤
    results = wm.query(
        MemoryQuery(query_text="alpha beta", session_id="s", min_score=0.5, top_k=10)
    )
    assert len(results) == 1
    assert results[0].score >= 0.5


def test_world_memory_upsert_many_returns_all_ids():
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import MemoryRecord, WorldMemory

    wm = WorldMemory(repository=InMemoryRAGRepository())
    records = [
        MemoryRecord(kind="k", content=f"c{i}", source="t", session_id="s") for i in range(3)
    ]
    ids = wm.upsert_many(records)
    assert len(ids) == 3
    assert ids == [r.id for r in records]
