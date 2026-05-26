import pytest
from pydantic import ValidationError

from core.schemas import LLMRequest, Message, ThinkingPolicy, TurnInput, TurnResult


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
    with pytest.raises(ValidationError):
        TurnInput(raw_text="", turn_index=0, session_id="s1")


def test_turn_input_requires_non_negative_turn_index():
    with pytest.raises(ValidationError):
        TurnInput(raw_text="hello", turn_index=-1, session_id="s1")


def test_turn_input_accepts_minimal_valid_payload():
    turn_input = TurnInput(raw_text="look around", turn_index=0, session_id="s1")
    assert turn_input.raw_text == "look around"
    assert turn_input.intent_hint is None


def test_turn_result_defaults_guard_retries_to_zero():
    result = TurnResult(turn_id="t1", response_text="ok")
    assert result.guard_retries == 0


def test_turn_result_rejects_negative_guard_retries():
    with pytest.raises(ValidationError):
        TurnResult(turn_id="t1", response_text="ok", guard_retries=-1)


def test_turn_input_rejects_path_traversal_session_id():
    from core.schemas import TurnInput

    with pytest.raises(ValidationError):
        TurnInput(raw_text="x", turn_index=0, session_id="../etc/passwd")
    with pytest.raises(ValidationError):
        TurnInput(raw_text="x", turn_index=0, session_id="s1/s2")
    with pytest.raises(ValidationError):
        TurnInput(raw_text="x", turn_index=0, session_id="s 1")  # 空格也禁
