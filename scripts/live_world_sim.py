from __future__ import annotations

import argparse
import asyncio

from core.config import AppSettings
from core.rag_repository import InMemoryRAGRepository
from game.world_sim.tick_workflow import WorldTickWorkflow
from main import build_runtime_from_settings, run_world_init_mvp
from scripts.live_world_init import DEFAULT_LIVE_ANSWER


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run world initialization, then drive the Tick Loop v0 simulation against the LLM."
    )
    parser.add_argument("--live", action="store_true", help="Actually call the external LLM provider.")
    parser.add_argument("--answer", default=DEFAULT_LIVE_ANSWER, help="Player answer for the world-building question.")
    parser.add_argument("--ticks", type=int, default=4, help="Maximum number of simulation ticks to run.")
    return parser


def ensure_live_enabled(args: argparse.Namespace) -> None:
    if not args.live:
        raise SystemExit("Refusing to call the live LLM without --live.")


async def async_main() -> None:
    args = build_parser().parse_args()
    ensure_live_enabled(args)

    runtime = build_runtime_from_settings(AppSettings())
    repository = InMemoryRAGRepository()

    init = await run_world_init_mvp(answer_text=args.answer, runtime=runtime, repository=repository)
    world_seed = init.workflow_result.world_seed
    print(f"World seed {world_seed.id}: {world_seed.premise}\n")

    tick_workflow = WorldTickWorkflow(runtime=runtime, repository=repository, max_ticks=args.ticks)
    result = await tick_workflow.run(init.workflow_result.causal_packet, world_seed.id)

    for record in result.records:
        print(f"--- Tick {record.tick} ---")
        for outcome in record.outcomes:
            print(f"[{outcome.node_id}] {outcome.narrative}")
    print(f"\nSimulation stopped at tick {result.final_tick}; RAG fragments: {repository.count()}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
