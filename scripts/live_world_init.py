from __future__ import annotations

import argparse
import asyncio

from core.rag_repository import InMemoryRAGRepository
from main import build_runtime_from_settings, run_world_init_mvp
from core.config import AppSettings


DEFAULT_LIVE_ANSWER = "每一次使用超凡力量都会失去一段真实记忆，越强大的行为失去的记忆越珍贵。"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one live world-initialization pass against the configured LLM.")
    parser.add_argument("--live", action="store_true", help="Actually call the external LLM provider.")
    parser.add_argument("--answer", default=DEFAULT_LIVE_ANSWER, help="Player answer for the world-building question.")
    return parser


def ensure_live_enabled(args: argparse.Namespace) -> None:
    if not args.live:
        raise SystemExit("Refusing to call the live LLM without --live.")


async def async_main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    ensure_live_enabled(args)

    runtime = build_runtime_from_settings(AppSettings())
    repository = InMemoryRAGRepository()
    result = await run_world_init_mvp(
        answer_text=args.answer,
        runtime=runtime,
        repository=repository,
    )

    print(result.workflow_result.world_seed.model_dump_json(indent=2))
    print(result.workflow_result.causal_packet.model_dump_json(indent=2))
    print(f"RAG fragments written: {', '.join(result.fragment_ids)}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

