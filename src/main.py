from __future__ import annotations

import argparse
import asyncio

from pydantic import BaseModel

from core.agents.runtime import AgentRuntime
from core.config import AppSettings
from core.llm_gateway import LLMGateway
from core.rag_repository import InMemoryRAGRepository, UniversalRAGRepository
from game.world_init.memory import causal_packet_to_fragments, world_seed_to_fragments
from game.world_init.schemas import PlayerWorldAnswer
from game.world_init.workflow import WorldInitResult, WorldInitWorkflow


DEFAULT_WORLD_QUESTION = "这个世界的超凡力量代价是什么？"


class WorldInitMVPResult(BaseModel):
    workflow_result: WorldInitResult
    fragment_ids: list[str]


async def run_world_init_mvp(
    *,
    answer_text: str,
    runtime: AgentRuntime,
    repository: UniversalRAGRepository,
    question_id: str = "world_law_cost",
    question_text: str = DEFAULT_WORLD_QUESTION,
) -> WorldInitMVPResult:
    answer = PlayerWorldAnswer(
        question_id=question_id,
        question_text=question_text,
        answer_text=answer_text,
    )
    workflow_result = await WorldInitWorkflow(runtime=runtime).run(answer)
    fragments = [
        *world_seed_to_fragments(workflow_result.world_seed, question_id=question_id),
        *causal_packet_to_fragments(workflow_result.causal_packet),
    ]
    fragment_ids = repository.upsert_batch(fragments)
    return WorldInitMVPResult(workflow_result=workflow_result, fragment_ids=fragment_ids)


def build_runtime_from_settings(settings: AppSettings) -> AgentRuntime:
    if not settings.mimo_api_key:
        raise SystemExit("MIMO_API_KEY is required. Put it in .env.local or export it before running.")
    gateway = LLMGateway(
        api_key=settings.mimo_api_key,
        base_url=settings.mimo_base_url,
        default_model=settings.mimo_model,
    )
    return AgentRuntime(gateway=gateway)


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="Run the world initialization MVP loop.")
    parser.add_argument("--answer", help="Player answer to the world-building question.")
    args = parser.parse_args()

    answer_text = args.answer or input(f"{DEFAULT_WORLD_QUESTION}\n> ").strip()
    settings = AppSettings()
    runtime = build_runtime_from_settings(settings)
    repository = InMemoryRAGRepository()
    result = await run_world_init_mvp(
        answer_text=answer_text,
        runtime=runtime,
        repository=repository,
    )

    print(result.workflow_result.world_seed.model_dump_json(indent=2))
    print(f"RAG fragments written: {', '.join(result.fragment_ids)}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

