from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Protocol

from core.schemas import MemoryFragment, RAGQueryResult


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
    def __init__(self):
        self._fragments: dict[str, MemoryFragment] = {}

    def upsert(self, fragment: MemoryFragment) -> str:
        self._fragments[fragment.id] = fragment
        return fragment.id

    def upsert_batch(self, fragments: list[MemoryFragment]) -> list[str]:
        return [self.upsert(fragment) for fragment in fragments]

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
        scored = [
            RAGQueryResult(fragment=fragment, score=self._score(query, fragment.content))
            for fragment in candidates
        ]
        scored.sort(key=lambda result: result.score, reverse=True)
        return [result for result in scored if result.score > 0 or not query.strip()][:top_k]

    def count(self) -> int:
        return len(self._fragments)

    @staticmethod
    def _matches_metadata(fragment: MemoryFragment, metadata_filter: dict[str, Any] | None) -> bool:
        if not metadata_filter:
            return True
        return all(fragment.metadata.get(key) == value for key, value in metadata_filter.items())

    @staticmethod
    def _score(query: str, content: str) -> float:
        query_terms = _terms(query)
        if not query_terms:
            return 1.0
        content_terms = _terms(content)
        if not content_terms:
            return 0.0
        query_counts = Counter(query_terms)
        content_counts = Counter(content_terms)
        dot = sum(query_counts[term] * content_counts[term] for term in query_counts)
        query_norm = math.sqrt(sum(value * value for value in query_counts.values()))
        content_norm = math.sqrt(sum(value * value for value in content_counts.values()))
        if query_norm == 0 or content_norm == 0:
            return 0.0
        return dot / (query_norm * content_norm)


class ChromaRAGRepository:
    def __init__(self, *, persist_dir: str = "data/chroma", collection_name: str = "universal_memory"):
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("ChromaRAGRepository requires the optional 'chromadb' dependency.") from exc

        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(collection_name)

    def upsert(self, fragment: MemoryFragment) -> str:
        self._collection.upsert(
            ids=[fragment.id],
            documents=[fragment.content],
            metadatas=[fragment.metadata],
        )
        return fragment.id

    def upsert_batch(self, fragments: list[MemoryFragment]) -> list[str]:
        self._collection.upsert(
            ids=[fragment.id for fragment in fragments],
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
        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
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


def _terms(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.lower())

