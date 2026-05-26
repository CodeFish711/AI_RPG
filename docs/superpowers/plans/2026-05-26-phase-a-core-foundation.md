# Phase A: Core Schema Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 Turn Loop Engine 重设计的 Phase A — core 层数据契约收敛 + 5 个核心组件(WorldMemory / Guard / Narrative / TurnStore + FakeGateway 测试工具)的接口与基本实现就位,全部单元测试通过。Phase A 不接入 LLM 真实调用、不实现 TurnLoop 主路径,只做底座。

**Architecture:** core 层按"数据契约 → 测试基础设施 → 组件骨架"顺序落地。`Turn` 类放在 `core/turn_store.py`(依赖 `GuardDecision` + `MemoryRecord`),避免 `core/schemas.py` 循环引用。所有 LLM 相关组件用 `FakeStructuredGateway` 走通,无需 MIMO API key。

**Tech Stack:** Python 3.11+, Pydantic 2.7+, pytest, pytest-asyncio(已配)。无新依赖。

**Spec 引用:** [docs/superpowers/specs/2026-05-26-turn-loop-engine-redesign-design.md](../specs/2026-05-26-turn-loop-engine-redesign-design.md) §5 / §9 Phase A

---

## File Structure

| 文件 | 类型 | 职责 |
|------|------|------|
| `src/core/schemas.py` | 修改 | 删 TickEvent / SimulationNode;加 TurnInput / TurnResult |
| `tests/test_core_schemas.py` | 修改 | 加 TurnInput / TurnResult 边界值测试;删旧 schema 引用(若有) |
| `tests/_fakes.py` | 新建 | `FakeStructuredGateway`:测试用 LLM gateway,按 schema 返回预编排响应 |
| `tests/test_fakes.py` | 新建 | 验证 FakeStructuredGateway 行为本身 |
| `src/core/agents/guard.py` | 新建 | `GuardFinding` / `GuardDecision` / `ReferenceItem` / `GuardInput` / `ConsistencyGuard` |
| `tests/test_core_agents_guard.py` | 新建 | Guard schema 边界 + ConsistencyGuard.check 基本流程 |
| `src/core/world_memory.py` | 新建 | `MemoryRecord` / `MemoryQuery` / `WorldMemory` |
| `tests/test_world_memory.py` | 新建 | MemoryRecord 边界 + WorldMemory query/upsert 行为 |
| `src/core/turn_store.py` | 新建 | `Turn`(整轮快照,含 GuardDecision / MemoryRecord 引用)+ `TurnStore` JSONL 存盘 |
| `tests/test_turn_store.py` | 新建 | Turn 序列化往返 + TurnStore.save/load_recent |
| `src/core/agents/narrative.py` | 新建 | `NarrativeContext` / `NarrativeAgent`(AgentRuntime 的泛型薄封装) |
| `tests/test_core_agents_narrative.py` | 新建 | NarrativeAgent.run 用 FakeGateway 走通基本流程 |
| `tests/test_import_graph.py` | 新建 | 静态校验 core/* 不 import game/*;core/* 文件文本不含游戏域名词 |

**Phase A 不涉及的文件**(Phase B-E 处理):`core/turn_loop.py`、`game/text_adventure/*`、`game/world_init/*` 的物理移动、`main.py` 改写。

---

## Pre-Task: 环境核对(2 分钟)

- [ ] **Step 1: 确认在 AI_RPG 仓库根目录**

```bash
pwd
```

Expected: `/Users/fangkai/ai_work/games/AI_RPG`

- [ ] **Step 2: 确认 venv 激活,pytest 可用**

```bash
.venv/bin/pytest --version
```

Expected: `pytest 8.x.x`(或更高)。若失败:`python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev,rag]"`

- [ ] **Step 3: 确认当前所有测试基线通过**

```bash
.venv/bin/pytest -q
```

Expected: 全部 PASS(若有 fail,先记录基线,本 plan 不引入新 fail)。

---

## Task 1: `core/schemas.py` 收敛

**Files:**
- Modify: `src/core/schemas.py`(删 TickEvent + SimulationNode,加 TurnInput + TurnResult)
- Modify: `tests/test_core_schemas.py`(加 TurnInput + TurnResult 测试)

- [ ] **Step 1: 写 TurnInput 失败测试**

追加到 `tests/test_core_schemas.py` 末尾:

```python
def test_turn_input_requires_non_empty_raw_text():
    from core.schemas import TurnInput

    with pytest.raises(ValidationError):
        TurnInput(raw_text="", turn_index=0, session_id="s1")


def test_turn_input_requires_non_negative_turn_index():
    from core.schemas import TurnInput

    with pytest.raises(ValidationError):
        TurnInput(raw_text="hello", turn_index=-1, session_id="s1")


def test_turn_input_accepts_minimal_valid_payload():
    from core.schemas import TurnInput

    turn_input = TurnInput(raw_text="look around", turn_index=0, session_id="s1")
    assert turn_input.raw_text == "look around"
    assert turn_input.intent_hint is None


def test_turn_result_defaults_guard_retries_to_zero():
    from core.schemas import TurnInput, TurnResult

    turn_input = TurnInput(raw_text="x", turn_index=0, session_id="s1")
    # 此测试在 Task 4 Turn 类就位后才能完整跑通(需要 Turn 实例)。
    # Phase A 阶段只验证 TurnResult schema 字段存在,先用占位 dict:
    from core.schemas import TurnResult
    # 不构造完整 TurnResult,只验证 schema 含 guard_retries 字段:
    assert "guard_retries" in TurnResult.model_fields
    assert TurnResult.model_fields["guard_retries"].default == 0
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
.venv/bin/pytest tests/test_core_schemas.py -v
```

Expected: 4 个新测试 FAIL,提示 `cannot import name 'TurnInput' / 'TurnResult'`。

- [ ] **Step 3: 改写 `src/core/schemas.py`**

完整替换文件内容为:

```python
from __future__ import annotations

from datetime import UTC, datetime
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
    session_id: str = Field(min_length=1)


class TurnResult(BaseModel):
    # 注:Turn 类放在 core.turn_store(Task 4),避免循环引用。
    # TurnResult 在 Phase A 只声明字段;run_turn 方法签名 in Phase B 才完整使用。
    turn_id: str = Field(min_length=1)
    response_text: str = Field(min_length=1)
    guard_retries: int = Field(default=0, ge=0)
```

注意:**删除原 `TickEvent` 和 `SimulationNode` 类**。

- [ ] **Step 4: 跑测试,确认 pass**

```bash
.venv/bin/pytest tests/test_core_schemas.py -v
```

Expected: 所有测试(原 3 个 + 新 4 个 = 7 个)PASS。

- [ ] **Step 5: 跑全套测试,确认未破坏其他模块**

```bash
.venv/bin/pytest -q
```

Expected: 全部 PASS。若有失败提示 `TickEvent` / `SimulationNode` 引用不存在,说明有其他代码用到了它们 — 排查并按用途处理(删 import / 修复)。

- [ ] **Step 6: Commit**

```bash
git add src/core/schemas.py tests/test_core_schemas.py
git commit -m "$(cat <<'EOF'
phase-a: schemas 收敛 — 删 TickEvent/SimulationNode,加 TurnInput/TurnResult

Spec 9.A. Turn 类放 turn_store.py(避免循环引用)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `tests/_fakes.py` — FakeStructuredGateway

**Files:**
- Create: `tests/_fakes.py`(测试用 LLM gateway 工具)
- Create: `tests/test_fakes.py`(验证 fake 自身行为)

测试基础设施,后续 guard/narrative/turn_loop 都依赖它。

- [ ] **Step 1: 写 FakeStructuredGateway 的失败测试**

创建 `tests/test_fakes.py`:

```python
import pytest
from pydantic import BaseModel, ValidationError

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
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
.venv/bin/pytest tests/test_fakes.py -v
```

Expected: 全部 FAIL,提示 `No module named 'tests._fakes'`。

- [ ] **Step 3: 实现 `tests/_fakes.py`**

```python
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
```

- [ ] **Step 4: 跑测试,确认 pass**

```bash
.venv/bin/pytest tests/test_fakes.py -v
```

Expected: 4 个测试全部 PASS。

- [ ] **Step 5: 跑全套测试**

```bash
.venv/bin/pytest -q
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add tests/_fakes.py tests/test_fakes.py
git commit -m "$(cat <<'EOF'
phase-a: 加 FakeStructuredGateway 测试工具

按 (schema, response) 顺序返回预编排响应。后续 guard / narrative /
turn_loop 测试都依赖它。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `core/agents/guard.py` — ConsistencyGuard

**Files:**
- Create: `src/core/agents/guard.py`
- Create: `tests/test_core_agents_guard.py`

实现 Guard 的 schema + ConsistencyGuard 基本流程。Phase A 完整实现 check 方法(把 GuardInput 装进 AgentTask,调 AgentRuntime,返回 GuardDecision)。

- [ ] **Step 1: 写 Guard schema 失败测试**

创建 `tests/test_core_agents_guard.py`:

```python
import pytest
from pydantic import BaseModel, ValidationError


def test_guard_finding_requires_known_severity():
    from core.agents.guard import GuardFinding

    GuardFinding(severity="info", message="ok")
    GuardFinding(severity="warning", message="ok")
    GuardFinding(severity="error", message="ok")
    with pytest.raises(ValidationError):
        GuardFinding(severity="fatal", message="ok")


def test_guard_decision_revise_requires_revised_payload():
    from core.agents.guard import GuardDecision, GuardFinding

    # accept 不需要 payload
    GuardDecision(decision="accept", findings=[])
    # reject 不需要 payload
    GuardDecision(decision="reject", findings=[GuardFinding(severity="error", message="bad")])

    # revise 必须有 payload — 缺失 raise
    with pytest.raises(ValidationError, match="revised_payload"):
        GuardDecision(
            decision="revise",
            findings=[GuardFinding(severity="warning", message="typo")],
            revised_payload=None,
        )

    # revise 有 payload — pass
    GuardDecision(
        decision="revise",
        findings=[GuardFinding(severity="warning", message="typo")],
        revised_payload={"narration": "fixed"},
    )


def test_reference_item_label_required():
    from core.agents.guard import ReferenceItem

    ReferenceItem(label="world_law:magic_cost", content="魔法需血液")
    with pytest.raises(ValidationError):
        ReferenceItem(label="", content="x")


def test_guard_input_accepts_minimal_payload():
    from core.agents.guard import GuardInput, ReferenceItem

    gi = GuardInput(
        proposal={"narration": "hi"},
        references=[ReferenceItem(label="rule", content="be consistent")],
        rules=["no zero-cost magic"],
        session_id="s1",
    )
    assert gi.proposal == {"narration": "hi"}
    assert len(gi.references) == 1


@pytest.mark.asyncio
async def test_consistency_guard_check_returns_decision_from_runtime():
    from core.agents.guard import ConsistencyGuard, GuardDecision, GuardInput, ReferenceItem
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from core.schemas import ThinkingPolicy
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(
        GuardDecision,
        GuardDecision(decision="accept", findings=[]),
    )

    profile = AgentProfile(
        id="guard",
        name="ConsistencyGuard",
        role="canon check",
        objective="check proposal vs references",
        thinking=ThinkingPolicy(type="enabled"),
        temperature=0.2,
        max_tokens=2048,
    )
    guard = ConsistencyGuard(runtime=AgentRuntime(gateway=gateway), profile=profile)

    decision = await guard.check(
        GuardInput(
            proposal={"narration": "ok"},
            references=[ReferenceItem(label="rule", content="x")],
            rules=["r1"],
            session_id="s1",
        )
    )
    assert decision.decision == "accept"
    assert len(gateway.invocations) == 1
    # references 和 rules 都进了 user message context:
    user_msg = gateway.invocations[0].messages[1]
    assert "rule" in user_msg.content
    assert "r1" in user_msg.content
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
.venv/bin/pytest tests/test_core_agents_guard.py -v
```

Expected: 全部 FAIL,提示 `No module named 'core.agents.guard'`。

- [ ] **Step 3: 实现 `src/core/agents/guard.py`**

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
    session_id: str = Field(min_length=1)


_GUARD_INSTRUCTION = (
    "你是 Canon Guard。判断'提案'是否违反'参考材料',返回 GuardDecision JSON。"
    "accept = 一致放行;revise = 可修复小矛盾,必须给 revised_payload;"
    "reject = 不可修复矛盾(违反法则/复活死人/凭空物品)。"
)


class ConsistencyGuard:
    """通用 Guard:把 GuardInput 装进 AgentTask,调 AgentRuntime,返回 GuardDecision。"""

    def __init__(self, *, runtime: AgentRuntime, profile: AgentProfile) -> None:
        self.runtime = runtime
        self.profile = profile

    async def check(self, guard_input: GuardInput) -> GuardDecision:
        task = AgentTask(
            instruction=_GUARD_INSTRUCTION,
            context=guard_input.model_dump(mode="json"),
            required_output="GuardDecision",
        )
        return await self.runtime.run_agent(self.profile, task, GuardDecision)
```

- [ ] **Step 4: 跑测试,确认 pass**

```bash
.venv/bin/pytest tests/test_core_agents_guard.py -v
```

Expected: 5 个测试全部 PASS。

- [ ] **Step 5: 跑全套测试**

```bash
.venv/bin/pytest -q
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/core/agents/guard.py tests/test_core_agents_guard.py
git commit -m "$(cat <<'EOF'
phase-a: 加 core/agents/guard.py — ConsistencyGuard

GuardDecision.revise 强制要求 revised_payload(model_validator)。
ConsistencyGuard 是 AgentRuntime 的薄封装,把 GuardInput 序列化进
AgentTask.context,后续 prompt 形态在 Phase B 接 TurnLoop 时再调。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `core/world_memory.py` — WorldMemory

**Files:**
- Create: `src/core/world_memory.py`
- Create: `tests/test_world_memory.py`

WorldMemory 是 RAG 之上的语义化门面。Phase A 实现:`MemoryRecord` / `MemoryQuery` 数据契约 + `WorldMemory.query / upsert / upsert_many / find_similar` 方法,底层用 `InMemoryRAGRepository`。kind 路由通过 metadata filter 实现。

- [ ] **Step 1: 写测试**

创建 `tests/test_world_memory.py`:

```python
import pytest
from pydantic import ValidationError


def test_memory_record_requires_non_empty_fields():
    from core.world_memory import MemoryRecord

    MemoryRecord(kind="world_law", content="x", source="t:1", session_id="s")
    with pytest.raises(ValidationError):
        MemoryRecord(kind="", content="x", source="t:1", session_id="s")
    with pytest.raises(ValidationError):
        MemoryRecord(kind="k", content="", source="t:1", session_id="s")
    with pytest.raises(ValidationError):
        MemoryRecord(kind="k", content="x", source="", session_id="s")
    with pytest.raises(ValidationError):
        MemoryRecord(kind="k", content="x", source="t:1", session_id="")


def test_memory_record_confidence_in_range():
    from core.world_memory import MemoryRecord

    MemoryRecord(kind="k", content="x", source="s", session_id="x", confidence=0.0)
    MemoryRecord(kind="k", content="x", source="s", session_id="x", confidence=1.0)
    with pytest.raises(ValidationError):
        MemoryRecord(kind="k", content="x", source="s", session_id="x", confidence=1.5)


def test_memory_query_top_k_and_score_bounds():
    from core.world_memory import MemoryQuery

    MemoryQuery(query_text="q", session_id="s", top_k=1)
    MemoryQuery(query_text="q", session_id="s", top_k=50)
    with pytest.raises(ValidationError):
        MemoryQuery(query_text="q", session_id="s", top_k=0)
    with pytest.raises(ValidationError):
        MemoryQuery(query_text="q", session_id="s", top_k=51)
    with pytest.raises(ValidationError):
        MemoryQuery(query_text="q", session_id="s", min_score=-0.1)
    with pytest.raises(ValidationError):
        MemoryQuery(query_text="q", session_id="s", min_score=1.1)


def test_world_memory_upsert_and_query_round_trip():
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import MemoryQuery, MemoryRecord, WorldMemory

    wm = WorldMemory(repository=InMemoryRAGRepository())
    rec = MemoryRecord(
        kind="world_law",
        content="magic requires blood",
        source="turn:0",
        session_id="s1",
    )
    wm.upsert(rec)

    results = wm.query(MemoryQuery(query_text="blood", session_id="s1", top_k=5))
    assert len(results) == 1
    assert results[0].fragment.content == "magic requires blood"


def test_world_memory_query_filters_by_session_id():
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import MemoryQuery, MemoryRecord, WorldMemory

    wm = WorldMemory(repository=InMemoryRAGRepository())
    wm.upsert(MemoryRecord(kind="k", content="alpha", source="t", session_id="s1"))
    wm.upsert(MemoryRecord(kind="k", content="alpha", source="t", session_id="s2"))

    results = wm.query(MemoryQuery(query_text="alpha", session_id="s1", top_k=10))
    assert len(results) == 1
    assert results[0].fragment.metadata["session_id"] == "s1"


def test_world_memory_query_filters_by_kinds():
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import MemoryQuery, MemoryRecord, WorldMemory

    wm = WorldMemory(repository=InMemoryRAGRepository())
    wm.upsert(MemoryRecord(kind="world_law", content="alpha law", source="t", session_id="s"))
    wm.upsert(MemoryRecord(kind="character", content="alpha char", source="t", session_id="s"))

    results = wm.query(
        MemoryQuery(query_text="alpha", session_id="s", kinds=["world_law"], top_k=10)
    )
    assert len(results) == 1
    assert results[0].fragment.metadata["kind"] == "world_law"


def test_world_memory_min_score_threshold():
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import MemoryQuery, MemoryRecord, WorldMemory

    wm = WorldMemory(repository=InMemoryRAGRepository())
    wm.upsert(MemoryRecord(kind="k", content="alpha beta", source="t", session_id="s"))
    wm.upsert(MemoryRecord(kind="k", content="completely unrelated", source="t", session_id="s"))

    # min_score=0.5 时,完全不相关的应被过滤
    results = wm.query(
        MemoryQuery(query_text="alpha beta", session_id="s", min_score=0.5, top_k=10)
    )
    assert len(results) == 1
    assert results[0].score >= 0.5


def test_world_memory_upsert_many_returns_all_ids():
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import MemoryRecord, WorldMemory

    wm = WorldMemory(repository=InMemoryRAGRepository())
    records = [
        MemoryRecord(kind="k", content=f"c{i}", source="t", session_id="s") for i in range(3)
    ]
    ids = wm.upsert_many(records)
    assert len(ids) == 3
    assert ids == [r.id for r in records]
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
.venv/bin/pytest tests/test_world_memory.py -v
```

Expected: 全部 FAIL,提示 `No module named 'core.world_memory'`。

- [ ] **Step 3: 实现 `src/core/world_memory.py`**

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from core.rag_repository import UniversalRAGRepository
from core.schemas import MemoryFragment, RAGQueryResult


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryQuery(BaseModel):
    query_text: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    kinds: list[str] | None = None
    top_k: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class WorldMemory:
    """RAG 之上的语义化记忆门面。core 暴露这个接口,Repository 是实现细节。

    metadata 约定:
      - session_id: 会话隔离
      - kind: game 层自定义类别(world_law / location / character / ...)
      - source: 来源标记(turn:N / world_init / manual)
      - confidence: 0.0-1.0
      - record_id: MemoryRecord.id(便于反查)
    """

    def __init__(self, *, repository: UniversalRAGRepository) -> None:
        self.repository = repository

    def upsert(self, record: MemoryRecord) -> str:
        fragment = self._record_to_fragment(record)
        return self.repository.upsert(fragment)

    def upsert_many(self, records: list[MemoryRecord]) -> list[str]:
        fragments = [self._record_to_fragment(r) for r in records]
        return self.repository.upsert_batch(fragments)

    def query(self, q: MemoryQuery) -> list[RAGQueryResult]:
        # 注:InMemoryRAGRepository.metadata_filter 是精确等值匹配,不支持 IN 多值。
        # 多 kinds 的情况下,先按 session_id 过滤,后在 Python 侧按 kinds 过滤。
        metadata_filter: dict[str, Any] = {"session_id": q.session_id}
        if q.kinds and len(q.kinds) == 1:
            metadata_filter["kind"] = q.kinds[0]

        raw = self.repository.hybrid_search(
            query=q.query_text,
            top_k=q.top_k * 4 if q.kinds and len(q.kinds) > 1 else q.top_k,
            metadata_filter=metadata_filter,
        )

        if q.kinds and len(q.kinds) > 1:
            allowed = set(q.kinds)
            raw = [r for r in raw if r.fragment.metadata.get("kind") in allowed]

        if q.min_score > 0.0:
            raw = [r for r in raw if r.score >= q.min_score]

        return raw[: q.top_k]

    def find_similar(
        self, content: str, session_id: str, threshold: float = 0.92
    ) -> MemoryRecord | None:
        """根据 content 做相似度查找。≥ threshold 视为'重复'。MVP 用现有 hybrid_search,Phase B 视情况换 embedding。"""
        results = self.repository.hybrid_search(
            query=content,
            top_k=1,
            metadata_filter={"session_id": session_id},
        )
        if not results or results[0].score < threshold:
            return None
        return self._fragment_to_record(results[0].fragment)

    @staticmethod
    def _record_to_fragment(record: MemoryRecord) -> MemoryFragment:
        return MemoryFragment(
            id=record.id,
            content=record.content,
            metadata={
                "kind": record.kind,
                "source": record.source,
                "session_id": record.session_id,
                "confidence": record.confidence,
                "created_at": record.created_at.isoformat(),
                "record_id": record.id,
                **record.metadata,
            },
        )

    @staticmethod
    def _fragment_to_record(fragment: MemoryFragment) -> MemoryRecord:
        meta = fragment.metadata
        return MemoryRecord(
            id=meta.get("record_id", fragment.id),
            kind=meta.get("kind", "unknown"),
            content=fragment.content,
            source=meta.get("source", "unknown"),
            session_id=meta.get("session_id", "unknown"),
            confidence=float(meta.get("confidence", 1.0)),
            created_at=datetime.fromisoformat(meta["created_at"])
            if "created_at" in meta
            else datetime.now(UTC),
            metadata={
                k: v
                for k, v in meta.items()
                if k not in {"kind", "source", "session_id", "confidence", "created_at", "record_id"}
            },
        )
```

- [ ] **Step 4: 跑测试,确认 pass**

```bash
.venv/bin/pytest tests/test_world_memory.py -v
```

Expected: 8 个测试全部 PASS。若 `test_world_memory_min_score_threshold` fail(因为 InMemoryRAGRepository 的 cosine score 可能比预期低),把 min_score 改为更宽松的 0.1 再核;或修改测试期待。

- [ ] **Step 5: 跑全套测试**

```bash
.venv/bin/pytest -q
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/core/world_memory.py tests/test_world_memory.py
git commit -m "$(cat <<'EOF'
phase-a: 加 core/world_memory.py — WorldMemory 语义化记忆门面

MemoryRecord / MemoryQuery 数据契约 + WorldMemory 类。
kind 用 str(由 game 层自定义),通过 metadata filter 路由。
多 kinds 用 Python 侧过滤(InMemoryRAGRepository 不支持 IN 查询)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `core/turn_store.py` — Turn + JSONL 存盘

**Files:**
- Create: `src/core/turn_store.py`
- Create: `tests/test_turn_store.py`

`Turn` 类放这里(依赖 `GuardDecision` + `MemoryRecord`,所以必须晚于 Task 3/4)。`TurnStore` 实现 JSONL 存盘 + `load_recent(session_id, n)`。

- [ ] **Step 1: 写测试**

创建 `tests/test_turn_store.py`:

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest


def test_turn_minimal_payload_validates():
    from core.schemas import TurnInput
    from core.turn_store import Turn

    t = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="s1"))
    assert t.status == "ok"
    assert t.response_text is None
    assert t.id  # auto-generated


def test_turn_round_trip_json_with_guard_and_records():
    from core.agents.guard import GuardDecision
    from core.schemas import TurnInput
    from core.turn_store import Turn
    from core.world_memory import MemoryRecord

    original = Turn(
        input=TurnInput(raw_text="say hi", turn_index=2, session_id="s1"),
        narrative_draft={"narration": "hello"},
        guard_decision=GuardDecision(decision="accept", findings=[]),
        curated_records=[
            MemoryRecord(kind="event", content="player said hi", source="turn:2", session_id="s1")
        ],
        response_text="hello back",
        status="ok",
    )

    dumped = original.model_dump_json()
    restored = Turn.model_validate_json(dumped)

    assert restored.input.raw_text == "say hi"
    assert restored.input.turn_index == 2
    assert restored.guard_decision is not None
    assert restored.guard_decision.decision == "accept"
    assert len(restored.curated_records) == 1
    assert restored.curated_records[0].kind == "event"
    assert restored.response_text == "hello back"


def test_turn_store_save_appends_jsonl_line(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    turn = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="s1"))
    store.save(turn)

    session_file = tmp_path / "s1.jsonl"
    assert session_file.exists()
    lines = session_file.read_text().splitlines()
    assert len(lines) == 1
    decoded = json.loads(lines[0])
    assert decoded["input"]["raw_text"] == "x"


def test_turn_store_save_multiple_turns_appends_lines(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    for i in range(3):
        store.save(Turn(input=TurnInput(raw_text=f"x{i}", turn_index=i, session_id="s2")))

    session_file = tmp_path / "s2.jsonl"
    lines = session_file.read_text().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["input"]["turn_index"] == 0
    assert json.loads(lines[2])["input"]["turn_index"] == 2


def test_turn_store_load_recent_returns_last_n(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    for i in range(5):
        store.save(Turn(input=TurnInput(raw_text=f"x{i}", turn_index=i, session_id="s3")))

    recent = store.load_recent(session_id="s3", n=2)
    assert len(recent) == 2
    assert recent[0].input.turn_index == 3
    assert recent[1].input.turn_index == 4


def test_turn_store_load_recent_handles_missing_session(tmp_path: Path):
    from core.turn_store import TurnStore

    store = TurnStore(data_dir=tmp_path)
    assert store.load_recent(session_id="never", n=5) == []


def test_turn_store_load_session_returns_all_turns_in_order(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    for i in range(3):
        store.save(Turn(input=TurnInput(raw_text=f"x{i}", turn_index=i, session_id="s4")))

    all_turns = store.load_session(session_id="s4")
    assert len(all_turns) == 3
    assert [t.input.turn_index for t in all_turns] == [0, 1, 2]
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
.venv/bin/pytest tests/test_turn_store.py -v
```

Expected: 全部 FAIL,提示 `No module named 'core.turn_store'`。

- [ ] **Step 3: 实现 `src/core/turn_store.py`**

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from core.agents.guard import GuardDecision
from core.schemas import RAGQueryResult, TurnInput
from core.world_memory import MemoryRecord


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


class TurnStore:
    """把 Turn 序列化为 JSONL,每 session 一个文件:<data_dir>/<session_id>.jsonl。"""

    def __init__(self, *, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save(self, turn: Turn) -> None:
        path = self._path_for(turn.input.session_id)
        line = turn.model_dump_json()
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load_session(self, *, session_id: str) -> list[Turn]:
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
        if n <= 0:
            return []
        all_turns = self.load_session(session_id=session_id)
        return all_turns[-n:]

    def _path_for(self, session_id: str) -> Path:
        return self.data_dir / f"{session_id}.jsonl"
```

- [ ] **Step 4: 跑测试,确认 pass**

```bash
.venv/bin/pytest tests/test_turn_store.py -v
```

Expected: 7 个测试全部 PASS。

- [ ] **Step 5: 跑全套测试**

```bash
.venv/bin/pytest -q
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/core/turn_store.py tests/test_turn_store.py
git commit -m "$(cat <<'EOF'
phase-a: 加 core/turn_store.py — Turn 快照 + JSONL 存盘

Turn 类(依赖 GuardDecision + MemoryRecord)+ TurnStore.save/
load_session/load_recent。每 session 一个 JSONL 文件,行级 append。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `core/agents/narrative.py` — NarrativeAgent

**Files:**
- Create: `src/core/agents/narrative.py`
- Create: `tests/test_core_agents_narrative.py`

NarrativeAgent 是 `AgentRuntime.run_agent` 的泛型薄封装。把 `NarrativeContext`(player_input + retrieved_memory + extra)序列化进 AgentTask.context,output_schema 由调用方指定。

- [ ] **Step 1: 写测试**

创建 `tests/test_core_agents_narrative.py`:

```python
import pytest
from pydantic import BaseModel, Field


class _DemoBeat(BaseModel):
    narration: str = Field(min_length=1)
    new_facts: list[str] = Field(default_factory=list)


def test_narrative_context_serializes_minimal_payload():
    from core.agents.narrative import NarrativeContext
    from core.schemas import TurnInput

    ctx = NarrativeContext(
        player_input=TurnInput(raw_text="look", turn_index=0, session_id="s1"),
        retrieved_memory=[],
    )
    assert ctx.player_input.raw_text == "look"
    assert ctx.extra == {}


@pytest.mark.asyncio
async def test_narrative_agent_runs_with_fake_gateway():
    from core.agents.narrative import NarrativeAgent, NarrativeContext
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from core.schemas import ThinkingPolicy, TurnInput
    from tests._fakes import FakeStructuredGateway

    gateway = FakeStructuredGateway()
    gateway.queue_response(_DemoBeat, _DemoBeat(narration="你看到一片森林。"))

    profile = AgentProfile(
        id="narrator",
        name="NarrativeAgent",
        role="narrator",
        objective="generate next narrative beat",
        thinking=ThinkingPolicy(type="enabled"),
        temperature=0.8,
        max_tokens=4096,
    )
    agent = NarrativeAgent(runtime=AgentRuntime(gateway=gateway), profile=profile)

    result = await agent.run(
        context=NarrativeContext(
            player_input=TurnInput(raw_text="look around", turn_index=0, session_id="s1"),
            retrieved_memory=[],
            extra={"scene_summary": "你在森林深处。"},
        ),
        output_schema=_DemoBeat,
    )

    assert isinstance(result, _DemoBeat)
    assert result.narration == "你看到一片森林。"
    # context 的 raw_text 与 extra 必须进了 user message:
    user_msg = gateway.invocations[0].messages[1]
    assert "look around" in user_msg.content
    assert "scene_summary" in user_msg.content


@pytest.mark.asyncio
async def test_narrative_agent_passes_through_output_schema_choice():
    from core.agents.narrative import NarrativeAgent, NarrativeContext
    from core.agents.runtime import AgentRuntime
    from core.agents.schemas import AgentProfile
    from core.schemas import TurnInput
    from tests._fakes import FakeStructuredGateway

    class _AltBeat(BaseModel):
        line: str = Field(min_length=1)

    gateway = FakeStructuredGateway()
    gateway.queue_response(_AltBeat, _AltBeat(line="hi"))

    profile = AgentProfile(id="n", name="N", role="r", objective="o")
    agent = NarrativeAgent(runtime=AgentRuntime(gateway=gateway), profile=profile)

    result = await agent.run(
        context=NarrativeContext(
            player_input=TurnInput(raw_text="x", turn_index=0, session_id="s"),
            retrieved_memory=[],
        ),
        output_schema=_AltBeat,
    )
    assert isinstance(result, _AltBeat)
    assert result.line == "hi"
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
.venv/bin/pytest tests/test_core_agents_narrative.py -v
```

Expected: 全部 FAIL,提示 `No module named 'core.agents.narrative'`。

- [ ] **Step 3: 实现 `src/core/agents/narrative.py`**

```python
from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, Field

from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile, AgentTask
from core.schemas import RAGQueryResult, TurnInput


T = TypeVar("T", bound=BaseModel)


_NARRATIVE_INSTRUCTION = (
    "你是叙事生成 agent。基于玩家本轮输入与检索到的相关记忆,生成下一段叙事 JSON。"
    "如有新事实(角色/地点/事件/玩家状态),通过 output_schema 的相应字段返回。"
)


class NarrativeContext(BaseModel):
    player_input: TurnInput
    retrieved_memory: list[RAGQueryResult] = Field(default_factory=list)
    extra: dict[str, object] = Field(default_factory=dict)


class NarrativeAgent:
    """单 agent 叙事生成的统一入口,output_schema 由 game 层指定。"""

    def __init__(self, *, runtime: AgentRuntime, profile: AgentProfile) -> None:
        self.runtime = runtime
        self.profile = profile

    async def run(self, *, context: NarrativeContext, output_schema: type[T]) -> T:
        task = AgentTask(
            instruction=_NARRATIVE_INSTRUCTION,
            context=context.model_dump(mode="json"),
            required_output=output_schema.__name__,
        )
        return await self.runtime.run_agent(self.profile, task, output_schema)
```

- [ ] **Step 4: 跑测试,确认 pass**

```bash
.venv/bin/pytest tests/test_core_agents_narrative.py -v
```

Expected: 3 个测试全部 PASS。

- [ ] **Step 5: 跑全套测试**

```bash
.venv/bin/pytest -q
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/core/agents/narrative.py tests/test_core_agents_narrative.py
git commit -m "$(cat <<'EOF'
phase-a: 加 core/agents/narrative.py — NarrativeAgent

AgentRuntime.run_agent 的泛型薄封装,output_schema 由调用方指定。
NarrativeContext 序列化进 AgentTask.context,prompt 形态在 Phase B
接 TurnLoop 时再调。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `tests/test_import_graph.py` — core / game 边界静态校验

**Files:**
- Create: `tests/test_import_graph.py`

强制 core/* 不 import game/*,core/* 文件文本不含游戏域名词集合。这是 Spec §8.B 的最后一项。

- [ ] **Step 1: 写测试**

创建 `tests/test_import_graph.py`:

```python
import ast
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

# core 不允许出现的游戏域名词(case-insensitive 全词匹配)。
# 不含 "world"(spec §6 自己有 world_memory / world_init 命名),不含 "memory" 等通用词。
_FORBIDDEN_GAME_TERMS = {
    "world_law",
    "character",
    "location",
    "faction",
    "combat",
    "npc",
    "scene",
    "inventory",
    "quest",
    "spell",
}


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name == "__init__.py" and path.stat().st_size == 0:
            continue
        yield path


def test_core_does_not_import_game():
    core_root = SRC_ROOT / "core"
    violations: list[str] = []
    for path in _iter_python_files(core_root):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("game.") or alias.name == "game":
                        violations.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module.startswith("game.") or node.module == "game"):
                    violations.append(f"{path}: from {node.module} import ...")
    assert not violations, "core/* must not import game/*:\n" + "\n".join(violations)


def test_core_files_do_not_mention_game_domain_terms():
    core_root = SRC_ROOT / "core"
    # 全词匹配,case-insensitive。允许在注释里出现"不要做"的描述,所以只扫非注释/非字符串行。
    # 简化:跳过 # 起始的行(注释)与 docstring(粗略用三引号块跳过)。
    violations: list[str] = []
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in _FORBIDDEN_GAME_TERMS) + r")\b",
        re.IGNORECASE,
    )
    for path in _iter_python_files(core_root):
        source = path.read_text(encoding="utf-8")
        # 简易剥离 docstring(连续三引号块);保留注释外的代码。
        # 这一步不追求 100% 精确,只防"有意引入"。
        in_doc = False
        for line_num, raw in enumerate(source.splitlines(), 1):
            stripped = raw.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                # 简单切换:出现就翻转(三引号块开始/结束)
                triple_count = raw.count('"""') + raw.count("'''")
                if triple_count >= 2:
                    pass  # 同行开闭
                else:
                    in_doc = not in_doc
                continue
            if in_doc:
                continue
            if stripped.startswith("#"):
                continue
            match = pattern.search(raw)
            if match:
                violations.append(f"{path}:{line_num}: {match.group(0)!r} in: {raw.strip()}")
    assert not violations, (
        "core/* must not mention game domain terms (use generic 'node' / 'memory' / 'event' / 'agent'):\n"
        + "\n".join(violations)
    )
```

- [ ] **Step 2: 跑测试,确认 pass(或 fail 后调整名词集合)**

```bash
.venv/bin/pytest tests/test_import_graph.py -v
```

Expected: 2 个测试 PASS。**若 fail**:
- `test_core_does_not_import_game` fail → 真的有 core 文件 import game,必须修
- `test_core_files_do_not_mention_game_domain_terms` fail → 检查具体行:
  - 若是注释/docstring 误判 → 调整测试中的 docstring 剥离逻辑
  - 若是真有变量名/字符串字面量含禁词 → 改名

- [ ] **Step 3: Commit**

```bash
git add tests/test_import_graph.py
git commit -m "$(cat <<'EOF'
phase-a: 加 import-graph 静态校验

强制 core/* 不 import game/*,core/* 文件文本不含游戏域名词。
是 spec §8.B 的最后一项,也是 core/game 边界铁律的代码守护。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Phase A 收尾

**Files:** 无新文件,只跑测试 + 看覆盖率 + 标记里程碑。

- [ ] **Step 1: 跑全套测试 + verbose**

```bash
.venv/bin/pytest -v
```

Expected: 全部 PASS。统计:Phase A 新增约 30+ 个测试,加原有测试,总数应 ≥ 50。

- [ ] **Step 2: 跑覆盖率(可选,需安装 pytest-cov)**

```bash
.venv/bin/pip install pytest-cov 2>&1 | tail -3
.venv/bin/pytest --cov=src --cov-report=term-missing -q
```

Expected: `src/core/` 覆盖率 ≥ 80%。若低于 80%,记录漏覆盖的具体 line,但 Phase A 不强制 — 完整覆盖率验收在 §8.F 由 Phase E 达成。

- [ ] **Step 3: 确认 git 状态干净**

```bash
git status
git log --oneline -10
```

Expected:
- `git status` 显示 "nothing to commit, working tree clean"
- `git log` 显示本 Phase 的 7 个 commit(每个 task 一个)+ 前置 design commit

- [ ] **Step 4: 打 Phase A 里程碑 tag(可选)**

```bash
git tag -a phase-a-complete -m "Phase A: core foundation complete"
git tag --list | grep phase-a
```

Expected: 显示 `phase-a-complete`。注:tag 默认本地,如要推到远端需 `git push --tags`(本 plan 不要求推)。

- [ ] **Step 5: 输出最终进度报告**

人工汇总以下信息到 plan 末尾(或单独写一份 phase-a-completion-report.md,放 docs/superpowers/):
- 新增文件清单(7 个,见 File Structure)
- 新增测试数与通过率
- 已实现 spec §5 的哪些 schema、§9 Phase A 的哪些动作
- 未完成项 / 已知遗留(若有)— 例如某个 fuzzy 行为留待 Phase B

---

## Phase A 自审(执行者读完整个 plan 后,实施前先扫一遍)

- [ ] **Spec coverage**:Spec §5 (core schema) 与 §9 Phase A 列的所有动作,是否都能在 Task 1-7 找到?
  - schemas.py 收敛 → Task 1 ✓
  - guard.py → Task 3 ✓
  - narrative.py → Task 6 ✓
  - world_memory.py → Task 4 ✓
  - turn_store.py → Task 5 ✓
  - 单元测试 → 每个 Task 内含 ✓
  - **未含**:`core/turn_loop.py` 在 Phase A 不实现(spec §9 Phase A 也未列,正确;Phase B 范围)
- [ ] **Placeholder 扫描**:plan 内是否有 TBD / TODO / "类似 Task N" 等占位?— 无
- [ ] **Type 一致性**:
  - `GuardDecision` / `ReferenceItem` / `GuardInput` 在 Task 3 定义,Task 5 / Task 6 引用 — 名字一致 ✓
  - `MemoryRecord` / `MemoryQuery` 在 Task 4 定义,Task 5 引用 — 一致 ✓
  - `TurnInput` 在 Task 1 定义,Task 5 / Task 6 引用 — 一致 ✓
  - `Turn` 在 Task 5 定义,Phase B 才被消费 — 本 Phase 无冲突
- [ ] **依赖顺序**:Task 1 → 2 → 3 → 4 → 5(turn_store 依赖 3+4)→ 6 → 7 → 8 — 顺序正确 ✓

---

## Phase A 结束后的衔接

Phase A 完成后,要写 Phase B 的 plan(`docs/superpowers/plans/2026-05-26-phase-b-turn-loop.md`)。Phase B 主要内容:
- `core/turn_loop.py` 实现 §6.1 时序
- TurnLoop 集成 NarrativeAgent / WorldMemory / ConsistencyGuard / TurnStore
- Guard 决策分支(accept / revise / reject / circuit-open 降级)
- TurnTelemetry 记录
- 集成测试(§8.C 前 4 个用例)

Phase B 起 ConsistencyGuard / NarrativeAgent 在 prompt 装配上可能要调整(当前 Phase A 是简单的 context dict 注入,Phase B 接 TurnLoop 后会看出 prompt 是否够用)。**Phase A 不预先优化 prompt,等真用上再调**。
