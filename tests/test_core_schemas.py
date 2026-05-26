import pytest
from pydantic import ValidationError

from core.schemas import LLMRequest, Message, ThinkingPolicy


def test_llm_request_uses_mimo_defaults():
    request = LLMRequest(messages=[Message(role="user", content="ping")])

    assert request.model == "mimo-v2.5-pro"
    assert request.max_tokens == 4096
    assert request.thinking.type == "auto"


def test_thinking_policy_only_accepts_supported_modes():
    assert ThinkingPolicy(type="enabled").type == "enabled"
    assert ThinkingPolicy(type="disabled").type == "disabled"

    with pytest.raises(ValidationError):
        ThinkingPolicy(type="verbose")


def test_message_rejects_invalid_roles():
    with pytest.raises(ValidationError):
        Message(role="tool", content="not supported yet")


def test_turn_input_requires_non_empty_raw_text():
    from core.schemas import TurnInput

    with pytest.raises(ValidationError):
        TurnInput(raw_text="", turn_index=0, session_id="s1")


def test_turn_input_requires_non_negative_turn_index():
    from core.schemas import TurnInput

    with pytest.raises(ValidationError):
        TurnInput(raw_text="hello", turn_index=-1, session_id="s1")


def test_turn_input_accepts_minimal_valid_payload():
    from core.schemas import TurnInput

    turn_input = TurnInput(raw_text="look around", turn_index=0, session_id="s1")
    assert turn_input.raw_text == "look around"
    assert turn_input.intent_hint is None


def test_turn_result_defaults_guard_retries_to_zero():
    from core.schemas import TurnResult

    # 不构造完整 TurnResult,只验证 schema 含 guard_retries 字段:
    assert "guard_retries" in TurnResult.model_fields
    assert TurnResult.model_fields["guard_retries"].default == 0

