import pytest

pytest.importorskip("chromadb")

from core.rag_repository import ChromaRAGRepository
from core.schemas import MemoryFragment


def test_chroma_repository_persists_and_searches_fragments(tmp_path):
    repository = ChromaRAGRepository(persist_dir=str(tmp_path), collection_name="test_memory")
    fragment_id = repository.upsert(
        MemoryFragment(
            content="World law: memory is the price of power.",
            metadata={"kind": "world_law", "world_seed_id": "seed-1"},
        )
    )

    reopened = ChromaRAGRepository(persist_dir=str(tmp_path), collection_name="test_memory")
    results = reopened.hybrid_search("memory price", metadata_filter={"kind": "world_law"})

    assert reopened.count() == 1
    assert results[0].fragment.id == fragment_id
    assert results[0].fragment.metadata["world_seed_id"] == "seed-1"


def test_chroma_repository_returns_empty_search_results_for_empty_collection(tmp_path):
    repository = ChromaRAGRepository(persist_dir=str(tmp_path), collection_name="empty_memory")

    assert repository.hybrid_search("memory") == []
