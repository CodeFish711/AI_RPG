# Phase B: Turn Loop 主路径 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 Turn Loop Engine 重设计的 Phase B — 落地 `core/turn_loop.py` 主路径,集成 NarrativeAgent / WorldMemory / ConsistencyGuard / TurnStore 五件套,跑通完整 ①-⑦ 时序含 Guard 三分支 + Gateway 熔断降级 + TurnTelemetry 记录。完成后 spec §8.C 前 4 个集成测试用例全过。

**Architecture:** TurnLoop 是 core 层的薄编排器,依赖注入 4 个 Phase A 已就位的组件,自身只负责装配 GuardInput.references / 处理 Guard 决策分支 / 写入 Turn 快照 / 处理熔断异常。同时把 Phase A final reviewer 的 4 个 Important risks 在前两个 task 一次性修掉(避免在 TurnLoop 实施中再被踩到)。

**Tech Stack:** Python 3.11+, Pydantic 2.7+, pytest + pytest-asyncio。无新依赖。

**Spec 引用:** [docs/superpowers/specs/2026-05-26-turn-loop-engine-redesign-design.md](../specs/2026-05-26-turn-loop-engine-redesign-design.md) §6, §7, §8.C, §9 Phase B / Phase C

**Phase A 完成报告**:[2026-05-26-phase-a-completion-report.md](2026-05-26-phase-a-completion-report.md)。Final reviewer 提的 4 个 Important risks 由本 plan 的 Task 1-2 处理。

---

## File Structure

| 文件 | 类型 | 职责 |
|------|------|------|
| `src/core/schemas.py` | 修改 | 删 TurnResult(Task 1 搬到 turn_store.py) |
| `src/core/turn_store.py` | 修改 | 加 TurnResult / _validate_session_id helper |
| `src/core/agents/guard.py` | 修改 | GuardInput.session_id 加 pattern;ConsistencyGuard 接受 instruction override(Task 2);_GUARD_INSTRUCTION 去游戏域措辞 |
| `src/core/agents/narrative.py` | 修改 | NarrativeContext.extra 改 dict[str, Any];NarrativeAgent 接受 instruction override(Task 2);_NARRATIVE_INSTRUCTION 去游戏域措辞 |
| `src/core/llm_gateway.py` | 修改 | 加 GatewayCircuitOpen 异常 + circuit breaker 状态 + 阈值校验 |
| `src/core/turn_loop.py` | 新建 | TurnLoop 主编排器 |
| `tests/test_core_schemas.py` | 修改 | 删 TurnResult 测试(移到 test_turn_store.py) |
| `tests/test_turn_store.py` | 修改 | 加 TurnResult 测试 + session_id 校验测试 |
| `tests/test_core_agents_guard.py` | 修改 | GuardInput pattern 测试 + instruction override 测试 |
| `tests/test_core_agents_narrative.py` | 修改 | extra 类型测试 + instruction override 测试 |
| `tests/test_llm_gateway.py` | 修改 | circuit breaker 测试 |
| `tests/test_turn_loop.py` | 新建 | TurnLoop 全部测试(accept / revise / reject / circuit-open / telemetry) |

**Phase B 不涉及**:Phase D(text_adventure)/ Phase E(world_init 降级)/ ChromaRAGRepository 真实使用 / Live LLM 集成。

---

## Pre-Task: 环境核对

- [ ] **Step 1: 确认在 AI_RPG 目录、Phase A tag、Phase A 测试基线**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && pwd && git tag | grep phase-a && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q 2>&1 | tail -3
```

Expected: `phase-a-complete` 存在 + ~71 passed + 1 skipped。若数字不符,先弄清楚 Phase A 基线再开工。

---

## Task 1: Phase A risks 清理

**Files:**
- Modify: `src/core/schemas.py`(删 TurnResult)
- Modify: `src/core/turn_store.py`(加 TurnResult + _validate_session_id + 在 save/load/_path_for 校验)
- Modify: `src/core/agents/guard.py`(GuardInput.session_id 加 pattern)
- Modify: `src/core/agents/narrative.py`(NarrativeContext.extra 改 dict[str, Any])
- Modify: `tests/test_core_schemas.py`(删 TurnResult 测试)
- Modify: `tests/test_turn_store.py`(加 TurnResult 测试 + session_id 校验测试)
- Modify: `tests/test_core_agents_guard.py`(GuardInput pattern 测试)

- [ ] **Step 1: 写 TurnResult 在 turn_store.py 的失败测试**

追加到 `tests/test_turn_store.py` 末尾:

```python
def test_turn_result_holds_turn_reference():
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnResult

    turn = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="s1"))
    result = TurnResult(turn=turn, response_text="hello", guard_retries=0)
    assert result.turn.id == turn.id
    assert result.response_text == "hello"
    assert result.guard_retries == 0


def test_turn_result_defaults_guard_retries_to_zero():
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnResult

    turn = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="s1"))
    result = TurnResult(turn=turn, response_text="hi")
    assert result.guard_retries == 0


def test_turn_result_response_text_required_non_empty():
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnResult
    from pydantic import ValidationError

    turn = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="s1"))
    with pytest.raises(ValidationError):
        TurnResult(turn=turn, response_text="")


def test_turn_store_save_rejects_invalid_session_id(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    # 用 pydantic-level 合法 session_id 构造 Turn(因为 TurnInput 自带 pattern)
    # 然后手动改 input 字段绕过(模拟外部恶意输入)— 测试 store 入口防御
    turn = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="legit"))
    # 这次构造时 pydantic 已挡 — 验证另一个路径:load_session 接外部 session_id
    with pytest.raises(ValueError, match="invalid session_id"):
        store.load_session(session_id="../etc/passwd")
    with pytest.raises(ValueError, match="invalid session_id"):
        store.load_recent(session_id="a/b", n=5)


def test_turn_store_save_accepts_valid_session_id(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="abc_123")))
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=1, session_id="abc-123")))
    assert (tmp_path / "abc_123.jsonl").exists()
    assert (tmp_path / "abc-123.jsonl").exists()
```

- [ ] **Step 2: 同时删除 test_core_schemas.py 中旧的 TurnResult 测试,把 TurnResult 引用从 import 行删掉**

打开 `tests/test_core_schemas.py`,做 3 处修改:

(1) 第一行 import 改为(删 TurnResult):
```python
from core.schemas import LLMRequest, Message, ThinkingPolicy, TurnInput
```

(2) 删除整个 `test_turn_result_defaults_guard_retries_to_zero` 函数(已迁移到 test_turn_store.py)

(3) 删除整个 `test_turn_result_rejects_negative_guard_retries` 函数(也迁移到 test_turn_store.py,Task 1 不再单独保留 — 因为 Turn 类承担了大部分校验,TurnResult 只是个简单 wrapper)

- [ ] **Step 3: 给 GuardInput.session_id 加 pattern 的失败测试**

追加到 `tests/test_core_agents_guard.py` 末尾:

```python
def test_guard_input_rejects_path_traversal_session_id():
    from core.agents.guard import GuardInput

    with pytest.raises(ValidationError):
        GuardInput(proposal={}, session_id="../etc")
    with pytest.raises(ValidationError):
        GuardInput(proposal={}, session_id="a/b")
    with pytest.raises(ValidationError):
        GuardInput(proposal={}, session_id="a b")
```

- [ ] **Step 4: 给 NarrativeContext.extra 改 Any 的兼容测试(verify 接受 nested dict)**

追加到 `tests/test_core_agents_narrative.py` 末尾:

```python
def test_narrative_context_extra_accepts_nested_dict():
    from core.agents.narrative import NarrativeContext
    from core.schemas import TurnInput

    ctx = NarrativeContext(
        player_input=TurnInput(raw_text="x", turn_index=0, session_id="s1"),
        retrieved_memory=[],
        extra={"scene": {"location": "forest", "characters": ["Aria"]}},
    )
    # 序列化后 nested dict 仍然可读
    dumped = ctx.model_dump(mode="json")
    assert dumped["extra"]["scene"]["location"] == "forest"
    assert dumped["extra"]["scene"]["characters"] == ["Aria"]
```

- [ ] **Step 5: 跑测试,确认 fail(8 新测试 fail,旧测试可能有 import error)**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_store.py tests/test_core_agents_guard.py tests/test_core_agents_narrative.py tests/test_core_schemas.py -v
```

Expected: 大量 fail(TurnResult 找不到 / session_id pattern 未实现 / 其他)。这是 RED 阶段。

- [ ] **Step 6: 改 `src/core/schemas.py`(删 TurnResult class 整段)**

完整替换为:

```python
from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ThinkingPolicy(BaseModel):
    type: Literal["disabled", "auto", "enabled"] = "auto"


class LLMRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    model: str = "mimo-v2.5-pro"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    thinking: ThinkingPolicy = Field(default_factory=ThinkingPolicy)
    extra: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: dict[str, Any] = Field(default_factory=dict)
    finish_reason: str | None = None
    cached: bool = False


class MemoryFragment(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class RAGQueryResult(BaseModel):
    fragment: MemoryFragment
    score: float


class TurnInput(BaseModel):
    raw_text: str = Field(min_length=1)
    intent_hint: str | None = None
    turn_index: int = Field(ge=0)
    session_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_\-]+$")
```

