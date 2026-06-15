"""text_adventure CLI app — 契约 5。

入口:`python -m game.text_adventure.app` 或 `python -m game.text_adventure.app --resume <id>`。
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Callable

from core.agents.runtime import AgentRuntime
from core.config import AppSettings
from core.llm_gateway import LLMGateway
from core.rag_repository import InMemoryRAGRepository
from core.turn_loop import TurnLoop, TurnLoopConfig
from core.turn_store import TurnStore
from core.world_memory import WorldMemory

from game.text_adventure.guard_rules import TEXT_ADVENTURE_GUARD_RULES
from game.text_adventure.loop_wrapper import run_turn_with_curator
from game.text_adventure.memory_curator import TextAdventureCurator
from game.text_adventure.narrative_agent import build_guard, build_narrative_agent
from game.text_adventure.schemas import NarrativeBeat, TextAdventureMemoryKind


def resolve_session(
    *,
    turn_store: TurnStore,
    resume: str | None,
    new_session: str | None,
) -> str:
    """解析 session_id:--resume / --session / default。
    --resume 时校验 id 必须在 list_sessions 中存在。"""
    if resume is not None:
        available = turn_store.list_sessions()
        if resume not in available:
            raise ValueError(
                f"Session not found: {resume!r}. Available: {available[:5]}"
            )
        return resume
    return new_session or "default"


async def run_session(
    *,
    session_id: str,
    data_dir: Path,
    gateway,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    """跑一轮交互式 session。input_fn / output_fn 可注入便于测试。"""
    runtime = AgentRuntime(gateway=gateway)
    wm = WorldMemory(repository=InMemoryRAGRepository())
    turn_store = TurnStore(data_dir=data_dir)
    loop = TurnLoop(
        narrative_agent=build_narrative_agent(runtime=runtime),
        guard=build_guard(runtime=runtime),
        world_memory=wm,
        turn_store=turn_store,
        config=TurnLoopConfig(
            narrative_output_schema=NarrativeBeat,
            response_text_field="narration",
            retrieval_kinds=[k.value for k in TextAdventureMemoryKind],
            references_priority_kinds=[
                TextAdventureMemoryKind.WORLD_LAW.value,
                TextAdventureMemoryKind.LOCATION.value,
                TextAdventureMemoryKind.CHARACTER.value,
                TextAdventureMemoryKind.EVENT.value,
                TextAdventureMemoryKind.PLAYER_STATE.value,
            ],
            guard_rules=TEXT_ADVENTURE_GUARD_RULES,
        ),
    )
    curator = TextAdventureCurator(world_memory=wm)

    output_fn(f"=== Session: {session_id} ===")
    output_fn("输入指令(或 /quit 退出):")

    while True:
        try:
            user_input = input_fn("> ").strip()
        except (EOFError, KeyboardInterrupt, StopIteration):
            break
        if not user_input:
            continue
        if user_input == "/quit":
            break
        result = await run_turn_with_curator(
            loop=loop, curator=curator, session_id=session_id, raw_text=user_input,
        )
        output_fn(result.response_text)


def _build_gateway_from_env() -> LLMGateway:
    settings = AppSettings()
    if not settings.mimo_api_key:
        raise SystemExit(
            "MIMO_API_KEY is required. 在 .env.local 设置或 export 后再跑。"
        )
    return LLMGateway(
        api_key=settings.mimo_api_key,
        base_url=settings.mimo_base_url,
        default_model=settings.mimo_model,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="text_adventure")
    parser.add_argument("--session", help="新 session id(默认 'default')")
    parser.add_argument("--resume", help="续接已有 session_id")
    parser.add_argument("--data-dir", default="data/sessions", help="JSONL 存盘目录")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    turn_store = TurnStore(data_dir=data_dir)
    try:
        session_id = resolve_session(
            turn_store=turn_store, resume=args.resume, new_session=args.session,
        )
    except ValueError as exc:
        raise SystemExit(str(exc))

    gateway = _build_gateway_from_env()
    asyncio.run(run_session(
        session_id=session_id, data_dir=data_dir, gateway=gateway,
    ))


if __name__ == "__main__":
    main()
