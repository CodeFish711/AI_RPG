from __future__ import annotations

from core.agents.schemas import AgentProfile
from core.schemas import ThinkingPolicy


WORLD_BUILDING_STYLE = [
    "Return only valid JSON.",
    "Respect the player's answer as primary canon.",
    "Prefer specific constraints over vague flavor.",
]


def _profile(agent_id: str, name: str, role: str, objective: str) -> AgentProfile:
    return AgentProfile(
        id=agent_id,
        name=name,
        role=role,
        objective=objective,
        style_rules=WORLD_BUILDING_STYLE,
        temperature=0.8,
        max_tokens=4096,
        thinking=ThinkingPolicy(type="enabled"),
    )


def build_debate_profiles() -> list[AgentProfile]:
    return [
        _profile(
            "expander",
            "Expander",
            "Expand the consequences of the player's world-building answer.",
            "Find generative implications, hidden pressures, and useful creative affordances.",
        ),
        _profile(
            "critic",
            "Critic",
            "Challenge weak assumptions and logical gaps.",
            "Identify contradictions, missing costs, loopholes, and unstable rules.",
        ),
        _profile(
            "drama_designer",
            "Drama Designer",
            "Extract durable dramatic pressure from the answer.",
            "Turn the premise into tensions that can drive long-running play.",
        ),
    ]


def build_synthesizer_profile() -> AgentProfile:
    return _profile(
        "synthesizer",
        "Synthesizer",
        "Merge debate turns into one coherent world seed candidate.",
        "Produce a compact, structured seed with laws, tensions, and open questions.",
    )


def build_canon_guard_profile() -> AgentProfile:
    return _profile(
        "canon_guard",
        "Canon Guard",
        "Judge whether a world seed candidate is internally consistent.",
        "Accept good candidates, request targeted revision for weak ones, and reject unsafe contradictions.",
    )


def build_causality_analyzer_profile() -> AgentProfile:
    return _profile(
        "causality_analyzer",
        "Causality Analyzer",
        "Translate accepted world laws into delayed impact packets.",
        "Generate bounded butterfly-effect seeds without directly mutating state.",
    )