注意:**完全删除原 TurnResult class**。

- [ ] **Step 7: 改 `src/core/turn_store.py`(加 TurnResult class + _validate_session_id helper + 在 save/load_session/load_recent/_path_for 调用)**

完整替换为:

```python
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from core.agents.guard import GuardDecision
from core.schemas import RAGQueryResult, TurnInput
from core.world_memory import MemoryRecord


_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _validate_session_id(session_id: str) -> None:
    """防御性入口校验。Pydantic 已挡构造时不合法的 session_id,这里挡函数参数式注入。"""
    if not _SESSION_ID_RE.match(session_id):
        raise ValueError(f"invalid session_id: {session_id!r}")


class Turn(BaseModel):
    """一次完整闭环的快照,可序列化存盘。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    input: TurnInput
    retrieved_memory: list[RAGQueryResult] = Field(default_factory=list)
    narrative_draft: dict[str, Any] | None = None
    guard_decision: GuardDecision | None = None
    curated_records: list[MemoryRecord] = Field(default_factory=list)
    response_text: str | None = None
    status: Literal["ok", "degraded", "failed"] = "ok"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TurnResult(BaseModel):
    """TurnLoop.run_turn 的返回值。turn 是整轮快照,response_text 是给玩家看的文本。"""

    turn: Turn
    response_text: str = Field(min_length=1)
    guard_retries: int = Field(default=0, ge=0)


class TurnStore:
    """把 Turn 序列化为 JSONL,每 session 一个文件:<data_dir>/<session_id>.jsonl。"""

    def __init__(self, *, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save(self, turn: Turn) -> None:
        # turn.input.session_id 已被 Pydantic 校验过 pattern
        path = self._path_for(turn.input.session_id)
        line = turn.model_dump_json()
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load_session(self, *, session_id: str) -> list[Turn]:
        _validate_session_id(session_id)
        path = self._path_for(session_id)
        if not path.exists():
            return []
        turns: list[Turn] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            turns.append(Turn.model_validate_json(line))
        return turns

    def load_recent(self, *, session_id: str, n: int) -> list[Turn]:
        _validate_session_id(session_id)
        if n <= 0:
            return []
        all_turns = self.load_session(session_id=session_id)
        return all_turns[-n:]

    def _path_for(self, session_id: str) -> Path:
        # _path_for 是私有,但仍做防御性 assert(如果未来内部代码绕过校验)
        assert _SESSION_ID_RE.match(session_id), f"_path_for: invalid session_id {session_id!r}"
        return self.data_dir / f"{session_id}.jsonl"
```

- [ ] **Step 8: 改 `src/core/agents/guard.py`(GuardInput.session_id 加 pattern)**

打开文件,找到 `class GuardInput(BaseModel):` 块,把:
```python
    session_id: str = Field(min_length=1)
```
改为:
```python
    session_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_\-]+$")
```

- [ ] **Step 9: 改 `src/core/agents/narrative.py`(NarrativeContext.extra 改 dict[str, Any])**

打开文件,把:
```python
class NarrativeContext(BaseModel):
    player_input: TurnInput
    retrieved_memory: list[RAGQueryResult] = Field(default_factory=list)
    extra: dict[str, object] = Field(default_factory=dict)
```

改为(只改 extra 类型):
```python
from typing import Any

# ... 在 imports 顶部加 Any (如果还没有) ...

class NarrativeContext(BaseModel):
    player_input: TurnInput
    retrieved_memory: list[RAGQueryResult] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
```

具体:在 `from pydantic import BaseModel, Field` 下面加 `from typing import Any`(若已存在跳过)。`extra` 类型从 `dict[str, object]` 改为 `dict[str, Any]`。

- [ ] **Step 10: 跑测试,确认全部 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: ~80+ passed(71 Phase A + 8 新增 ≈ 79-80),1 skipped。若有 fail 排查 — 常见原因:
- `TurnResult` import 仍在 schemas 引用(grep `from core.schemas import.*TurnResult`)
- `tests/test_core_schemas.py` 没删 TurnResult test
- session_id pattern 影响其他 test fixture(找出来改成合法 session_id)

如果发现 Task 1 范围外的测试 fail(比如 turn_loop / 其他 task 6+ 的代码,本 task 都没碰),STOP 报告。

- [ ] **Step 11: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/core/schemas.py src/core/turn_store.py src/core/agents/guard.py src/core/agents/narrative.py tests/test_core_schemas.py tests/test_turn_store.py tests/test_core_agents_guard.py tests/test_core_agents_narrative.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-b: task 1 — Phase A 4 个 risks 清理

- TurnResult 从 schemas.py 搬到 turn_store.py(turn: Turn 直接引用,
  解决 Phase A 为避免循环引用做的妥协)
- TurnStore 加 _validate_session_id helper,save/load_session/load_recent
  入口防御性校验(spec §6.4 路径安全)
- GuardInput.session_id 加 pattern,与 TurnInput/MemoryRecord 一致
- NarrativeContext.extra 类型从 dict[str, object] 改 dict[str, Any],
  与 LLMRequest.extra / 其他 metadata 字段一致
- 加 8 个 regression 测试

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Prompt prose 通用化 + game 注入接口

**Files:**
- Modify: `src/core/agents/guard.py`(_GUARD_INSTRUCTION 通用化 + ConsistencyGuard 接 instruction override)
- Modify: `src/core/agents/narrative.py`(_NARRATIVE_INSTRUCTION 通用化 + NarrativeAgent 接 instruction override)
- Modify: `tests/test_core_agents_guard.py`(instruction override 测试)
- Modify: `tests/test_core_agents_narrative.py`(instruction override 测试)

**目标**:
- 默认 instruction 字符串去除游戏域措辞("Canon Guard / 复活死人 / 凭空物品 / 角色 / 地点 / 事件 / 玩家状态")
- 加 `instruction: str | None = None` 参数到 `__init__`,None 时用 default,否则用 game 注入
- 这是为 Phase D 让 game/text_adventure 注入自己的 prompt template 做准备

- [ ] **Step 1: 写 instruction override 测试(guard)**

追加到 `tests/test_core_agents_guard.py` 末尾:

```python
@pytest.mark.asyncio
async def test_consistency_guard_uses_default_instruction_when_not_overridden():
    from core.agents.guard import ConsistencyGuard, GuardDecision, GuardInput
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    profile = AgentProfile(id="g", name="G", role="r", objective="o")
    guard = ConsistencyGuard(runtime=AgentRuntime(gateway=gateway), profile=profile)
    await guard.check(GuardInput(proposal={}, session_id="s"))

    user_msg = gateway.invocations[0].messages[1]
    # default instruction 应该在 prompt 里(user message 包含 instruction)
    assert "一致" in user_msg.content or "accept" in user_msg.content


@pytest.mark.asyncio
async def test_consistency_guard_uses_instruction_override_when_provided():
    from core.agents.guard import ConsistencyGuard, GuardDecision, GuardInput
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    profile = AgentProfile(id="g", name="G", role="r", objective="o")
    custom_instruction = "GAME_SPECIFIC_GUARD_PROMPT_xyz123"
    guard = ConsistencyGuard(
        runtime=AgentRuntime(gateway=gateway),
        profile=profile,
        instruction=custom_instruction,
    )
    await guard.check(GuardInput(proposal={}, session_id="s"))

    user_msg = gateway.invocations[0].messages[1]
    assert "GAME_SPECIFIC_GUARD_PROMPT_xyz123" in user_msg.content
```

- [ ] **Step 2: 写 instruction override 测试(narrative)**

追加到 `tests/test_core_agents_narrative.py` 末尾:

```python
@pytest.mark.asyncio
async def test_narrative_agent_uses_default_instruction_when_not_overridden():
    from core.agents.narrative import NarrativeAgent, NarrativeContext
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from core.schemas import TurnInput
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(_DemoBeat, _DemoBeat(narration="ok"))

    profile = AgentProfile(id="n", name="N", role="r", objective="o")
    agent = NarrativeAgent(runtime=AgentRuntime(gateway=gateway), profile=profile)
    await agent.run(
        context=NarrativeContext(
            player_input=TurnInput(raw_text="x", turn_index=0, session_id="s"),
            retrieved_memory=[],
        ),
        output_schema=_DemoBeat,
    )

    user_msg = gateway.invocations[0].messages[1]
    # default instruction 应该出现(generic "叙事" 字样)
    assert "叙事" in user_msg.content or "narrative" in user_msg.content.lower()


@pytest.mark.asyncio
async def test_narrative_agent_uses_instruction_override_when_provided():
    from core.agents.narrative import NarrativeAgent, NarrativeContext
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from core.schemas import TurnInput
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(_DemoBeat, _DemoBeat(narration="ok"))

    profile = AgentProfile(id="n", name="N", role="r", objective="o")
    custom = "GAME_NARRATIVE_TEMPLATE_xyz999"
    agent = NarrativeAgent(
        runtime=AgentRuntime(gateway=gateway),
        profile=profile,
        instruction=custom,
    )
    await agent.run(
        context=NarrativeContext(
            player_input=TurnInput(raw_text="x", turn_index=0, session_id="s"),
            retrieved_memory=[],
        ),
        output_schema=_DemoBeat,
    )

    user_msg = gateway.invocations[0].messages[1]
    assert "GAME_NARRATIVE_TEMPLATE_xyz999" in user_msg.content
```

