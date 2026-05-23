import math
import pytest

from core.rag_repository import (
    ChromaRAGRepository,
    HashedTextEmbedding,
    InMemoryRAGRepository,
    SentenceTransformerEmbedding,
    hashed_text_embedding,
)
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


def test_in_memory_rag_uses_injected_embedding_model():
    class StubEmbedding:
        def __init__(self) -> None:
            self.embed_calls: list[str] = []

        @property
        def dimensions(self) -> int:
            return 2

        def embed(self, text: str) -> list[float]:
            self.embed_calls.append(text)
            return [1.0, 0.0] if "alpha" in text.lower() else [0.0, 1.0]

        def embed_batch(self, texts: list[str]) -> list[list[float]]:
            return [self.embed(text) for text in texts]

    stub = StubEmbedding()
    repository = InMemoryRAGRepository(embedding_model=stub)
    alpha_id = repository.upsert(MemoryFragment(content="alpha fragment", metadata={}))
    beta_id = repository.upsert(MemoryFragment(content="beta fragment", metadata={}))

    results = repository.hybrid_search("alpha query", top_k=2)

    assert [result.fragment.id for result in results][0] == alpha_id
    assert all(call in {"alpha fragment", "beta fragment", "alpha query"} for call in stub.embed_calls)
    assert any(result.fragment.id == beta_id and result.score == 0.0 for result in results) is False


def test_in_memory_rag_empty_query_returns_all_candidates():
    repository = InMemoryRAGRepository()
    repository.upsert(MemoryFragment(content="alpha", metadata={"kind": "x"}))
    repository.upsert(MemoryFragment(content="beta", metadata={"kind": "x"}))

    results = repository.hybrid_search("", top_k=10)

    assert len(results) == 2
    assert all(result.score == 1.0 for result in results)


def test_chroma_repository_reports_missing_optional_dependency():
    try:
        import chromadb  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="chromadb"):
            ChromaRAGRepository()
    else:
        pytest.skip("chromadb is installed in this environment")


def test_hashed_text_embedding_is_deterministic_and_normalized():
    first = hashed_text_embedding("memory price", dimensions=16)
    second = hashed_text_embedding("memory price", dimensions=16)

    assert first == second
    assert len(first) == 16
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_hashed_text_embedding_class_wraps_function():
    model = HashedTextEmbedding(dimensions=16)
    assert model.dimensions == 16
    assert model.embed("memory price") == hashed_text_embedding("memory price", dimensions=16)
    batch = model.embed_batch(["alpha", "beta"])
    assert len(batch) == 2 and all(len(vector) == 16 for vector in batch)


def test_sentence_transformer_embedding_reports_missing_optional_dependency():
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="sentence-transformers"):
            SentenceTransformerEmbedding()
    else:
        pytest.skip("sentence-transformers is installed in this environment")
