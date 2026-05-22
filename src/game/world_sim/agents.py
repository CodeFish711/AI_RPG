from __future__ import annotations

from core.agents.schemas import AgentProfile
from core.schemas import ThinkingPolicy


NODE_TICK_STYLE = [
    "Return only valid JSON.",
    "Stay consistent with retrieved world memory and accepted world laws.",
    "Advance the situation concretely; avoid vague flavor.",
    "New impacts are abstract seeds — never assert that target entities already exist.",
]


def build_node_agent_profile() -> AgentProfile:
    return AgentProfile(
        id="node_simulator",
        name="Node Simulator",
        role="Advance one simulation node by a single tick in response to an incoming event.",
        objective=(
            "Narrate what happens to this node this tick, propose concrete changes, "
            "and optionally seed bounded delayed impacts for future ticks."
        ),
        style_rules=NODE_TICK_STYLE,
        temperature=0.8,
        max_tokens=4096,
        thinking=ThinkingPolicy(type="enabled"),
    )
