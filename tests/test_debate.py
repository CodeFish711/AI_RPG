from __future__ import annotations

import pytest

from game.world_init.debate import DebateSession, DebateSessionResult, DebateTurn
from core.agents.schemas import AgentProfile, AgentTask


class FakeRuntime:
    def __init__(self):
        self.calls: list[tuple[AgentProfile, AgentTask, type]] = []

    async def run_agent(self, profile: AgentProfile, task: AgentTask, output_schema: type):
        self.calls.append((profile, task, output_schema))
        return DebateTurn(
            agent_id=profile.id,
            position=f"{profile.name} position",
            claims=[f"{profile.id} claim"],
        )


@pytest.mark.asyncio
async def test_debate_session_runs_each_agent_and_collects_turns():
    runtime = FakeRuntime()
    session = DebateSession(runtime=runtime)
    profiles = [
        AgentProfile(id="expander", name="Expander", role="Expand", objective="Expand consequences"),
        AgentProfile(id="critic", name="Critic", role="Challenge", objective="Find gaps"),
    ]
    task = AgentTask(instruction="Debate the setting", required_output="Return a DebateTurn")

    result = await session.run(profiles, task)

    assert isinstance(result, DebateSessionResult)
    assert [turn.agent_id for turn in result.turns] == ["expander", "critic"]
    assert result.consensus_points == []
    assert result.unresolved_tensions == []
    assert [call[0].id for call in runtime.calls] == ["expander", "critic"]


@pytest.mark.asyncio
async def test_debate_session_requires_at_least_one_agent():
    session = DebateSession(runtime=FakeRuntime())
    task = AgentTask(instruction="Debate the setting", required_output="Return a DebateTurn")

    with pytest.raises(ValueError, match="at least one agent"):
        await session.run([], task)

