import pytest
from pydantic import ValidationError


def test_guard_finding_requires_known_severity():
    from core.agents.guard import GuardFinding

    GuardFinding(severity="info", message="ok")
    GuardFinding(severity="warning", message="ok")
    GuardFinding(severity="error", message="ok")
    with pytest.raises(ValidationError):
        GuardFinding(severity="fatal", message="ok")


def test_guard_decision_revise_requires_revised_payload():
    from core.agents.guard import GuardDecision, GuardFinding

    # accept 不需要 payload
    GuardDecision(decision="accept", findings=[])
    # reject 不需要 payload
    GuardDecision(decision="reject", findings=[GuardFinding(severity="error", message="bad")])

    # revise 必须有 payload — 缺失 raise
    with pytest.raises(ValidationError, match="revised_payload"):
        GuardDecision(
            decision="revise",
            findings=[GuardFinding(severity="warning", message="typo")],
            revised_payload=None,
        )

    # revise 有 payload — pass
    GuardDecision(
        decision="revise",
        findings=[GuardFinding(severity="warning", message="typo")],
        revised_payload={"narration": "fixed"},
    )


def test_reference_item_label_required():
    from core.agents.guard import ReferenceItem

    ReferenceItem(label="world_law:magic_cost", content="魔法需血液")
    with pytest.raises(ValidationError):
        ReferenceItem(label="", content="x")


def test_guard_input_accepts_minimal_payload():
    from core.agents.guard import GuardInput, ReferenceItem

    gi = GuardInput(
        proposal={"narration": "hi"},
        references=[ReferenceItem(label="rule", content="be consistent")],
        rules=["no zero-cost magic"],
        session_id="s1",
    )
    assert gi.proposal == {"narration": "hi"}
    assert len(gi.references) == 1


@pytest.mark.asyncio
async def test_consistency_guard_check_returns_decision_from_runtime():
    from core.agents.guard import ConsistencyGuard, GuardDecision, GuardInput, ReferenceItem
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from core.schemas import ThinkingPolicy
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(
        GuardDecision,
        GuardDecision(decision="accept", findings=[]),
    )

    profile = AgentProfile(
        id="guard",
        name="ConsistencyGuard",
        role="canon check",
        objective="check proposal vs references",
        thinking=ThinkingPolicy(type="enabled"),
        temperature=0.2,
        max_tokens=2048,
    )
    guard = ConsistencyGuard(runtime=AgentRuntime(gateway=gateway), profile=profile)

    decision = await guard.check(
        GuardInput(
            proposal={"narration": "ok"},
            references=[ReferenceItem(label="rule", content="x")],
            rules=["r1"],
            session_id="s1",
        )
    )
    assert decision.decision == "accept"
    assert len(gateway.invocations) == 1
    # references 和 rules 都进了 user message context:
    user_msg = gateway.invocations[0].messages[1]
    assert "rule" in user_msg.content
    assert "r1" in user_msg.content


def test_guard_input_rejects_path_traversal_session_id():
    from core.agents.guard import GuardInput

    with pytest.raises(ValidationError):
        GuardInput(proposal={}, session_id="../etc")
    with pytest.raises(ValidationError):
        GuardInput(proposal={}, session_id="a/b")
    with pytest.raises(ValidationError):
        GuardInput(proposal={}, session_id="a b")


def test_guard_input_accepts_session_id_with_underscores_and_hyphens():
    from core.agents.guard import GuardInput

    # 显式正向用例:含 _ / - / 数字 / 字母混合,验证 pattern 接受
    gi = GuardInput(proposal={}, session_id="s_1-a-B-9")
    assert gi.session_id == "s_1-a-B-9"


def test_guard_input_rejects_trailing_newline_session_id():
    from core.agents.guard import GuardInput

    # \A...\Z pattern 应该拒绝 trailing newline(原 ^...$ 在 default mode 会接受)
    with pytest.raises(ValidationError):
        GuardInput(proposal={}, session_id="abc\n")


@pytest.mark.asyncio
async def test_consistency_guard_uses_default_instruction_when_not_overridden():
    from core.agents.guard import ConsistencyGuard, GuardDecision, GuardInput
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    profile = AgentProfile(id="g", name="G", role="r", objective="o")
    guard = ConsistencyGuard(runtime=AgentRuntime(gateway=gateway), profile=profile)
    await guard.check(GuardInput(proposal={}, session_id="s"))

    user_msg = gateway.invocations[0].messages[1]
    # default instruction 中应该含通用 "一致" 字样(或其他 default 关键词)
    assert "一致" in user_msg.content or "accept" in user_msg.content


@pytest.mark.asyncio
async def test_consistency_guard_uses_instruction_override_when_provided():
    from core.agents.guard import ConsistencyGuard, GuardDecision, GuardInput
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    profile = AgentProfile(id="g", name="G", role="r", objective="o")
    custom_instruction = "GAME_SPECIFIC_GUARD_PROMPT_xyz123"
    guard = ConsistencyGuard(
        runtime=AgentRuntime(gateway=gateway),
        profile=profile,
        instruction=custom_instruction,
    )
    await guard.check(GuardInput(proposal={}, session_id="s"))

    user_msg = gateway.invocations[0].messages[1]
    assert "GAME_SPECIFIC_GUARD_PROMPT_xyz123" in user_msg.content
