from __future__ import annotations

import math
import re
from hashlib import sha256
from typing import Any, Protocol

from core.schemas import MemoryFragment, RAGQueryResult


class EmbeddingModel(Protocol):
    @property
    def dimensions(self) -> int:
        ...

    def embed(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


class HashedTextEmbedding:
    def __init__(self, *, dimensions: int = 64) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        return hashed_text_embedding(text, dimensions=self._dimensions)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class SentenceTransformerEmbedding:
    def __init__(
        self,
        *,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str | None = None,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "SentenceTransformerEmbedding requires the optional 'sentence-transformers' "
                "dependency (install via the [rag] extras)."
            ) from exc

        self._model = SentenceTransformer(model_name, device=device)
        self._dimensions = int(self._model.get_sentence_embedding_dimension())

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]


class UniversalRAGRepository(Protocol):
    def upsert(self, fragment: MemoryFragment) -> str:
        ...

    def upsert_batch(self, fragments: list[MemoryFragment]) -> list[str]:
        ...

    def hybrid_search(
        self,
        query: str,
        top_k: int = 8,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RAGQueryResult]:
        ...

    def count(self) -> int:
        ...


class InMemoryRAGRepository:
    def __init__(self, *, embedding_model: EmbeddingModel | None = None) -> None:
        self._fragments: dict[str, MemoryFragment] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._embedding_model: EmbeddingModel = embedding_model or HashedTextEmbedding()

    def upsert(self, fragment: MemoryFragment) -> str:
        self._fragments[fragment.id] = fragment
        self._embeddings[fragment.id] = self._embedding_model.embed(fragment.content)
        return fragment.id

    def upsert_batch(self, fragments: list[MemoryFragment]) -> list[str]:
        if not fragments:
            return []
        vectors = self._embedding_model.embed_batch([fragment.content for fragment in fragments])
        for fragment, vector in zip(fragments, vectors, strict=True):
            self._fragments[fragment.id] = fragment
            self._embeddings[fragment.id] = vector
        return [fragment.id for fragment in fragments]

    def hybrid_search(
        self,
        query: str,
        top_k: int = 8,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RAGQueryResult]:
        candidates = [
            fragment
            for fragment in self._fragments.values()
            if self._matches_metadata(fragment, metadata_filter)
        ]
        if not query.strip():
            return [RAGQueryResult(fragment=fragment, score=1.0) for fragment in candidates[:top_k]]

        query_vector = self._embedding_model.embed(query)
        scored = [
            RAGQueryResult(
                fragment=fragment,
                score=_cosine(query_vector, self._embeddings[fragment.id]),
            )
            for fragment in candidates
        ]
        scored.sort(key=lambda result: result.score, reverse=True)
        return [result for result in scored if result.score > 0][:top_k]

    def count(self) -> int:
        return len(self._fragments)

    @staticmethod
    def _matches_metadata(fragment: MemoryFragment, metadata_filter: dict[str, Any] | None) -> bool:
        if not metadata_filter:
            return True
        return all(fragment.metadata.get(key) == value for key, value in metadata_filter.items())


class ChromaRAGRepository:
    def __init__(
        self,
        *,
        persist_dir: str = "data/chroma",
        collection_name: str = "universal_memory",
        embedding_model: EmbeddingModel | None = None,
    ):
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as exc:
            raise RuntimeError("ChromaRAGRepository requires the optional 'chromadb' dependency.") from exc

        self._embedding_model: EmbeddingModel = embedding_model or HashedTextEmbedding()
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, fragment: MemoryFragment) -> str:
        self._collection.upsert(
            ids=[fragment.id],
            embeddings=[self._embedding_model.embed(fragment.content)],
            documents=[fragment.content],
            metadatas=[fragment.metadata],
        )
        return fragment.id

    def upsert_batch(self, fragments: list[MemoryFragment]) -> list[str]:
        self._collection.upsert(
            ids=[fragment.id for fragment in fragments],
            embeddings=self._embedding_model.embed_batch(
                [fragment.content for fragment in fragments]
            ),
            documents=[fragment.content for fragment in fragments],
            metadatas=[fragment.metadata for fragment in fragments],
        )
        return [fragment.id for fragment in fragments]

    def hybrid_search(
        self,
        query: str,
        top_k: int = 8,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RAGQueryResult]:
        if not query.strip():
            results = self._collection.get(
                where=metadata_filter,
                limit=top_k,
                include=["documents", "metadatas"],
            )
            return self._results_from_get(results)

        count = self.count()
        if count == 0:
            return []

        results = self._collection.query(
            query_embeddings=[self._embedding_model.embed(query)],
            n_results=min(top_k, count),
            where=metadata_filter,
            include=["documents", "metadatas", "distances"],
        )
        fragments: list[RAGQueryResult] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for index, fragment_id in enumerate(ids):
            distance = distances[index] if index < len(distances) else 1.0
            fragments.append(
                RAGQueryResult(
                    fragment=MemoryFragment(
                        id=fragment_id,
                        content=documents[index],
                        metadata=metadatas[index] or {},
                    ),
                    score=max(0.0, 1.0 - float(distance)),
                )
            )
        return fragments

    def count(self) -> int:
        return self._collection.count()

    @staticmethod
    def _results_from_get(results: dict[str, Any]) -> list[RAGQueryResult]:
        ids = results.get("ids", [])
        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])
        return [
            RAGQueryResult(
                fragment=MemoryFragment(
                    id=fragment_id,
                    content=documents[index],
                    metadata=metadatas[index] or {},
                ),
                score=1.0,
            )
            for index, fragment_id in enumerate(ids)
        ]


def _terms(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.lower())


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def hashed_text_embedding(text: str, *, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    terms = _terms(text)
    if not terms:
        vector[0] = 1.0
        return vector

    for term in terms:
        digest = sha256(term.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [value / norm for value in vector]
