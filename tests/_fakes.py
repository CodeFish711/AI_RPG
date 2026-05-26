from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from core.schemas import LLMRequest

T = TypeVar("T", bound=BaseModel)


class FakeStructuredGateway:
    """测试用 LLM gateway。按 (schema, response) 顺序返回预编排响应。"""

    def __init__(self) -> None:
        self._queue: list[tuple[type[BaseModel], BaseModel]] = []
        self.invocations: list[LLMRequest] = []

    def queue_response(self, schema: type[T], response: T) -> None:
        assert isinstance(response, schema), (
            f"queue_response: response type {type(response).__name__} "
            f"does not match schema {schema.__name__}"
        )
        self._queue.append((schema, response))

    async def complete_and_parse(self, request: LLMRequest, output_schema: type[T]) -> T:
        self.invocations.append(request)
        assert self._queue, f"FakeStructuredGateway: no queued response for {output_schema.__name__}"
        queued_schema, queued_response = self._queue.pop(0)
        assert queued_schema is output_schema, (
            f"FakeStructuredGateway: schema mismatch — queued {queued_schema.__name__}, "
            f"requested {output_schema.__name__}"
        )
        return queued_response  # type: ignore[return-value]
