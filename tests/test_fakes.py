import pytest
from pydantic import BaseModel

from core.schemas import LLMRequest, Message


class _Out(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_fake_gateway_returns_queued_response():
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Out, _Out(answer="ok"))

    request = LLMRequest(messages=[Message(role="user", content="ping")])
    result = await gateway.complete_and_parse(request, _Out)

    assert result.answer == "ok"


@pytest.mark.asyncio
async def test_fake_gateway_raises_when_queue_empty():
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    request = LLMRequest(messages=[Message(role="user", content="ping")])

    with pytest.raises(AssertionError, match="no queued response"):
        await gateway.complete_and_parse(request, _Out)


@pytest.mark.asyncio
async def test_fake_gateway_records_invocations():
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Out, _Out(answer="a"))
    gateway.queue_response(_Out, _Out(answer="b"))

    request1 = LLMRequest(messages=[Message(role="user", content="first")])
    request2 = LLMRequest(messages=[Message(role="user", content="second")])
    await gateway.complete_and_parse(request1, _Out)
    await gateway.complete_and_parse(request2, _Out)

    assert len(gateway.invocations) == 2
    assert gateway.invocations[0].messages[0].content == "first"
    assert gateway.invocations[1].messages[0].content == "second"


@pytest.mark.asyncio
async def test_fake_gateway_raises_on_schema_mismatch():
    from tests._fakes import FakeStructuredGateway

    class _Other(BaseModel):
        value: int

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Out, _Out(answer="x"))

    request = LLMRequest(messages=[Message(role="user", content="x")])
    with pytest.raises(AssertionError, match="schema mismatch"):
        await gateway.complete_and_parse(request, _Other)