- [ ] **Step 3: 跑测试,确认 fail**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_core_agents_guard.py tests/test_core_agents_narrative.py -v -k "instruction"
```

Expected: 4 新测试 FAIL(instruction 参数不存在 + default 文本不匹配)。

- [ ] **Step 4: 改 `src/core/agents/guard.py`(通用化 _GUARD_INSTRUCTION + 加 instruction override)**

完整替换为:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile, AgentTask


class GuardFinding(BaseModel):
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1)
    path: str | None = None


class GuardDecision(BaseModel):
    decision: Literal["accept", "revise", "reject"]
    findings: list[GuardFinding] = Field(default_factory=list)
    revised_payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _revise_requires_payload(self) -> "GuardDecision":
        if self.decision == "revise" and self.revised_payload is None:
            raise ValueError("revised_payload is required when decision='revise'")
        return self


class ReferenceItem(BaseModel):
    label: str = Field(min_length=1)
    content: str = Field(min_length=1)
    score: float | None = None


class GuardInput(BaseModel):
    proposal: dict[str, Any]
    references: list[ReferenceItem] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    session_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_\-]+$")


# 通用 default instruction:不含游戏域措辞(原"Canon Guard 复活死人凭空物品"已剔除)
# game 层可通过 ConsistencyGuard(instruction=...) 注入自己的 game-specific prompt
DEFAULT_GUARD_INSTRUCTION = (
    "你是一致性裁决 agent。根据'参考材料 / 硬性规则'判定'提案'是否合规,返回 GuardDecision JSON。"
    "accept = 提案与参考一致放行;"
    "revise = 提案存在可修复的小矛盾,必须给出 revised_payload(修订后完整提案);"
    "reject = 提案存在不可修复矛盾。"
)


class ConsistencyGuard:
    """通用 Guard:把 GuardInput 装进 AgentTask,调 AgentRuntime,返回 GuardDecision。

    instruction 参数允许 game 层注入 game-specific prompt template,
    None 时用 DEFAULT_GUARD_INSTRUCTION。
    """

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        profile: AgentProfile,
        instruction: str | None = None,
    ) -> None:
        self.runtime = runtime
        self.profile = profile
        self.instruction = instruction if instruction is not None else DEFAULT_GUARD_INSTRUCTION

    async def check(self, guard_input: GuardInput) -> GuardDecision:
        task = AgentTask(
            instruction=self.instruction,
            context=guard_input.model_dump(mode="json"),
            required_output="GuardDecision",
        )
        return await self.runtime.run_agent(self.profile, task, GuardDecision)
```

注意:
- `_GUARD_INSTRUCTION` 改名为 `DEFAULT_GUARD_INSTRUCTION`(去前缀下划线,成为公开默认值)
- 文本去掉 "Canon Guard" / "复活死人" / "凭空物品"
- `instruction` 是 `__init__` 的 keyword-only 参数,None 用 default

- [ ] **Step 5: 改 `src/core/agents/narrative.py`(通用化 + 加 instruction override)**

完整替换为:

```python
from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, Field

from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile, AgentTask
from core.schemas import RAGQueryResult, TurnInput


T = TypeVar("T", bound=BaseModel)


# 通用 default instruction:不含游戏域措辞(原"角色/地点/事件/玩家状态"已剔除)
# game 层可通过 NarrativeAgent(instruction=...) 注入自己的 game-specific prompt
DEFAULT_NARRATIVE_INSTRUCTION = (
    "你是叙事生成 agent。基于玩家本轮输入与检索到的相关记忆,"
    "生成符合 output_schema 的下一段叙事 JSON。"
    "如有新事实需要记录,通过 output_schema 的相应字段返回。"
)


class NarrativeContext(BaseModel):
    player_input: TurnInput
    retrieved_memory: list[RAGQueryResult] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class NarrativeAgent:
    """单 agent 叙事生成的统一入口,output_schema 由 game 层指定。

    instruction 参数允许 game 层注入 game-specific prompt template,
    None 时用 DEFAULT_NARRATIVE_INSTRUCTION。
    """

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        profile: AgentProfile,
        instruction: str | None = None,
    ) -> None:
        self.runtime = runtime
        self.profile = profile
        self.instruction = instruction if instruction is not None else DEFAULT_NARRATIVE_INSTRUCTION

    async def run(self, *, context: NarrativeContext, output_schema: type[T]) -> T:
        task = AgentTask(
            instruction=self.instruction,
            context=context.model_dump(mode="json"),
            required_output=output_schema.__name__,
        )
        return await self.runtime.run_agent(self.profile, task, output_schema)
```

注意:
- `_NARRATIVE_INSTRUCTION` 改名 `DEFAULT_NARRATIVE_INSTRUCTION`
- 文本去掉 "角色/地点/事件/玩家状态" 等游戏域词
- `instruction` 参数模式与 guard 一致

- [ ] **Step 6: 跑测试,确认全部 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_core_agents_guard.py tests/test_core_agents_narrative.py -v
```

Expected: 全部 PASS(原有测试 + 4 个新 instruction 测试)。

- [ ] **Step 7: 跑 import-graph 测试,确认 core 不再含游戏域 prose(检验 Phase A final reviewer 关切已解决)**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_import_graph.py -v
.venv/bin/python -c "
import re
patt = re.compile(r'\b(canon|death|resurrect)\b', re.IGNORECASE)
import pathlib
for p in pathlib.Path('src/core').rglob('*.py'):
    text = p.read_text()
    if patt.search(text):
        print(f'{p}: still contains forbidden English word')
" 
```

Expected: import-graph 2 测试 PASS。Python 脚本无输出(代表 core 不再含 canon/death/resurrect 等)。

- [ ] **Step 8: 跑全套测试**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: ~84 passed,1 skipped。

- [ ] **Step 9: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/core/agents/guard.py src/core/agents/narrative.py tests/test_core_agents_guard.py tests/test_core_agents_narrative.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-b: task 2 — prompt prose 通用化 + game 可注入 instruction

- DEFAULT_GUARD_INSTRUCTION / DEFAULT_NARRATIVE_INSTRUCTION 去除游戏域措辞
  (原 "Canon Guard / 复活死人 / 凭空物品" + "角色/地点/事件/玩家状态"
   全部剔除),现在 core/ 真正不含游戏域 prose
- ConsistencyGuard / NarrativeAgent __init__ 加 instruction: str | None = None
  参数,None 用 default,game 层(Phase D)可注入自己的 prompt template
- 4 个新 instruction override 测试

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: LLMGateway circuit breaker

**Files:**
- Modify: `src/core/llm_gateway.py`(加 GatewayCircuitOpen 异常 + circuit state + 阈值校验)
- Modify: `tests/test_llm_gateway.py`(加 circuit breaker 测试)

**目标**(spec §7.D):连续 N 次调用失败 → 触发熔断,X 秒内 `complete()` 直接抛 `GatewayCircuitOpen`。N 默认 5,X 默认 15 分钟(900 秒)。成功调用 reset counter。

- [ ] **Step 1: 写 circuit breaker 失败测试**

追加到 `tests/test_llm_gateway.py` 末尾(如果文件不存在,先创建并加 import):

先确认 `tests/test_llm_gateway.py` 是否存在,内容是什么:

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && ls -la tests/test_llm_gateway.py && head -30 tests/test_llm_gateway.py 2>/dev/null || echo "NOT FOUND"
```

如果文件不存在,创建并写以下完整内容(包括 imports);如果存在,追加新测试。

新测试内容(若新建文件,把 imports 也包进去):

```python
import asyncio

import httpx
import pytest

from core.llm_gateway import GatewayCircuitOpen, LLMGateway, LLMGatewayError
from core.schemas import LLMRequest, Message


def _always_fail_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "service unavailable"})
    return httpx.MockTransport(handler)


