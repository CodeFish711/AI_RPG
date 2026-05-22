import pytest

from core.rag_repository import ChromaRAGRepository, InMemoryRAGRepository
from core.schemas import MemoryFragment


def test_in_memory_rag_upserts_and_searches_by_metadata():
    repository = InMemoryRAGRepository()
    world_seed_id = repository.upsert(
        MemoryFragment(
            content="World seed: power costs memory.",
            metadata={"kind": "world_seed", "world_seed_id": "seed-1"},
        )
    )
    law_id = repository.upsert(
        MemoryFragment(
            content="World law: every extraordinary act consumes a true memory.",
            metadata={"kind": "world_law", "world_seed_id": "seed-1"},
        )
    )

    assert repository.count() == 2
    assert world_seed_id != law_id

    results = repository.hybrid_search("memory", metadata_filter={"kind": "world_law"})

    assert len(results) == 1
    assert results[0].fragment.id == law_id
    assert results[0].score > 0


def test_in_memory_rag_upsert_replaces_existing_fragment():
    repository = InMemoryRAGRepository()
    repository.upsert(MemoryFragment(id="fixed", content="old content", metadata={"kind": "note"}))
    repository.upsert(MemoryFragment(id="fixed", content="new content", metadata={"kind": "note"}))

    results = repository.hybrid_search("new", top_k=5)

    assert repository.count() == 1
    assert results[0].fragment.content == "new content"


def test_chroma_repository_reports_missing_optional_dependency():
    try:
        import chromadb  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="chromadb"):
            ChromaRAGRepository()
    else:
        pytest.skip("chromadb is installed in this environment")
