

def test_build_narrative_agent_injects_text_adventure_instruction():
    from core.agents.runtime import AgentRuntime
    from core.schemas import LLMRequest
    from game.text_adventure.narrative_agent import build_narrative_agent
    from game.text_adventure.prompts import NARRATIVE_INSTRUCTION

    class _NoOpGateway:
        async def complete_and_parse(self, request: LLMRequest, output_schema):
            raise NotImplementedError

    runtime = AgentRuntime(gateway=_NoOpGateway())
    agent = build_narrative_agent(runtime=runtime)
    assert agent.instruction == NARRATIVE_INSTRUCTION


def test_build_narrative_agent_profile_id_is_text_adventure_narrator():
    from core.agents.runtime import AgentRuntime
    from core.schemas import LLMRequest
    from game.text_adventure.narrative_agent import build_narrative_agent

    class _NoOpGateway:
        async def complete_and_parse(self, request: LLMRequest, output_schema):
            raise NotImplementedError

    runtime = AgentRuntime(gateway=_NoOpGateway())
    agent = build_narrative_agent(runtime=runtime)
    assert agent.profile.id == "text_adventure_narrator"


def test_build_guard_injects_text_adventure_instruction():
    from core.agents.runtime import AgentRuntime
    from core.schemas import LLMRequest
    from game.text_adventure.narrative_agent import build_guard
    from game.text_adventure.prompts import GUARD_INSTRUCTION

    class _NoOpGateway:
        async def complete_and_parse(self, request: LLMRequest, output_schema):
            raise NotImplementedError

    runtime = AgentRuntime(gateway=_NoOpGateway())
    guard = build_guard(runtime=runtime)
    assert guard.instruction == GUARD_INSTRUCTION


def test_build_guard_profile_id_is_text_adventure_guard():
    from core.agents.runtime import AgentRuntime
    from core.schemas import LLMRequest
    from game.text_adventure.narrative_agent import build_guard

    class _NoOpGateway:
        async def complete_and_parse(self, request: LLMRequest, output_schema):
            raise NotImplementedError

    runtime = AgentRuntime(gateway=_NoOpGateway())
    guard = build_guard(runtime=runtime)
    assert guard.profile.id == "text_adventure_guard"