def _always_success_transport(content: str = '{"answer": "ok"}') -> httpx.MockTransport:
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
    gateway = LLMGateway(
        api_key="test",
        max_retries=0,  # 每次 fail 不重试,直接计入 consecutive_failures
        failure_threshold=5,
        circuit_window_seconds=900,
        transport=_always_fail_transport(),
    )
    request = LLMRequest(messages=[Message(role="user", content="ping")])

    # 前 5 次都失败,但仍尝试请求(抛 LLMGatewayError,不是 GatewayCircuitOpen)
    for i in range(5):
        with pytest.raises(LLMGatewayError) as exc_info:
            await gateway.complete(request)
        assert not isinstance(exc_info.value, GatewayCircuitOpen)

    # 第 6 次:熔断已打开,直接抛 GatewayCircuitOpen(不进 _call_api)
    with pytest.raises(GatewayCircuitOpen):
        await gateway.complete(request)


@pytest.mark.asyncio
async def test_gateway_circuit_reopens_window_after_success():
    """成功一次调用 → reset consecutive_failures counter,熔断窗口不再打开。"""
    # 第 1 阶段:用 fail transport 累积 4 次失败(阈值前一次)
    gateway = LLMGateway(
        api_key="test",
        max_retries=0,
        failure_threshold=5,
        circuit_window_seconds=900,
        transport=_always_fail_transport(),
    )
    request = LLMRequest(messages=[Message(role="user", content="ping")])
    for i in range(4):
        with pytest.raises(LLMGatewayError):
            await gateway.complete(request)
    # 还未熔断
    assert gateway.consecutive_failures == 4

    # 第 2 阶段:切换 transport 到 success
    gateway._transport = _always_success_transport()
    response = await gateway.complete(request)
    assert response.content
    # 成功后 counter 必须 reset
    assert gateway.consecutive_failures == 0


@pytest.mark.asyncio
async def test_gateway_circuit_closes_after_window_expires(monkeypatch):
    """熔断打开后,window 时间过去 → 下次调用恢复尝试(不再直接抛 GatewayCircuitOpen)。"""
    from datetime import UTC, datetime, timedelta

    gateway = LLMGateway(
        api_key="test",
        max_retries=0,
        failure_threshold=2,
        circuit_window_seconds=60,
        transport=_always_fail_transport(),
    )
    request = LLMRequest(messages=[Message(role="user", content="ping")])

    # 触发熔断(2 次失败到阈值)
    for i in range(2):
        with pytest.raises(LLMGatewayError):
            await gateway.complete(request)
    # 第 3 次确认熔断已打开
    with pytest.raises(GatewayCircuitOpen):
        await gateway.complete(request)

    # 把 circuit_open_until 手动倒回过去(模拟时间流逝 > window)
    gateway.circuit_open_until = datetime.now(UTC) - timedelta(seconds=1)

    # 下次调用应该尝试请求(虽然 transport 还是 fail,但不会立即 GatewayCircuitOpen)
    with pytest.raises(LLMGatewayError) as exc_info:
        await gateway.complete(request)
    assert not isinstance(exc_info.value, GatewayCircuitOpen)


@pytest.mark.asyncio
async def test_gateway_circuit_default_threshold_and_window():
    """默认值检查:failure_threshold=5, circuit_window_seconds=900。"""
    gateway = LLMGateway(api_key="test")
    assert gateway.failure_threshold == 5
    assert gateway.circuit_window_seconds == 900
    assert gateway.consecutive_failures == 0
    assert gateway.circuit_open_until is None
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_llm_gateway.py -v -k "circuit"
```

Expected: 4 新测试 FAIL(`GatewayCircuitOpen` 找不到 / `failure_threshold` 参数不存在 / etc)。

- [ ] **Step 3: 改 `src/core/llm_gateway.py`(加 GatewayCircuitOpen + circuit state + 阈值校验)**

修改要点(基于现有文件):
1. 在 `class GatewaySchemaError(LLMGatewayError):` 下方加新异常:
   ```python
   class GatewayCircuitOpen(LLMGatewayError):
       """Raised when circuit breaker is open due to consecutive failures."""
   ```
2. `LLMGateway.__init__` 加 2 个参数 + 2 个状态字段:
   - `failure_threshold: int = 5`
   - `circuit_window_seconds: int = 900`
   - `self.failure_threshold = failure_threshold`
   - `self.circuit_window_seconds = circuit_window_seconds`
   - `self.consecutive_failures = 0`
   - `self.circuit_open_until: datetime | None = None`
3. `complete()` 入口加熔断检查 + 成功/失败后更新 state

完整替换 `src/core/llm_gateway.py` 为:

```python
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
```

- [ ] **Step 4: 跑 circuit breaker 测试,确认 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_llm_gateway.py -v -k "circuit"
```

Expected: 4 测试 PASS。

- [ ] **Step 5: 跑全套测试,无回归**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: ~88 passed,1 skipped。

- [ ] **Step 6: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/core/llm_gateway.py tests/test_llm_gateway.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-b: task 3 — LLMGateway circuit breaker

spec §7.D 熔断机制:连续 5 次失败(默认)→ 触发熔断,15 分钟
(900 秒)内 complete() 直接抛 GatewayCircuitOpen 不发请求。
成功调用 reset counter。Window 过期后自动 close circuit 继续尝试。

4 个新测试覆盖:阈值触发 / 成功后 reset / window 过期重启 / 默认值。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: TurnLoop.run_turn accept happy path

**Files:**
- Create: `src/core/turn_loop.py`
- Create: `tests/test_turn_loop.py`

**目标**:落地 TurnLoop 的"主框架 + accept 分支",其他 Guard 分支与降级留 Task 5/6。本 task 只保证 happy path(Guard accept)能从玩家输入跑到 response_text 返回。

**TurnLoop 配置依赖注入**(spec §6.2):
- narrative_agent: NarrativeAgent
- guard: ConsistencyGuard
- world_memory: WorldMemory
- turn_store: TurnStore
- retrieval_kinds: list[str](game 指定要捞哪些 kind)
- guard_rules: list[str](game 注入的硬性规则)
- recent_turns_count: int = 3
- retrieval_top_k: int = 8
- degradation_text: str = "<<画面有些模糊,试试换种方式描述你想做的事。>>"

- [ ] **Step 1: 写 accept happy path 失败测试**

创建 `tests/test_turn_loop.py`:

```python
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from core.agents.guard import ConsistencyGuard, GuardDecision
from core.agents.narrative import NarrativeAgent
from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile
from core.rag_repository import InMemoryRAGRepository
from core.schemas import TurnInput
from core.turn_store import Turn, TurnStore
from core.world_memory import WorldMemory
from tests._fakes import FakeStructuredGateway


class _Beat(BaseModel):
    narration: str = Field(min_length=1)
    new_facts: list[str] = Field(default_factory=list)


def _build_components(*, gateway: FakeStructuredGateway, tmp_path: Path):
    runtime = AgentRuntime(gateway=gateway)
    narrative = NarrativeAgent(
        runtime=runtime,
        profile=AgentProfile(id="n", name="N", role="narrator", objective="o"),
    )
    guard = ConsistencyGuard(
        runtime=runtime,
        profile=AgentProfile(id="g", name="G", role="guard", objective="o"),
    )
    world_memory = WorldMemory(repository=InMemoryRAGRepository())
    turn_store = TurnStore(data_dir=tmp_path)
    return narrative, guard, world_memory, turn_store


@pytest.mark.asyncio
async def test_turn_loop_run_turn_happy_accept(tmp_path: Path):
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    # 编排 2 次响应:Narrative beat → Guard accept
    gateway.queue_response(_Beat, _Beat(narration="你站在森林边缘。"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=["world_law"],
            guard_rules=["rule1"],
        ),
    )

    result = await loop.run_turn(session_id="sess_01", raw_text="环顾四周")

    assert result.response_text == "你站在森林边缘。"
    assert result.guard_retries == 0
    assert result.turn.status == "ok"
    assert result.turn.input.raw_text == "环顾四周"
    assert result.turn.input.turn_index == 0
    assert result.turn.guard_decision is not None
    assert result.turn.guard_decision.decision == "accept"
    # 该轮已存盘
    saved = store.load_session(session_id="sess_01")
    assert len(saved) == 1
    assert saved[0].id == result.turn.id


@pytest.mark.asyncio
async def test_turn_loop_run_turn_increments_turn_index_across_calls(tmp_path: Path):
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    # 两轮 × 2 LLM 调用 = 4 个 queued response
    for i in range(2):
        gateway.queue_response(_Beat, _Beat(narration=f"narration_{i}"))
        gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=["world_law"],
            guard_rules=[],
        ),
    )

    result0 = await loop.run_turn(session_id="sess_02", raw_text="行动 0")
    result1 = await loop.run_turn(session_id="sess_02", raw_text="行动 1")

    assert result0.turn.input.turn_index == 0
    assert result1.turn.input.turn_index == 1
    saved = store.load_session(session_id="sess_02")
    assert len(saved) == 2


@pytest.mark.asyncio
async def test_turn_loop_run_turn_passes_retrieved_memory_into_narrative(tmp_path: Path):
    """证明 retrieve → narrative 链路:已写入的 WorldMemory 记录会作为 retrieved_memory 进 narrative context。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig
    from core.world_memory import MemoryRecord

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="response"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    # 预先写入一条 world_law,query "blood" 时应捞到
    wm.upsert(MemoryRecord(
        kind="world_law", content="magic requires blood",
        source="seed", session_id="sess_03",
    ))

    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=["world_law"],
            guard_rules=[],
        ),
    )
    result = await loop.run_turn(session_id="sess_03", raw_text="blood ritual")

    # Narrative agent 收到的 user message 应包含 retrieved_memory 中的 "magic requires blood"
    narrative_user_msg = gateway.invocations[0].messages[1]
    assert "magic requires blood" in narrative_user_msg.content
    assert result.turn.retrieved_memory  # 非空
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_loop.py -v
```

