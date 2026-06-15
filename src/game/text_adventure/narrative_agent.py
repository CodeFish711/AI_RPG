"""text_adventure 工厂 — 契约 3。

构造 NarrativeAgent / ConsistencyGuard 并注入 game-specific instruction。
"""

from __future__ import annotations

from core.agents.guard import ConsistencyGuard
from core.agents.narrative import NarrativeAgent
from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile
from core.schemas import ThinkingPolicy

from game.text_adventure.prompts import GUARD_INSTRUCTION, NARRATIVE_INSTRUCTION


def build_narrative_agent(*, runtime: AgentRuntime) -> NarrativeAgent:
    """构造 text_adventure 的 NarrativeAgent。注入 NARRATIVE_INSTRUCTION。"""
    profile = AgentProfile(
        id="text_adventure_narrator",
        name="TextAdventureNarrator",
        role="叙事 agent",
        objective="生成符合 NarrativeBeat schema 的下一段叙事",
        temperature=0.8,
        max_tokens=2048,
        thinking=ThinkingPolicy(type="enabled"),
    )
    return NarrativeAgent(
        runtime=runtime,
        profile=profile,
        instruction=NARRATIVE_INSTRUCTION,
    )


def build_guard(*, runtime: AgentRuntime) -> ConsistencyGuard:
    """构造 text_adventure 的 ConsistencyGuard。注入 GUARD_INSTRUCTION。"""
    profile = AgentProfile(
        id="text_adventure_guard",
        name="TextAdventureGuard",
        role="一致性裁决 agent",
        objective="判定提案是否合规",
        temperature=0.2,
        max_tokens=2048,
        thinking=ThinkingPolicy(type="enabled"),
    )
    return ConsistencyGuard(
        runtime=runtime,
        profile=profile,
        instruction=GUARD_INSTRUCTION,
    )
