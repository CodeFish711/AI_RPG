from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from core.schemas import LLMRequest, LLMResponse, Message, ThinkingPolicy


T = TypeVar("T", bound=BaseModel)


class LLMGatewayError(RuntimeError):
    """Base error for provider and gateway failures."""


class GatewaySchemaError(LLMGatewayError):
    """Raised when model output cannot be coerced into the requested schema."""


class GatewayCircuitOpen(LLMGatewayError):
    """Raised when circuit breaker is open due to consecutive failures."""


class LLMGateway:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://token-plan-cn.xiaomimimo.com/v1",
        default_model: str = "mimo-v2.5-pro",
        max_retries: int = 2,
        timeout: float = 60.0,
        min_tokens_for_thinking: int = 1024,
        default_thinking: ThinkingPolicy | None = None,
        failure_threshold: int = 5,
        circuit_window_seconds: int = 900,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.max_retries = max_retries
        self.timeout = timeout
        self.min_tokens_for_thinking = min_tokens_for_thinking
        self.default_thinking = default_thinking or ThinkingPolicy(type="auto")
        self.failure_threshold = failure_threshold
        self.circuit_window_seconds = circuit_window_seconds
        self.consecutive_failures = 0
        self.circuit_open_until: datetime | None = None
        self._transport = transport

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # 熔断检查:circuit 开着且未到 window 结束 → 直接抛
        if self.circuit_open_until is not None:
            now = datetime.now(UTC)
            if now < self.circuit_open_until:
                raise GatewayCircuitOpen(
                    f"circuit breaker open until {self.circuit_open_until.isoformat()}"
                )
            # window 已过,关闭熔断,重置 counter,继续尝试
            self.circuit_open_until = None
            self.consecutive_failures = 0

        current = self._with_default_model(request)
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._call_api(current)
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    continue
                # 最终失败,累积 counter 并可能开熔断
                self._record_failure()
                raise LLMGatewayError(f"LLM provider request failed: {exc}") from exc

            if self._needs_more_completion_budget(response) and attempt < self.max_retries:
                current = current.model_copy(update={"max_tokens": max(current.max_tokens * 2, self.min_tokens_for_thinking * 2)})
                continue

            # 成功:reset counter
            self.consecutive_failures = 0
            self.circuit_open_until = None
            return response

        # 不该走到这里
        self._record_failure()
        raise LLMGatewayError(f"LLM provider request failed: {last_error}")

    def _record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.circuit_open_until = datetime.now(UTC) + timedelta(seconds=self.circuit_window_seconds)

    async def complete_and_parse(self, request: LLMRequest, output_schema: type[T]) -> T:
        current = request
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            response = await self.complete(current)
            try:
                payload = self.extract_json(response.content)
                return output_schema.model_validate(payload)
            except (ValueError, ValidationError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    current = self._with_validation_feedback(current, exc, output_schema)
                    continue

        raise GatewaySchemaError(f"LLM output failed schema validation: {last_error}") from last_error

    @staticmethod
    def run_sync(awaitable: Any) -> Any:
        return asyncio.run(awaitable)

    async def _call_api(self, request: LLMRequest) -> LLMResponse:
        payload = self._build_payload(request)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        message = choice.get("message") or {}
        return LLMResponse(
            content=message.get("content") or "",
            model=request.model,
            usage=data.get("usage") or {},
            finish_reason=choice.get("finish_reason"),
        )

    def _build_payload(self, request: LLMRequest) -> dict[str, Any]:
        thinking = self._resolve_thinking(request.thinking)
        max_tokens = request.max_tokens
        if thinking.type == "enabled":
            max_tokens = max(max_tokens, self.min_tokens_for_thinking)

        payload: dict[str, Any] = {
            "messages": [message.model_dump() for message in request.messages],
            "model": request.model or self.default_model,
            "temperature": request.temperature,
            "max_tokens": max_tokens,
        }
        if thinking.type != "auto":
            payload["thinking"] = {"type": thinking.type}
        payload.update(request.extra)
        return payload

    def _resolve_thinking(self, thinking: ThinkingPolicy) -> ThinkingPolicy:
        if thinking.type == "auto":
            return self.default_thinking
        return thinking

    def _with_default_model(self, request: LLMRequest) -> LLMRequest:
        if request.model:
            return request
        return request.model_copy(update={"model": self.default_model})

    def _with_validation_feedback(
        self,
        request: LLMRequest,
        error: Exception,
        output_schema: type[BaseModel],
    ) -> LLMRequest:
        feedback = Message(
            role="user",
            content=(
                "你的上一个 JSON 输出校验失败。\n"
                f"错误：{error}\n"
                f"目标 Schema：{json.dumps(output_schema.model_json_schema(), ensure_ascii=False)}\n"
                "请只输出符合 Schema 的 JSON，不要输出解释。"
            ),
        )
        return request.model_copy(
            update={
                "messages": [*request.messages, feedback],
                "temperature": max(0.0, request.temperature * 0.5),
                "thinking": ThinkingPolicy(type="disabled"),
            }
        )

    @staticmethod
    def extract_json(text: str) -> Any:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            first_object = stripped.find("{")
            last_object = stripped.rfind("}")
            if first_object >= 0 and last_object > first_object:
                return json.loads(stripped[first_object : last_object + 1])
            first_array = stripped.find("[")
            last_array = stripped.rfind("]")
            if first_array >= 0 and last_array > first_array:
                return json.loads(stripped[first_array : last_array + 1])
            raise

    @staticmethod
    def _needs_more_completion_budget(response: LLMResponse) -> bool:
        details = response.usage.get("completion_tokens_details") or {}
        reasoning_tokens = int(details.get("reasoning_tokens") or 0)
        return response.content.strip() == "" and response.finish_reason == "length" and reasoning_tokens > 0