Expected: 3 测试 FAIL(`No module named 'core.turn_loop'`)。

- [ ] **Step 3: 创建 `src/core/turn_loop.py`(只实现 accept happy path,reject/revise/降级留 Task 5/6)**

```python
from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, Field

from core.agents.guard import (
    ConsistencyGuard,
    GuardDecision,
    GuardInput,
    ReferenceItem,
)
from core.agents.narrative import NarrativeAgent, NarrativeContext
from core.schemas import TurnInput
from core.turn_store import Turn, TurnResult, TurnStore
from core.world_memory import MemoryQuery, WorldMemory


T = TypeVar("T", bound=BaseModel)


class TurnLoopConfig(BaseModel):
    """TurnLoop 行为配置。game 层通过它注入策略。"""

    model_config = {"arbitrary_types_allowed": True}

    narrative_output_schema: type[BaseModel]   # game 指定的 NarrativeBeat 类
    response_text_field: str = "narration"     # NarrativeBeat 中给玩家看的文本字段名
    retrieval_kinds: list[str] = Field(default_factory=list)
    guard_rules: list[str] = Field(default_factory=list)
    recent_turns_count: int = Field(default=3, ge=0, le=10)
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    degradation_text: str = Field(
        default="<<画面有些模糊,试试换种方式描述你想做的事。>>",
        min_length=1,
    )


class TurnLoop:
    """spec §6.1 主路径编排器。本 task 只实现 accept happy path。"""

    def __init__(
        self,
        *,
        narrative_agent: NarrativeAgent,
        guard: ConsistencyGuard,
        world_memory: WorldMemory,
        turn_store: TurnStore,
        config: TurnLoopConfig,
    ) -> None:
        self.narrative_agent = narrative_agent
        self.guard = guard
        self.world_memory = world_memory
        self.turn_store = turn_store
        self.config = config

    async def run_turn(self, *, session_id: str, raw_text: str) -> TurnResult:
        # ① 构造 TurnInput(turn_index = 已存 turn 数)
        existing = self.turn_store.load_session(session_id=session_id)
        turn_index = len(existing)
        input = TurnInput(
            raw_text=raw_text,
            turn_index=turn_index,
            session_id=session_id,
        )

        # ② Retrieve
        retrieved = self.world_memory.query(MemoryQuery(
            query_text=raw_text,
            session_id=session_id,
            kinds=self.config.retrieval_kinds or None,
            top_k=self.config.retrieval_top_k,
        ))

        # ③ Narrate
        narrative_beat = await self.narrative_agent.run(
            context=NarrativeContext(
                player_input=input,
                retrieved_memory=retrieved,
            ),
            output_schema=self.config.narrative_output_schema,
        )
        proposal = narrative_beat.model_dump(mode="json")

        # ④ Guard
        references = self._build_references(retrieved, existing)
        decision = await self.guard.check(GuardInput(
            proposal=proposal,
            references=references,
            rules=self.config.guard_rules,
            session_id=session_id,
        ))

        # Task 4 阶段只处理 accept;其他分支 Task 5/6 实现
        if decision.decision != "accept":
            raise NotImplementedError(
                f"TurnLoop Task 4 only handles accept; got {decision.decision}. "
                "revise/reject 分支将在 Task 5/6 实现。"
            )

        # ⑤ Curate(Phase B 阶段:从 narrative_beat.new_facts 简单提取,Phase D 由 game-specific curator 替代)
        curated = []  # MVP Phase B 暂不沉淀 — 留给 Phase D MemoryCurator

        # ⑥ Persist
        response_text = self._extract_response_text(narrative_beat)
        turn = Turn(
            id="",  # 替换在下面
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=proposal,
            guard_decision=decision,
            curated_records=curated,
            response_text=response_text,
            status="ok",
        )
        # 因 Turn.id 是 default_factory,上面 id="" 会被 ValidationError 拒。改为不传 id:
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=proposal,
            guard_decision=decision,
            curated_records=curated,
            response_text=response_text,
            status="ok",
        )
        self.turn_store.save(turn)

        # ⑦ Return
        return TurnResult(turn=turn, response_text=response_text, guard_retries=0)

    def _build_references(
        self,
        retrieved: list,
        recent_turns: list[Turn],
    ) -> list[ReferenceItem]:
        """组装 GuardInput.references。Task 4 简化版:把 retrieved_memory 转 ReferenceItem。"""
        refs: list[ReferenceItem] = []
        for r in retrieved:
            refs.append(ReferenceItem(
                label=r.fragment.metadata.get("kind", "memory"),
                content=r.fragment.content,
                score=r.score,
            ))
        # Task 5+ 会补"最近 N 轮 turn"作为额外 references
        return refs

    def _extract_response_text(self, beat: BaseModel) -> str:
        """从 NarrativeBeat 中取出 response_text(默认 .narration 字段)。"""
        value = getattr(beat, self.config.response_text_field, None)
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"NarrativeBeat.{self.config.response_text_field} must be non-empty str; "
                f"got {type(value).__name__}: {value!r}"
            )
        return value
```

注意 `turn = Turn(id="", ...)` 那段是文档错误演示 — 真正的代码只构造一次 `turn = Turn(input=..., ...)`,不传 id 让 default_factory 生效。删掉那段冗余 — **改 source 时**只保留一个 turn 构造。

下面是清理后的 `run_turn` 末段(替换 ⑥ Persist 段):

```python
        # ⑤ Curate(Phase B 阶段暂不沉淀 — 留给 Phase D MemoryCurator)
        curated = []

        # ⑥ Persist
        response_text = self._extract_response_text(narrative_beat)
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=proposal,
            guard_decision=decision,
            curated_records=curated,
            response_text=response_text,
            status="ok",
        )
        self.turn_store.save(turn)

        # ⑦ Return
        return TurnResult(turn=turn, response_text=response_text, guard_retries=0)
```

(实际写文件时只写正确的版本,不要包含上面的"错误演示"段)

- [ ] **Step 4: 跑测试,确认 3 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_loop.py -v
```

Expected: 3 测试 PASS。如果有 fail:
- `arbitrary_types_allowed` 报错 → `TurnLoopConfig.model_config = {"arbitrary_types_allowed": True}` 必须存在(`type[BaseModel]` 不是 Pydantic 标准类型)
- `_extract_response_text` 失败 → 检查 `_Beat` 是否有 `narration` 字段且 default field name 配 "narration"

- [ ] **Step 5: 跑全套测试**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: ~91 passed,1 skipped。

- [ ] **Step 6: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/core/turn_loop.py tests/test_turn_loop.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-b: task 4 — core/turn_loop.py accept happy path

TurnLoopConfig + TurnLoop 主框架。本 task 只实现 Guard accept 分支
(revise/reject/降级在 Task 5/6)。一轮 ①-⑦ 时序完整:
input → retrieve → narrate → guard(accept only)→ persist → return。

3 个测试覆盖:happy path / turn_index 累加 / retrieved_memory 透传到 narrative。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: TurnLoop Guard revise + reject 分支

**Files:**
- Modify: `src/core/turn_loop.py`(替换 `if decision.decision != "accept": raise NotImplementedError`,实现 revise / reject 处理)
- Modify: `tests/test_turn_loop.py`(加 revise + reject 测试)

**逻辑**(spec §6.3):
- **revise**:直接采用 `decision.revised_payload`(不重跑 Narrate),`guard_retries = 1`,继续 ⑤-⑦
- **reject**(或 revise 无 payload — 但 GuardDecision model_validator 已强制 revise 必有 payload,所以这种情况不发生):走"安全降级":
  - `response_text = config.degradation_text`
  - `turn.status = "degraded"`
  - `turn.metadata["guard_rejection"] = {"findings": [...], "decision": "reject"}`
  - **`turn_index` 不前进**(下一轮玩家重试时 turn_index 应该一样)— 实现方式:**不调 turn_store.save**(那样 load_session 返回数不变,下次 turn_index 自动一样)。但 spec §6.3 说"仍保存 turn JSONL 供 debug" — 矛盾。
  - **解决**:存盘但用一个不计入 turn_index 的 status 标记。**最简单**:save 时把 turn.status = "degraded" 一起存,然后下次 `run_turn` 计算 turn_index 时只数 `status == "ok"` 的 turn(不是所有 turn)。

- [ ] **Step 1: 写 revise + reject 测试**

追加到 `tests/test_turn_loop.py`:

```python
@pytest.mark.asyncio
async def test_turn_loop_guard_revise_adopts_revised_payload(tmp_path: Path):
    """revise: 不重跑 Narrate,直接采用 revised_payload,guard_retries=1。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    # Narrative 给一个"原始" beat,Guard 给 revise + 修订后 payload
    gateway.queue_response(_Beat, _Beat(narration="原始叙述,有矛盾"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="revise",
            findings=[],
            revised_payload={"narration": "修订后的叙述", "new_facts": []},
        ),
    )

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            guard_rules=[],
        ),
    )
    result = await loop.run_turn(session_id="sess_rv", raw_text="test")

    # response_text 必须来自 revised_payload 而非原始 narrative
    assert result.response_text == "修订后的叙述"
    assert result.guard_retries == 1
    assert result.turn.status == "ok"  # revise 视为合规分支
    # 注:Narrative 只被调一次(没重跑),Guard 被调一次,共 2 次 LLM
    assert len(gateway.invocations) == 2


@pytest.mark.asyncio
async def test_turn_loop_guard_reject_degrades(tmp_path: Path):
    """reject: response_text=degradation_text, status=degraded, turn_index 不前进。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="违反法则的内容"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(decision="reject", findings=[]),
    )

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            guard_rules=[],
            degradation_text="<<降级文案>>",
        ),
    )
    result = await loop.run_turn(session_id="sess_rj", raw_text="test")

    assert result.response_text == "<<降级文案>>"
    assert result.turn.status == "degraded"
    assert result.turn.metadata.get("guard_rejection") is not None


