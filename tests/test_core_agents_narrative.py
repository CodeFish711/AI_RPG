import pytest
from pydantic import BaseModel, Field


class _DemoBeat(BaseModel):
    narration: str = Field(min_length=1)
    new_facts: list[str] = Field(default_factory=list)


def test_narrative_context_serializes_minimal_payload():
    from core.agents.narrative import NarrativeContext
    from core.schemas import TurnInput

    ctx = NarrativeContext(
        player_input=TurnInput(raw_text="look", turn_index=0, session_id="s1"),
        retrieved_memory=[],
    )
    assert ctx.player_input.raw_text == "look"
    assert ctx.extra == {}


@pytest.mark.asyncio
async def test_narrative_agent_runs_with_fake_gateway():
    from core.agents.narrative import NarrativeAgent, NarrativeContext
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from core.schemas import ThinkingPolicy, TurnInput
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(_DemoBeat, _DemoBeat(narration="你看到一片森林。"))

    profile = AgentProfile(
        id="narrator",
        name="NarrativeAgent",
        role="narrator",
        objective="generate next narrative beat",
        thinking=ThinkingPolicy(type="enabled"),
        temperature=0.8,
        max_tokens=4096,
    )
    agent = NarrativeAgent(runtime=AgentRuntime(gateway=gateway), profile=profile)

    result = await agent.run(
        context=NarrativeContext(
            player_input=TurnInput(raw_text="look around", turn_index=0, session_id="s1"),
            retrieved_memory=[],
            extra={"scene_summary": "你在森林深处。"},
        ),
        output_schema=_DemoBeat,
    )

    assert isinstance(result, _DemoBeat)
    assert result.narration == "你看到一片森林。"
    # context 的 raw_text 与 extra 必须进了 user message:
    user_msg = gateway.invocations[0].messages[1]
    assert "look around" in user_msg.content
    assert "scene_summary" in user_msg.content


@pytest.mark.asyncio
async def test_narrative_agent_passes_through_output_schema_choice():
    from core.agents.narrative import NarrativeAgent, NarrativeContext
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from core.schemas import TurnInput
    from tests._fakes import FakeStructuredGateway

    class _AltBeat(BaseModel):
        line: str = Field(min_length=1)

    gateway = FakeStructuredGateway()
    gateway.queue_response(_AltBeat, _AltBeat(line="hi"))

    profile = AgentProfile(id="n", name="N", role="r", objective="o")
    agent = NarrativeAgent(runtime=AgentRuntime(gateway=gateway), profile=profile)

    result = await agent.run(
        context=NarrativeContext(
            player_input=TurnInput(raw_text="x", turn_index=0, session_id="s"),
            retrieved_memory=[],
        ),
        output_schema=_AltBeat,
    )
    assert isinstance(result, _AltBeat)
    assert result.line == "hi"


def test_narrative_context_extra_accepts_nested_dict():
    from core.agents.narrative import NarrativeContext
    from core.schemas import TurnInput

    ctx = NarrativeContext(
        player_input=TurnInput(raw_text="x", turn_index=0, session_id="s1"),
        retrieved_memory=[],
        extra={"scene": {"location": "forest", "characters": ["Aria"]}},
    )
    dumped = ctx.model_dump(mode="json")
    assert dumped["extra"]["scene"]["location"] == "forest"
    assert dumped["extra"]["scene"]["characters"] == ["Aria"]


@pytest.mark.asyncio
async def test_narrative_agent_uses_default_instruction_when_not_overridden():
    from core.agents.narrative import NarrativeAgent, NarrativeContext
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from core.schemas import TurnInput
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(_DemoBeat, _DemoBeat(narration="ok"))

    profile = AgentProfile(id="n", name="N", role="r", objective="o")
    agent = NarrativeAgent(runtime=AgentRuntime(gateway=gateway), profile=profile)
    await agent.run(
        context=NarrativeContext(
            player_input=TurnInput(raw_text="x", turn_index=0, session_id="s"),
            retrieved_memory=[],
        ),
        output_schema=_DemoBeat,
    )

    user_msg = gateway.invocations[0].messages[1]
    # default instruction 中含 "叙事" 字样
    assert "叙事" in user_msg.content


@pytest.mark.asyncio
async def test_narrative_agent_uses_instruction_override_when_provided():
    from core.agents.narrative import NarrativeAgent, NarrativeContext
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from core.schemas import TurnInput
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(_DemoBeat, _DemoBeat(narration="ok"))

    profile = AgentProfile(id="n", name="N", role="r", objective="o")
    custom = "GAME_NARRATIVE_TEMPLATE_xyz999"
    agent = NarrativeAgent(
        runtime=AgentRuntime(gateway=gateway),
        profile=profile,
        instruction=custom,
    )
    await agent.run(
        context=NarrativeContext(
            player_input=TurnInput(raw_text="x", turn_index=0, session_id="s"),
            retrieved_memory=[],
        ),
        output_schema=_DemoBeat,
    )

    user_msg = gateway.invocations[0].messages[1]
    assert "GAME_NARRATIVE_TEMPLATE_xyz999" in user_msg.content
