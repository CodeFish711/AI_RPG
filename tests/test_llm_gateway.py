from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel

from core.llm_gateway import LLMGateway
from core.schemas import LLMRequest, Message, ThinkingPolicy


class Answer(BaseModel):
    ok: bool


def _response(content: str, *, finish_reason: str = "stop", usage: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {"content": content},
                }
            ],
            "usage": usage or {"completion_tokens": 1, "prompt_tokens": 1, "total_tokens": 2},
        },
    )


def test_complete_sends_enabled_thinking_with_min_token_budget():
    seen_payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.content))
        return _response("pong")

    gateway = LLMGateway(api_key="test-key", transport=httpx.MockTransport(handler))
    request = LLMRequest(
        messages=[Message(role="user", content="ping")],
        max_tokens=128,
        thinking=ThinkingPolicy(type="enabled"),
    )

    response = gateway.run_sync(gateway.complete(request))

    assert response.content == "pong"
    assert seen_payloads[0]["thinking"] == {"type": "enabled"}
    assert seen_payloads[0]["max_tokens"] == 1024


def test_complete_and_parse_retries_with_schema_feedback_and_disabled_thinking():
    seen_payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen_payloads.append(payload)
        if len(seen_payloads) == 1:
            return _response('{"ok": "not a boolean"}')
        return _response('{"ok": true}')

    gateway = LLMGateway(api_key="test-key", transport=httpx.MockTransport(handler), max_retries=1)
    request = LLMRequest(
        messages=[Message(role="user", content="Return JSON")],
        thinking=ThinkingPolicy(type="enabled"),
    )

    parsed = gateway.run_sync(gateway.complete_and_parse(request, Answer))

    assert parsed == Answer(ok=True)
    assert len(seen_payloads) == 2
    assert seen_payloads[1]["thinking"] == {"type": "disabled"}
    assert "校验失败" in seen_payloads[1]["messages"][-1]["content"]


def test_complete_retries_empty_reasoning_response_with_larger_budget():
    seen_payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen_payloads.append(payload)
        if len(seen_payloads) == 1:
            return _response(
                "",
                finish_reason="length",
                usage={
                    "completion_tokens": 1024,
                    "prompt_tokens": 10,
                    "total_tokens": 1034,
                    "completion_tokens_details": {"reasoning_tokens": 1023},
                },
            )
        return _response("finished")

    gateway = LLMGateway(api_key="test-key", transport=httpx.MockTransport(handler), max_retries=1)
    request = LLMRequest(
        messages=[Message(role="user", content="Think deeply")],
        thinking=ThinkingPolicy(type="enabled"),
        max_tokens=1024,
    )

    response = gateway.run_sync(gateway.complete(request))

    assert response.content == "finished"
    assert len(seen_payloads) == 2
    assert seen_payloads[1]["max_tokens"] == 2048