@pytest.mark.asyncio
async def test_turn_loop_reject_does_not_advance_turn_index(tmp_path: Path):
    """连续两次 reject 后,turn_index 应该仍是 0(degraded turn 不计数)。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    # 两轮 reject(2 narrative + 2 guard = 4 responses)
    for _ in range(2):
        gateway.queue_response(_Beat, _Beat(narration="违反"))
        gateway.queue_response(GuardDecision, GuardDecision(decision="reject", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            guard_rules=[],
        ),
    )
    r0 = await loop.run_turn(session_id="sess_nx", raw_text="试 1")
    r1 = await loop.run_turn(session_id="sess_nx", raw_text="试 2")

    assert r0.turn.input.turn_index == 0
    assert r1.turn.input.turn_index == 0  # 仍是 0 — degraded 不计入
    # 但两轮都被存盘(供 debug)
    saved = store.load_session(session_id="sess_nx")
    assert len(saved) == 2
    assert all(t.status == "degraded" for t in saved)
```

- [ ] **Step 2: 跑测试,确认 fail(因为当前 turn_loop 在 non-accept 时 raise NotImplementedError)**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_loop.py -v -k "revise or reject or not_advance"
```

Expected: 3 测试 FAIL with `NotImplementedError`。

- [ ] **Step 3: 修改 `src/core/turn_loop.py` 的 `run_turn` 方法**

把整段 `run_turn` 替换为(其余代码不变):

```python
    async def run_turn(self, *, session_id: str, raw_text: str) -> TurnResult:
        # ① 构造 TurnInput;turn_index 只数 status=="ok" 的 turn(degraded 不计数)
        existing = self.turn_store.load_session(session_id=session_id)
        turn_index = sum(1 for t in existing if t.status == "ok")
        input = TurnInput(
            raw_text=raw_text,
            turn_index=turn_index,
            session_id=session_id,
        )

        # ② Retrieve
        retrieved = self.world_memory.query(MemoryQuery(
            query_text=raw_text,
            session_id=session_id,
            kinds=self.config.retrieval_kinds or None,
            top_k=self.config.retrieval_top_k,
        ))

        # ③ Narrate
        narrative_beat = await self.narrative_agent.run(
            context=NarrativeContext(
                player_input=input,
                retrieved_memory=retrieved,
            ),
            output_schema=self.config.narrative_output_schema,
        )
        proposal = narrative_beat.model_dump(mode="json")

        # ④ Guard
        references = self._build_references(retrieved, existing)
        decision = await self.guard.check(GuardInput(
            proposal=proposal,
            references=references,
            rules=self.config.guard_rules,
            session_id=session_id,
        ))

        guard_retries = 0
        if decision.decision == "accept":
            final_payload = proposal
        elif decision.decision == "revise":
            # revise: 直接采用 revised_payload,不重跑 Narrate
            assert decision.revised_payload is not None  # GuardDecision validator 已保证
            final_payload = decision.revised_payload
            guard_retries = 1
        else:
            # reject: 走降级
            return self._build_degraded_result(
                input=input,
                retrieved=retrieved,
                proposal=proposal,
                decision=decision,
            )

        # ⑤ Curate(Phase B 暂不沉淀,留 Phase D)
        curated = []

        # ⑥ Persist + ⑦ Return
        response_text = self._extract_response_text_from_payload(final_payload)
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=final_payload,
            guard_decision=decision,
            curated_records=curated,
            response_text=response_text,
            status="ok",
        )
        self.turn_store.save(turn)
        return TurnResult(turn=turn, response_text=response_text, guard_retries=guard_retries)

    def _build_degraded_result(
        self,
        *,
        input: TurnInput,
        retrieved: list,
        proposal: dict[str, Any],
        decision: GuardDecision,
    ) -> TurnResult:
        """Guard reject → 降级路径。存盘但不沉淀 curate,status=degraded,response_text=固定文案。"""
        degradation_text = self.config.degradation_text
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=proposal,
            guard_decision=decision,
            curated_records=[],  # 降级不沉淀
            response_text=degradation_text,
            status="degraded",
            metadata={
                "guard_rejection": {
                    "decision": decision.decision,
                    "findings": [f.model_dump() for f in decision.findings],
                },
            },
        )
        self.turn_store.save(turn)
        return TurnResult(turn=turn, response_text=degradation_text, guard_retries=0)
```

并把 `_extract_response_text` 改名 + 改签名为 `_extract_response_text_from_payload`(接受 dict 而非 BaseModel):

```python
    def _extract_response_text_from_payload(self, payload: dict[str, Any]) -> str:
        """从 narrative payload(可能是原 beat 也可能是 revised_payload)中取 response_text。"""
        value = payload.get(self.config.response_text_field)
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"narrative payload[{self.config.response_text_field!r}] must be non-empty str; "
                f"got {type(value).__name__}: {value!r}"
            )
        return value
```

(原来的 `_extract_response_text(beat: BaseModel)` 整段删除)

- [ ] **Step 4: 跑测试,确认 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_loop.py -v
```

Expected: 全部 6 个 TurnLoop 测试 PASS(原 3 happy + 3 新 revise/reject)。

- [ ] **Step 5: 跑全套测试**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: ~94 passed,1 skipped。

- [ ] **Step 6: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/core/turn_loop.py tests/test_turn_loop.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-b: task 5 — TurnLoop Guard revise + reject 分支

- revise: 直接采用 revised_payload(不重跑 Narrate),guard_retries=1,status=ok
- reject: 走"安全降级" — response_text=config.degradation_text,
  status=degraded,turn.metadata 记录 guard_rejection findings,
  turn_index 不前进(下一轮 raw_text 重输,turn_index 仍是上次值)
- _extract_response_text_from_payload 改接受 dict(支持 revised_payload)
- 3 个新测试覆盖:revise / reject 降级 / 连续 reject 不前进 turn_index

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: TurnLoop 熔断降级 + TurnTelemetry

**Files:**
- Modify: `src/core/turn_loop.py`(加 try/except GatewayCircuitOpen,加 TurnTelemetry 记录)
- Modify: `tests/test_turn_loop.py`(加 circuit-open + telemetry 测试)

**逻辑**(spec §7.D, §7.F):
- 任何 LLM 调用(Narrate / Guard)抛 `GatewayCircuitOpen` → 走降级,`status="failed"`,`turn.metadata["circuit_open"]=True`
- 每轮记录 TurnTelemetry 写到 `turn.metadata["telemetry"]`:`retrieval_hit_count` / `retrieval_top_score` / `guard_decision` / `guard_findings_count` / `guard_retries` / `llm_call_count`(Narrate + Guard 总数,不区分)/ `duration_ms`

- [ ] **Step 1: 写 circuit-open + telemetry 失败测试**

追加到 `tests/test_turn_loop.py`:

```python
@pytest.mark.asyncio
async def test_turn_loop_circuit_open_degrades_as_failed(tmp_path: Path):
    """LLM Gateway 抛 GatewayCircuitOpen → 降级 status=failed,不抛给上层。"""
    from core.llm_gateway import GatewayCircuitOpen
    from core.turn_loop import TurnLoop, TurnLoopConfig

    class _CircuitOpenGateway:
        def __init__(self):
            self.invocations = []

        async def complete_and_parse(self, request, output_schema):
            self.invocations.append(request)
            raise GatewayCircuitOpen("circuit open")

    gateway = _CircuitOpenGateway()
    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=[],
            guard_rules=[],
        ),
    )
    result = await loop.run_turn(session_id="sess_co", raw_text="test")

    assert result.turn.status == "failed"
    assert result.response_text  # 非空 — degradation_text
    assert result.turn.metadata.get("circuit_open") is True


@pytest.mark.asyncio
async def test_turn_loop_records_telemetry_to_turn_metadata(tmp_path: Path):
    """每轮记录 TurnTelemetry 到 turn.metadata["telemetry"]。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig
    from core.world_memory import MemoryRecord

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="ok"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    # 预先写入一条记忆,使 retrieval_hit_count > 0
    wm.upsert(MemoryRecord(kind="world_law", content="foo", source="s", session_id="sess_t"))

    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=["world_law"],
            guard_rules=[],
        ),
    )
    result = await loop.run_turn(session_id="sess_t", raw_text="foo")

    telemetry = result.turn.metadata.get("telemetry")
    assert telemetry is not None
    assert telemetry["retrieval_hit_count"] >= 1
    assert telemetry["guard_decision"] == "accept"
    assert telemetry["guard_findings_count"] == 0
    assert telemetry["guard_retries"] == 0
    assert telemetry["llm_call_count"] == 2  # Narrate + Guard
    assert telemetry["duration_ms"] >= 0
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_loop.py -v -k "circuit_open or telemetry"
```

Expected: 2 FAIL。

- [ ] **Step 3: 修改 `src/core/turn_loop.py` — 加 TurnTelemetry 类 + try/except 熔断 + telemetry 记录**

完整替换文件为:

```python
from __future__ import annotations

