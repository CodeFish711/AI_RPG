from __future__ import annotations

import pytest
from pydantic import BaseModel

from core.agents.debate import DebateTurn
from core.agents.schemas import AgentProfile, AgentTask
from game.world_init.schemas import (
    CausalImpact,
    CausalImpactPacket,
    PlayerWorldAnswer,
    WorldLaw,
    WorldSeedCandidate,
)
from game.world_init.workflow import GuardDecision, WorldInitWorkflow


class FakeRuntime:
    def __init__(self):
        self.calls: list[tuple[str, str, type[BaseModel]]] = []

    async def run_agent(self, profile: AgentProfile, task: AgentTask, output_schema: type[BaseModel]) -> BaseModel:
        self.calls.append((profile.id, task.instruction, output_schema))
        if output_schema is DebateTurn:
            return DebateTurn(
                agent_id=profile.id,
                position=f"{profile.id} position",
                claims=[f"{profile.id} claim"],
            )
        if output_schema is WorldSeedCandidate:
            return WorldSeedCandidate(
                premise="Power costs memory.",
                laws=[
                    WorldLaw(
                        name="Memory Price",
                        statement="Every extraordinary act consumes a true memory.",
                        cost="A true memory is lost.",
                        limitation="False memories cannot pay the price.",
                    )
                ],
                tensions=["Power erodes identity."],
                open_questions=["Who remembers what was lost?"],
                source_summary="Synthesized from debate turns.",
            )
        if output_schema is GuardDecision:
            return GuardDecision(decision="accept", findings=[])
        if output_schema is CausalImpactPacket:
            return CausalImpactPacket(
                source_world_seed_id="pending",
                trigger_summary="Memory price changes future incentives.",
                impacts=[
                    CausalImpact(
                        target_type="rule",
                        target_hint="memory cost escalation",
                        impact_summary="Repeated use should create delayed identity pressure.",
                        intensity=0.8,
                        delay_ticks=2,
                    )
                ],
            )
        raise AssertionError(f"Unexpected schema: {output_schema}")


@pytest.mark.asyncio
async def test_world_init_workflow_runs_debate_synthesis_guard_and_causality():
    runtime = FakeRuntime()
    workflow = WorldInitWorkflow(runtime=runtime)
    answer = PlayerWorldAnswer(
        question_id="magic_cost",
        question_text="这个世界的超凡力量代价是什么？",
        answer_text="每一次使用都会失去一段真实记忆。",
    )

    result = await workflow.run(answer)

    assert result.world_seed.premise == "Power costs memory."
    assert result.world_seed.laws[0].name == "Memory Price"
    assert result.causal_packet.source_world_seed_id == result.world_seed.id
    assert [turn.agent_id for turn in result.debate.turns] == ["expander", "critic", "drama_designer"]
    assert [call[0] for call in runtime.calls] == [
        "expander",
        "critic",
        "drama_designer",
        "synthesizer",
        "canon_guard",
        "causality_analyzer",
    ]


@pytest.mark.asyncio
async def test_world_init_workflow_revises_candidate_when_guard_requests_revision():
    class RevisingRuntime(FakeRuntime):
        def __init__(self):
            super().__init__()
            self.guard_calls = 0

        async def run_agent(self, profile: AgentProfile, task: AgentTask, output_schema: type[BaseModel]) -> BaseModel:
            if output_schema is GuardDecision:
                self.calls.append((profile.id, task.instruction, output_schema))
                self.guard_calls += 1
                if self.guard_calls == 1:
                    return GuardDecision(decision="revise", findings=["Define memory tiers objectively."])
                return GuardDecision(decision="accept", findings=[])
            return await super().run_agent(profile, task, output_schema)

    runtime = RevisingRuntime()
    workflow = WorldInitWorkflow(runtime=runtime)
    answer = PlayerWorldAnswer(question_id="q", question_text="Question", answer_text="Answer")

    result = await workflow.run(answer)

    assert result.guard_decision.decision == "accept"
    assert [call[0] for call in runtime.calls] == [
        "expander",
        "critic",
        "drama_designer",
        "synthesizer",
        "canon_guard",
        "synthesizer",
        "canon_guard",
        "causality_analyzer",
    ]


@pytest.mark.asyncio
async def test_world_init_workflow_raises_when_revision_budget_is_exhausted():
    class AlwaysRevisingRuntime(FakeRuntime):
        async def run_agent(self, profile: AgentProfile, task: AgentTask, output_schema: type[BaseModel]) -> BaseModel:
            if output_schema is GuardDecision:
                return GuardDecision(decision="revise", findings=["Still ambiguous."])
            return await super().run_agent(profile, task, output_schema)

    workflow = WorldInitWorkflow(runtime=AlwaysRevisingRuntime(), max_revisions=2)
    answer = PlayerWorldAnswer(question_id="q", question_text="Question", answer_text="Answer")

    with pytest.raises(ValueError, match="still needs revision after 2"):
        await workflow.run(answer)


@pytest.mark.asyncio
async def test_world_init_workflow_raises_when_guard_rejects_candidate():
    class RejectingRuntime(FakeRuntime):
        async def run_agent(self, profile: AgentProfile, task: AgentTask, output_schema: type[BaseModel]) -> BaseModel:
            if output_schema is GuardDecision:
                return GuardDecision(decision="reject", findings=["Candidate contradicts answer."])
            return await super().run_agent(profile, task, output_schema)

    workflow = WorldInitWorkflow(runtime=RejectingRuntime())
    answer = PlayerWorldAnswer(question_id="q", question_text="Question", answer_text="Answer")

    with pytest.raises(ValueError, match="rejected"):
        await workflow.run(answer)

