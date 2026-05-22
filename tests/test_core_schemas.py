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