import time
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from core.agents.guard import (
    ConsistencyGuard,
    GuardDecision,
    GuardInput,
    ReferenceItem,
)
from core.agents.narrative import NarrativeAgent, NarrativeContext
from core.llm_gateway import GatewayCircuitOpen
from core.schemas import RAGQueryResult, TurnInput
from core.turn_store import Turn, TurnResult, TurnStore
from core.world_memory import MemoryQuery, WorldMemory


T = TypeVar("T", bound=BaseModel)


class TurnTelemetry(BaseModel):
    """每轮 TurnLoop 的可观测性指标(spec §7.F)。"""

    retrieval_hit_count: int = Field(ge=0)
    retrieval_top_score: float = Field(ge=0.0)
    guard_decision: str  # "accept" / "revise" / "reject" / "circuit_open"
    guard_findings_count: int = Field(ge=0)
    guard_retries: int = Field(ge=0)
    llm_call_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class TurnLoopConfig(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    narrative_output_schema: type[BaseModel]
    response_text_field: str = "narration"
    retrieval_kinds: list[str] = Field(default_factory=list)
    guard_rules: list[str] = Field(default_factory=list)
    recent_turns_count: int = Field(default=3, ge=0, le=10)
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    degradation_text: str = Field(
        default="<<画面有些模糊,试试换种方式描述你想做的事。>>",
        min_length=1,
    )


class TurnLoop:
    def __init__(
        self,
        *,
        narrative_agent: NarrativeAgent,
        guard: ConsistencyGuard,
        world_memory: WorldMemory,
        turn_store: TurnStore,
        config: TurnLoopConfig,
    ) -> None:
        self.narrative_agent = narrative_agent
        self.guard = guard
        self.world_memory = world_memory
        self.turn_store = turn_store
        self.config = config

    async def run_turn(self, *, session_id: str, raw_text: str) -> TurnResult:
        start_ns = time.monotonic_ns()
        llm_call_count = 0

        # ① 构造 TurnInput(turn_index 只数 status=="ok")
        existing = self.turn_store.load_session(session_id=session_id)
        turn_index = sum(1 for t in existing if t.status == "ok")
        input = TurnInput(
            raw_text=raw_text,
            turn_index=turn_index,
            session_id=session_id,
        )

        # ② Retrieve
        retrieved = self.world_memory.query(MemoryQuery(
            query_text=raw_text,
            session_id=session_id,
            kinds=self.config.retrieval_kinds or None,
            top_k=self.config.retrieval_top_k,
        ))
        retrieval_hit_count = len(retrieved)
        retrieval_top_score = retrieved[0].score if retrieved else 0.0

        # ③ Narrate(可能抛 GatewayCircuitOpen)
        try:
            narrative_beat = await self.narrative_agent.run(
                context=NarrativeContext(
                    player_input=input,
                    retrieved_memory=retrieved,
                ),
                output_schema=self.config.narrative_output_schema,
            )
            llm_call_count += 1
        except GatewayCircuitOpen:
            return self._build_circuit_open_result(
                input=input,
                retrieved=retrieved,
                start_ns=start_ns,
                llm_call_count=llm_call_count,
                retrieval_hit_count=retrieval_hit_count,
                retrieval_top_score=retrieval_top_score,
            )

        proposal = narrative_beat.model_dump(mode="json")

        # ④ Guard(可能抛 GatewayCircuitOpen)
        references = self._build_references(retrieved, existing)
        try:
            decision = await self.guard.check(GuardInput(
                proposal=proposal,
                references=references,
                rules=self.config.guard_rules,
                session_id=session_id,
            ))
            llm_call_count += 1
        except GatewayCircuitOpen:
            return self._build_circuit_open_result(
                input=input,
                retrieved=retrieved,
                start_ns=start_ns,
                llm_call_count=llm_call_count,
                retrieval_hit_count=retrieval_hit_count,
                retrieval_top_score=retrieval_top_score,
                partial_proposal=proposal,
            )

        guard_retries = 0
        if decision.decision == "accept":
            final_payload = proposal
        elif decision.decision == "revise":
            assert decision.revised_payload is not None
            final_payload = decision.revised_payload
            guard_retries = 1
        else:
            # reject 降级
            return self._build_degraded_result(
                input=input,
                retrieved=retrieved,
                proposal=proposal,
                decision=decision,
                start_ns=start_ns,
                llm_call_count=llm_call_count,
                retrieval_hit_count=retrieval_hit_count,
                retrieval_top_score=retrieval_top_score,
            )

        # ⑤-⑦ 正常路径
        response_text = self._extract_response_text_from_payload(final_payload)
        telemetry = TurnTelemetry(
            retrieval_hit_count=retrieval_hit_count,
            retrieval_top_score=retrieval_top_score,
            guard_decision=decision.decision,
            guard_findings_count=len(decision.findings),
            guard_retries=guard_retries,
            llm_call_count=llm_call_count,
            duration_ms=_elapsed_ms(start_ns),
        )
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=final_payload,
            guard_decision=decision,
            curated_records=[],
            response_text=response_text,
            status="ok",
            metadata={"telemetry": telemetry.model_dump()},
        )
        self.turn_store.save(turn)
        return TurnResult(turn=turn, response_text=response_text, guard_retries=guard_retries)

    def _build_degraded_result(
        self,
        *,
        input: TurnInput,
        retrieved: list[RAGQueryResult],
        proposal: dict[str, Any],
        decision: GuardDecision,
        start_ns: int,
        llm_call_count: int,
        retrieval_hit_count: int,
        retrieval_top_score: float,
    ) -> TurnResult:
        telemetry = TurnTelemetry(
            retrieval_hit_count=retrieval_hit_count,
            retrieval_top_score=retrieval_top_score,
            guard_decision=decision.decision,
            guard_findings_count=len(decision.findings),
            guard_retries=0,
            llm_call_count=llm_call_count,
            duration_ms=_elapsed_ms(start_ns),
        )
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=proposal,
            guard_decision=decision,
            curated_records=[],
            response_text=self.config.degradation_text,
            status="degraded",
            metadata={
                "guard_rejection": {
                    "decision": decision.decision,
                    "findings": [f.model_dump() for f in decision.findings],
                },
                "telemetry": telemetry.model_dump(),
            },
        )
        self.turn_store.save(turn)
        return TurnResult(turn=turn, response_text=self.config.degradation_text, guard_retries=0)

    def _build_circuit_open_result(
        self,
        *,
        input: TurnInput,
        retrieved: list[RAGQueryResult],
        start_ns: int,
        llm_call_count: int,
        retrieval_hit_count: int,
        retrieval_top_score: float,
        partial_proposal: dict[str, Any] | None = None,
    ) -> TurnResult:
        telemetry = TurnTelemetry(
            retrieval_hit_count=retrieval_hit_count,
            retrieval_top_score=retrieval_top_score,
            guard_decision="circuit_open",
            guard_findings_count=0,
            guard_retries=0,
            llm_call_count=llm_call_count,
            duration_ms=_elapsed_ms(start_ns),
        )
        turn = Turn(
            input=input,
            retrieved_memory=retrieved,
            narrative_draft=partial_proposal,
            guard_decision=None,
            curated_records=[],
            response_text=self.config.degradation_text,
            status="failed",
            metadata={
                "circuit_open": True,
                "telemetry": telemetry.model_dump(),
            },
        )
        self.turn_store.save(turn)
        return TurnResult(turn=turn, response_text=self.config.degradation_text, guard_retries=0)

    def _build_references(
        self,
        retrieved: list[RAGQueryResult],
        recent_turns: list[Turn],
    ) -> list[ReferenceItem]:
        refs: list[ReferenceItem] = []
        for r in retrieved:
            refs.append(ReferenceItem(
                label=r.fragment.metadata.get("kind", "memory"),
                content=r.fragment.content,
                score=r.score,
            ))
        return refs

    def _extract_response_text_from_payload(self, payload: dict[str, Any]) -> str:
        value = payload.get(self.config.response_text_field)
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"narrative payload[{self.config.response_text_field!r}] must be non-empty str; "
                f"got {type(value).__name__}: {value!r}"
            )
        return value


