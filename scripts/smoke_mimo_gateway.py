from __future__ import annotations

import asyncio

from core.config import AppSettings
from core.llm_gateway import LLMGateway
from core.schemas import LLMRequest, Message, ThinkingPolicy


def build_smoke_requests() -> tuple[LLMRequest, LLMRequest]:
    disabled = LLMRequest(
        messages=[
            Message(role="system", content="你是接口连通性测试助手，不要展示推理过程。"),
            Message(role="user", content="请只回答四个汉字：连接成功"),
        ],
        temperature=0,
        max_tokens=128,
        thinking=ThinkingPolicy(type="disabled"),
    )
    enabled = LLMRequest(
        messages=[
            Message(role="system", content="你是接口参数测试助手。"),
            Message(role="user", content='请只输出 JSON：{"ok":true}'),
        ],
        temperature=0,
        max_tokens=1024,
        thinking=ThinkingPolicy(type="enabled"),
    )
    return disabled, enabled


async def main() -> None:
    settings = AppSettings()
    if not settings.mimo_api_key:
        raise SystemExit("MIMO_API_KEY is required. Put it in .env.local or export it in the shell.")

    gateway = LLMGateway(
        api_key=settings.mimo_api_key,
        base_url=settings.mimo_base_url,
        default_model=settings.mimo_model,
    )
    disabled, enabled = build_smoke_requests()

    short_response = await gateway.complete(disabled.model_copy(update={"model": settings.mimo_model}))
    print(f"disabled thinking response: {short_response.content}")

    structured_response = await gateway.complete(enabled.model_copy(update={"model": settings.mimo_model}))
    print(f"enabled thinking response: {structured_response.content}")


if __name__ == "__main__":
    asyncio.run(main())

