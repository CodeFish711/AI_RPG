"""跑 5 个 10 轮 demo,统计 spec §8.F MVP 验收指标。

需要 MIMO_API_KEY env var。每个 demo 用预设玩家输入序列,统计:
- guard_decision 分布(accept / revise / reject / circuit_open)
- 平均 LLM 调用次数 / Turn
- 平均 duration_ms / Turn
- curated_count 总和(实际入库 record 数)

输出 JSON 报告到 stdout 和 data/acceptance_sessions/acceptance_<时间>.json。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from core.agents.runtime import AgentRuntime
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


# 5 个 demo,每个 10 轮玩家输入
DEMOS = [
    {
        "name": "森林探险",
        "inputs": [
            "我在哪里?", "环顾四周", "向前走", "听到声音", "藏起来",
            "看是什么", "搭话", "问名字", "问 NPC 这是哪", "继续探索",
        ],
    },
    {
        "name": "酒馆故事",
        "inputs": [
            "走进酒馆", "找张桌子坐下", "要一杯麦酒", "听旁边人聊天",
            "问酒保最近的传闻", "看墙上的告示", "接一个委托", "出酒馆",
            "想想下一步去哪", "决定去找委托人",
        ],
    },
    {
        "name": "魔法学院",
        "inputs": [
            "我在魔法学院门口", "进入大厅", "找接待员", "报名学习",
            "选魔法系", "上第一节课", "认识同学", "尝试施法",
            "施法失败", "请教老师",
        ],
    },
    {
        "name": "侦探案件",
        "inputs": [
            "我接到一个委托", "委托人是个寡妇", "她丈夫失踪", "我去她家",
            "搜查书房", "发现一封信", "信里提到 NPC Marcus", "去找 Marcus",
            "Marcus 说他不知道", "我察觉他在撒谎",
        ],
    },
    {
        "name": "废墟探索",
        "inputs": [
            "古老废墟入口", "推开石门", "里面很暗", "点燃火把",
            "看到壁画", "壁画讲述古代战争", "继续深入", "发现密室",
            "密室里有个石箱", "打开石箱",
        ],
    },
]


async def run_one_demo(demo: dict, gateway, data_dir: Path) -> dict:
    """跑一个 demo 的 10 轮,返回统计 dict。"""
    runtime = AgentRuntime(gateway=gateway)
    wm = WorldMemory(repository=InMemoryRAGRepository())
    store = TurnStore(data_dir=data_dir)
    loop = TurnLoop(
        narrative_agent=build_narrative_agent(runtime=runtime),
        guard=build_guard(runtime=runtime),
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=NarrativeBeat,
            response_text_field="narration",
            retrieval_kinds=[k.value for k in TextAdventureMemoryKind],
            references_priority_kinds=[
                TextAdventureMemoryKind.WORLD_LAW.value,
                TextAdventureMemoryKind.LOCATION.value,
                TextAdventureMemoryKind.CHARACTER.value,
                TextAdventureMemoryKind.EVENT.value,
            ],
            guard_rules=TEXT_ADVENTURE_GUARD_RULES,
        ),
    )
    curator = TextAdventureCurator(world_memory=wm)

    decisions: Counter[str] = Counter()
    llm_calls: list[int] = []
    durations: list[int] = []
    total_curated = 0
    session_id = f"acc_{demo['name'].replace(' ', '_')}"

    for raw_text in demo["inputs"]:
        try:
            result = await run_turn_with_curator(
                loop=loop, curator=curator, session_id=session_id, raw_text=raw_text,
            )
        except Exception as exc:
            print(f"  [{session_id}] turn failed: {exc}", file=sys.stderr, flush=True)
            decisions["exception"] += 1
            continue
        telemetry = result.turn.metadata.get("telemetry", {})
        decisions[telemetry.get("guard_decision", "unknown")] += 1
        llm_calls.append(int(telemetry.get("llm_call_count", 0)))
        durations.append(int(telemetry.get("duration_ms", 0)))
        total_curated += int(result.turn.metadata.get("curated_count", 0))

    n = max(len(llm_calls), 1)
    return {
        "name": demo["name"],
        "session_id": session_id,
        "turns": len(demo["inputs"]),
        "decisions": dict(decisions),
        "avg_llm_calls_per_turn": sum(llm_calls) / n,
        "avg_duration_ms": sum(durations) / n,
        "total_curated": total_curated,
    }


async def main():
    api_key = os.environ.get("MIMO_API_KEY")
    if not api_key:
        sys.exit("MIMO_API_KEY required")

    gateway = LLMGateway(api_key=api_key)
    data_dir = Path("data/acceptance_sessions")
    data_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for demo in DEMOS:
        print(f"=== 跑 demo: {demo['name']} ===", flush=True)
        stats = await run_one_demo(demo, gateway, data_dir)
        results.append(stats)
        print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)

    # 汇总
    total_decisions: Counter[str] = Counter()
    for r in results:
        for k, v in r["decisions"].items():
            total_decisions[k] += v
    total = sum(total_decisions.values()) or 1
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "demos": results,
        "aggregate": {
            "total_turns": total,
            "guard_accept_rate": total_decisions.get("accept", 0) / total,
            "guard_revise_rate": total_decisions.get("revise", 0) / total,
            "guard_reject_rate": total_decisions.get("reject", 0) / total,
            "circuit_open_rate": total_decisions.get("circuit_open", 0) / total,
        },
    }
    print("\n=== Aggregate ===", flush=True)
    print(json.dumps(summary["aggregate"], indent=2), flush=True)

    report_path = data_dir / f"acceptance_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n报告写入:{report_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
