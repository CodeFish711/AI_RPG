from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
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


# === Phase B Task 3: Circuit Breaker ===


def _circuit_fail_transport() -> httpx.MockTransport:
    """Always returns HTTP 503,模拟 provider 故障。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "service unavailable"})

    return httpx.MockTransport(handler)


def _circuit_success_transport(content: str = '{"answer": "ok"}') -> httpx.MockTransport:
    """Always returns 200 OK with given content。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"completion_tokens": 5},
            },
        )

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_gateway_circuit_opens_after_threshold_consecutive_failures():
    """连续 5 次失败 → 第 6 次调用直接抛 GatewayCircuitOpen,不再发请求。"""
    from core.llm_gateway import GatewayCircuitOpen, LLMGateway, LLMGatewayError

    gateway = LLMGateway(
        api_key="test",
        max_retries=0,
        failure_threshold=5,
        circuit_window_seconds=900,
        transport=_circuit_fail_transport(),
    )
    request = LLMRequest(messages=[Message(role="user", content="ping")])

    # 前 5 次都失败(LLMGatewayError),还未熔断
    for _ in range(5):
        with pytest.raises(LLMGatewayError) as exc_info:
            await gateway.complete(request)
        assert not isinstance(exc_info.value, GatewayCircuitOpen)

    # 第 6 次:熔断已打开,直接抛 GatewayCircuitOpen
    with pytest.raises(GatewayCircuitOpen):
        await gateway.complete(request)


@pytest.mark.asyncio
async def test_gateway_circuit_resets_consecutive_failures_after_success():
    """成功一次 → reset consecutive_failures counter。"""
    from core.llm_gateway import LLMGateway, LLMGatewayError

    gateway = LLMGateway(
        api_key="test",
        max_retries=0,
        failure_threshold=5,
        circuit_window_seconds=900,
        transport=_circuit_fail_transport(),
    )
    request = LLMRequest(messages=[Message(role="user", content="ping")])
    for _ in range(4):
        with pytest.raises(LLMGatewayError):
            await gateway.complete(request)
    assert gateway.consecutive_failures == 4

    # 切换 transport 到 success
    gateway._transport = _circuit_success_transport()
    response = await gateway.complete(request)
    assert response.content
    # 成功后 counter 必须 reset
    assert gateway.consecutive_failures == 0


@pytest.mark.asyncio
async def test_gateway_circuit_closes_after_window_expires():
    """熔断打开后,window 时间过去 → 下次调用恢复尝试。"""
    import time

    from core.llm_gateway import GatewayCircuitOpen, LLMGateway, LLMGatewayError

    gateway = LLMGateway(
        api_key="test",
        max_retries=0,
        failure_threshold=2,
        circuit_window_seconds=60,
        transport=_circuit_fail_transport(),
    )
    request = LLMRequest(messages=[Message(role="user", content="ping")])

    for i in range(2):
        with pytest.raises(LLMGatewayError):
            await gateway.complete(request)
    with pytest.raises(GatewayCircuitOpen):
        await gateway.complete(request)

    # 把 circuit_open_until 倒回过去(monotonic float)
    gateway.circuit_open_until = time.monotonic() - 1.0

    with pytest.raises(LLMGatewayError) as exc_info:
        await gateway.complete(request)
    assert not isinstance(exc_info.value, GatewayCircuitOpen)


@pytest.mark.asyncio
async def test_gateway_circuit_default_threshold_and_window():
    """默认值检查:failure_threshold=5, circuit_window_seconds=900。"""
    from core.llm_gateway import LLMGateway

    gateway = LLMGateway(api_key="test")
    assert gateway.failure_threshold == 5
    assert gateway.circuit_window_seconds == 900
    assert gateway.consecutive_failures == 0
    assert gateway.circuit_open_until is None

