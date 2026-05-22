from __future__ import annotations

import argparse
import contextlib
import io
import json

from core.rag_repository import ChromaRAGRepository
from core.schemas import MemoryFragment


def run_check(*, persist_dir: str = "data/chroma_check") -> dict[str, object]:
    repository = ChromaRAGRepository(persist_dir=persist_dir, collection_name="chroma_check_memory")
    repository.upsert(
        MemoryFragment(
            id="check-world-law",
            content="World law: memory is the price of power.",
            metadata={"kind": "world_law", "world_seed_id": "check-seed"},
        )
    )

    reopened = ChromaRAGRepository(persist_dir=persist_dir, collection_name="chroma_check_memory")
    results = reopened.hybrid_search("memory price", metadata_filter={"kind": "world_law"})
    return {
        "count": reopened.count(),
        "result_count": len(results),
        "first_id": results[0].fragment.id if results else None,
        "first_kind": results[0].fragment.metadata.get("kind") if results else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check local Chroma persistence and retrieval.")
    parser.add_argument("--persist-dir", default="data/chroma_check", help="Directory for Chroma persistence.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = run_check(persist_dir=args.persist_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
