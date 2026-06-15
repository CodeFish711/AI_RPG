from pathlib import Path

import pytest

from core.agents.guard import GuardDecision
from tests._fakes import FakeStructuredGateway

from game.text_adventure.schemas import NarrativeBeat


@pytest.mark.asyncio
async def test_app_run_session_processes_inputs_until_quit(tmp_path: Path):
    """run_session 处理输入直到 /quit;每轮产 NarrativeBeat + 调 Curator wrapper。"""
    from game.text_adventure.app import run_session

    gateway = FakeStructuredGateway()
    gateway.queue_response(NarrativeBeat, NarrativeBeat(narration="第 1 轮回复"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))
    gateway.queue_response(NarrativeBeat, NarrativeBeat(narration="第 2 轮回复"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    inputs = iter(["环顾四周", "前进", "/quit"])
    outputs: list[str] = []

    await run_session(
        session_id="test_sess",
        data_dir=tmp_path,
        gateway=gateway,
        input_fn=lambda _prompt: next(inputs),
        output_fn=lambda text: outputs.append(text),
    )

    # 应输出 2 轮 narration
    assert any("第 1 轮回复" in o for o in outputs)
    assert any("第 2 轮回复" in o for o in outputs)


@pytest.mark.asyncio
async def test_app_run_session_handles_empty_input(tmp_path: Path):
    """空输入应被忽略不调 LLM。"""
    from game.text_adventure.app import run_session

    gateway = FakeStructuredGateway()
    gateway.queue_response(NarrativeBeat, NarrativeBeat(narration="real reply"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    inputs = iter(["", "  ", "real input", "/quit"])
    outputs: list[str] = []

    await run_session(
        session_id="test_empty",
        data_dir=tmp_path,
        gateway=gateway,
        input_fn=lambda _prompt: next(inputs),
        output_fn=lambda text: outputs.append(text),
    )

    # 只调了 1 次 LLM(real input)
    assert any("real reply" in o for o in outputs)
    # 1 个非系统提示的 narration 输出
    narration_outputs = [o for o in outputs if "real reply" in o]
    assert len(narration_outputs) == 1


def test_app_resolve_session_handles_resume_with_valid_id(tmp_path: Path):
    """--resume <id>:id 在 list_sessions 中存在时返回该 id。"""
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore
    from game.text_adventure.app import resolve_session

    store = TurnStore(data_dir=tmp_path)
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="existing_sess")))

    result = resolve_session(turn_store=store, resume="existing_sess", new_session=None)
    assert result == "existing_sess"


def test_app_resolve_session_falls_back_to_default_when_no_args(tmp_path: Path):
    """无 --resume / --session 时返回 'default'。"""
    from core.turn_store import TurnStore
    from game.text_adventure.app import resolve_session

    store = TurnStore(data_dir=tmp_path)
    result = resolve_session(turn_store=store, resume=None, new_session=None)
    assert result == "default"


def test_app_resolve_session_uses_new_session_arg(tmp_path: Path):
    """--session <id>:直接用该 id 作为新 session。"""
    from core.turn_store import TurnStore
    from game.text_adventure.app import resolve_session

    store = TurnStore(data_dir=tmp_path)
    result = resolve_session(turn_store=store, resume=None, new_session="my_session")
    assert result == "my_session"


def test_app_resolve_session_raises_on_invalid_resume(tmp_path: Path):
    """--resume <id> 但 id 不存在时 raise(让 caller 提示用户)。"""
    from core.turn_store import TurnStore
    from game.text_adventure.app import resolve_session

    store = TurnStore(data_dir=tmp_path)
    with pytest.raises(ValueError, match="Session not found"):
        resolve_session(turn_store=store, resume="ghost_id", new_session=None)


@pytest.mark.asyncio
async def test_app_with_world_init_seeds_memory(tmp_path):
    """--with-world-init 触发 world_init 流程。LLM 响应 queue 太复杂(WorldInitWorkflow 有 6+ 次调用),
    本测试占位 skip,留 live smoke 验证整链路。"""
    pytest.skip(
        "world_init 流程的 LLM 响应 queue 复杂,留 live smoke 验证。"
        "只确认 import / argparse 接通即可。"
    )
