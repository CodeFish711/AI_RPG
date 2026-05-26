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