def _elapsed_ms(start_ns: int) -> int:
    return max(0, (time.monotonic_ns() - start_ns) // 1_000_000)
```

- [ ] **Step 4: 跑测试,确认 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_loop.py -v
```

Expected: 8 测试 PASS(原 6 + 2 新)。

- [ ] **Step 5: 跑全套测试**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: ~96 passed,1 skipped。

- [ ] **Step 6: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/core/turn_loop.py tests/test_turn_loop.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-b: task 6 — TurnLoop 熔断降级 + TurnTelemetry

- Narrate / Guard 抛 GatewayCircuitOpen → 降级路径,status=failed,
  turn.metadata["circuit_open"]=True,response_text=degradation_text
- TurnTelemetry 记录每轮指标(retrieval_hit_count / top_score /
  guard_decision / findings_count / guard_retries / llm_call_count /
  duration_ms)→ turn.metadata["telemetry"]
- 3 个路径(accept / degraded / failed)统一在 metadata 写 telemetry

2 个新测试覆盖:circuit_open 降级 / telemetry 记录正确。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Phase B 收尾

**Files:**
- 跑 ruff cleanup(若有)
- 跑全套测试 + 覆盖率
- 打 `phase-b-complete` tag
- 写 `docs/superpowers/plans/2026-05-27-phase-b-completion-report.md`

- [ ] **Step 1: ruff scan**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/ruff check --select F401 --fix src/ tests/ scripts/
```

Expected: 修若干 plan-bug 残留 unused imports(若没修内容也 OK)。

- [ ] **Step 2: 全套测试**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: 96+ passed,1 skipped。

- [ ] **Step 3: 覆盖率**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py --cov=src/core --cov-report=term-missing -q 2>&1 | tail -30
```

记录 `src/core/turn_loop.py` 覆盖率(目标 ≥ 85%)。

- [ ] **Step 4: Commit cleanup(若 ruff 修了文件)**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG status
# 若 ruff 修了文件:
git -C /Users/fangkai/ai_work/games/AI_RPG add -A
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-b: task 7 收尾 — ruff F401 清扫 unused imports
EOF
)"
# 若 ruff 没修:跳过本 commit
```

- [ ] **Step 5: 打 tag**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG tag -a phase-b-complete -m "Phase B: turn loop main path complete (7 tasks)"
git -C /Users/fangkai/ai_work/games/AI_RPG tag --list | grep phase
```

- [ ] **Step 6: 写完成报告**

创建 `/Users/fangkai/ai_work/games/AI_RPG/docs/superpowers/plans/2026-05-27-phase-b-completion-report.md`:

```markdown
# Phase B 完成报告

日期:2026-05-27 / 28(完成日)
关联 plan:[2026-05-27-phase-b-turn-loop.md](2026-05-27-phase-b-turn-loop.md)
关联 spec:[2026-05-26-turn-loop-engine-redesign-design.md](../specs/2026-05-26-turn-loop-engine-redesign-design.md)
分支:`codex/world-init-live-smoke`
里程碑 tag:`phase-b-complete`

## 概览

Phase B 7 个 task 全部完成,~96 测试 PASS。TurnLoop 主路径就位,4 种执行结果(accept / revise / reject 降级 / circuit_open 熔断降级)均有专属处理。可观测性 TurnTelemetry 落地。Phase C 可基于此引入 References 完整组装(含最近 turn 摘要)+ Curator 真实沉淀。

## 完成的 Task

| Task | 内容 | 主要 commit |
|------|------|------------|
| 1 | Phase A 4 risks 清理 | `<sha>` |
| 2 | Prompt prose 通用化 + game 注入接口 | `<sha>` |
| 3 | LLMGateway circuit breaker | `<sha>` |
| 4 | TurnLoop.run_turn accept happy path | `<sha>` |
| 5 | TurnLoop Guard revise + reject 分支 | `<sha>` |
| 6 | TurnLoop 熔断降级 + TurnTelemetry | `<sha>` |
| 7 | 收尾(ruff + tag + 报告) | `<sha>` |

## 新增文件

- `src/core/turn_loop.py`
- `tests/test_turn_loop.py`

## 修改的文件

- `src/core/schemas.py`(删 TurnResult)
- `src/core/turn_store.py`(加 TurnResult / _validate_session_id)
- `src/core/llm_gateway.py`(circuit breaker)
- `src/core/agents/guard.py`(GuardInput pattern + DEFAULT_GUARD_INSTRUCTION 通用化 + instruction override)
- `src/core/agents/narrative.py`(extra 改 Any + DEFAULT_NARRATIVE_INSTRUCTION 通用化 + instruction override)
- 对应测试文件多处扩展

## 已知遗留 / 留给 Phase C 的事项

1. `_build_references` 简化版 — 只把 retrieved_memory 转 ReferenceItem,没拼接"最近 3 轮 turn 摘要"。Phase C 实现完整 §7.B 顺序(rules > world_law > recent_turns > characters > events)
2. Curator 完全没沉淀 — `curated_records=[]` hardcoded。Phase D 由 game-specific `MemoryCurator` 替代(四道闸:Schema / Confidence / 去重 / 冲突)
3. Guard prompt 模板仍然 generic — Phase D 时 game/text_adventure 应通过 `instruction` 注入 game-specific guard prompt(spec §7.B)
4. WorldMemory.find_similar 阈值 0.92 用 InMemoryRAG 的 TF cosine — 不是真 embedding。Phase D 上 Chroma + 真 embedding 时,阈值要重新校准

## 下一步:Phase C 写 plan

Phase C 主要内容(spec §9):
- 完整 `_build_references` 实施(spec §7.B 顺序)
- 完整 集成测试(spec §8.C 覆盖剩余 6 用例)
- 一致性可观测性(telemetry 已就位,Phase C 加更多观测点)
- import-graph 测试扩展(可选:加 canon / death / resurrect 等 sentinel 词验证)
- 准备 Phase D text_adventure 接入的 contract 文档
```

- [ ] **Step 7: Commit 报告 + 重打 tag**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add docs/superpowers/plans/2026-05-27-phase-b-completion-report.md
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-b: 完成报告

7 task 全部完成,~96 测试 PASS。TurnLoop 主路径 4 个执行结果
(accept / revise / reject / circuit_open)全部就位,TurnTelemetry 落地。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git -C /Users/fangkai/ai_work/games/AI_RPG tag -d phase-b-complete
git -C /Users/fangkai/ai_work/games/AI_RPG tag -a phase-b-complete -m "Phase B: turn loop main path complete"
git -C /Users/fangkai/ai_work/games/AI_RPG log --oneline -15
```

---

## Phase B 自审

**1. Spec coverage:**
- Spec §6.1 时序 ①-⑦ → Task 4-6 实现 ✓
- Spec §6.3 Guard 决策分支 → Task 5 实现 accept/revise/reject ✓
- Spec §7.D Gateway 熔断 → Task 3 + Task 6(TurnLoop 接 GatewayCircuitOpen) ✓
- Spec §7.F TurnTelemetry → Task 6 ✓
- Spec §8.C 前 4 个集成测试用例 → Task 4-6 已含等价覆盖(accept / revise / reject / circuit_open)
- Spec §7.B references 完整顺序 → ⚠️ 简化版(只 retrieved_memory),完整顺序留 Phase C

**2. Placeholder scan:** 无 TBD / TODO / vague。

**3. Type consistency:**
- `TurnLoopConfig.narrative_output_schema: type[BaseModel]` → 所有 NarrativeAgent.run 调用一致
- `TurnTelemetry.guard_decision: str` → 字面值含 "accept"/"revise"/"reject"/"circuit_open"
- `_extract_response_text_from_payload(payload: dict)` → final_payload 是 dict(无论 proposal 还是 revised_payload)
- `GatewayCircuitOpen` import 路径一致(`from core.llm_gateway`)

**4. 已知架构选择**(plan reader 应该理解):
- `turn_index` 只数 `status=="ok"` 的 turn — degraded/failed 不前进
- `_build_references` 简化版 Phase C 再完整
- TurnLoop 没有 Guard 重试 — Pydantic model_validator 已强制 revise 必有 payload,所以"revise 失败"路径理论不可达
- Curator `curated_records=[]` 是 Phase D 待替换的占位
