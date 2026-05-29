# Phase C: References 完整 + 续接能力 + Phase D 准备 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 TurnLoop 从 "MVP 跑通" 升级为 "Phase D game 域可以直接挂上来跑通"的成熟状态。具体:完整 `_build_references`(spec §7.B 顺序,含 recent_turns 摘要)+ TurnStore 续接能力(`list_sessions`)+ LLMGateway monotonic clock 重构(技术债)+ 一致性集成测试加 spec §7.A 5 类失败分类覆盖 + Phase D contract 文档。

**Architecture:** Phase C 不引入新的 core 组件,只把现有组件的"简化版"补齐到 spec 要求。`_build_references` 从 retrieved_memory-only 扩展到完整 spec §7.B 顺序;TurnStore 加 `list_sessions` 给 Phase D `--resume` 用;LLMGateway 把 wall clock 换 monotonic clock(Phase B Task 3 review 推荐);新增一份 "extending-the-engine.md" contract 文档让 Phase D 开始时有清晰的 5 个契约。

**Tech Stack:** Python 3.11+, Pydantic 2.7+, pytest + pytest-asyncio。无新依赖。

**Spec 引用:** [docs/superpowers/specs/2026-05-26-turn-loop-engine-redesign-design.md](../specs/2026-05-26-turn-loop-engine-redesign-design.md) §7.A, §7.B, §7.D, §8.C, §8.F

**Phase B 完成报告:** [2026-05-27-phase-b-completion-report.md](2026-05-27-phase-b-completion-report.md)。本 plan 处理它列出的 5 个"留 Phase C"事项。

---

## File Structure

| 文件 | 类型 | 职责 |
|------|------|------|
| `src/core/llm_gateway.py` | 修改 | wall clock → monotonic clock(circuit_open_until 类型 datetime|None → float|None) |
| `tests/test_llm_gateway.py` | 修改 | monotonic 改后的相应测试调整 |
| `src/core/turn_store.py` | 修改 | 加 `list_sessions() -> list[str]`(按 mtime 倒序) |
| `tests/test_turn_store.py` | 修改 | list_sessions 测试(空 / 单 / 多 / 非 jsonl 忽略) |
| `src/core/turn_loop.py` | 修改 | `_build_references` 完整版(spec §7.B 顺序 + recent_turns 摘要) |
| `tests/test_turn_loop.py` | 修改 | references 顺序测试 + recent_turns 注入测试 |
| `tests/test_turn_loop_integration.py` | 新建 | 5 类一致性失败集成测试(spec §7.A) |
| `docs/superpowers/specs/extending-the-engine.md` | 新建 | Phase D 开始前的 contract 文档:列出 game 域要实现的 5 个契约 + mini example |

**Phase C 不涉及**:Phase D(text_adventure)/ Phase E(world_init 降级)/ ChromaRAG 真实使用 / Live LLM 集成 / Curator 实现(Phase D)。

---

## Pre-Task: 环境核对

- [ ] **Step 1: 确认 Phase B 基线**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && pwd && git tag | grep phase && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q 2>&1 | tail -3
```

Expected: `phase-a-complete` + `phase-b-complete` 都在 + 96 passed + 1 skipped。

---

## Task 1: LLMGateway monotonic clock 重构

**Files:**
- Modify: `src/core/llm_gateway.py`(`circuit_open_until: datetime | None` → `float | None`,用 `time.monotonic()`)
- Modify: `tests/test_llm_gateway.py`(测试 fixture 调整)

**目标**(Phase B Task 3 review Important #1):wall clock(`datetime.now(UTC)`)受 NTP / 时钟回退影响,熔断可能"卡死打开"或"过早关闭"。改用 `time.monotonic()` 是 Python 文档明确推荐做法。

- [ ] **Step 1: 改写 test_gateway_circuit_closes_after_window_expires 测试以适配 monotonic**

打开 `tests/test_llm_gateway.py`,找到 `test_gateway_circuit_closes_after_window_expires`:

当前:
```python
@pytest.mark.asyncio
async def test_gateway_circuit_closes_after_window_expires():
    """熔断打开后,window 时间过去 → 下次调用恢复尝试。"""
    from datetime import UTC, datetime, timedelta

    from core.llm_gateway import GatewayCircuitOpen, LLMGateway, LLMGatewayError

    gateway = LLMGateway(
        api_key="test",
        max_retries=0,
        failure_threshold=2,
        circuit_window_seconds=60,
        transport=_circuit_fail_transport(),
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

    # 下次调用应该尝试请求(虽然 transport 仍 fail,但不会立即 GatewayCircuitOpen)
    with pytest.raises(LLMGatewayError) as exc_info:
        await gateway.complete(request)
    assert not isinstance(exc_info.value, GatewayCircuitOpen)
```

替换为(monotonic 版,float 而非 datetime):
```python
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

    # 把 circuit_open_until 倒到过去(monotonic float)
    gateway.circuit_open_until = time.monotonic() - 1.0

    with pytest.raises(LLMGatewayError) as exc_info:
        await gateway.complete(request)
    assert not isinstance(exc_info.value, GatewayCircuitOpen)
```

- [ ] **Step 2: 改写 test_gateway_circuit_default_threshold_and_window 测试**

打开同文件,找到该测试:

当前:
```python
@pytest.mark.asyncio
async def test_gateway_circuit_default_threshold_and_window():
    """默认值检查:failure_threshold=5, circuit_window_seconds=900。"""
    from core.llm_gateway import LLMGateway

    gateway = LLMGateway(api_key="test")
    assert gateway.failure_threshold == 5
    assert gateway.circuit_window_seconds == 900
    assert gateway.consecutive_failures == 0
    assert gateway.circuit_open_until is None
```

无需改动 — `is None` 检查对 datetime / float 都成立。**跳过本 step 的修改**,直接确认它仍能跑过(monotonic float 改动后)。

- [ ] **Step 3: 跑测试,确认 fail**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_llm_gateway.py -v -k "circuit"
```

Expected: 4 测试中,`test_gateway_circuit_closes_after_window_expires` 应该仍 PASS(我们改了测试用 monotonic 但 production code 还是 wall clock,所以 datetime/float 类型不匹配 → 抛 TypeError);其他 3 个可能仍 PASS(因为他们没碰 circuit_open_until 字段)。

实际上可能所有 4 个都 PASS(production 还没改),那是因为 step 1 的测试改成了 `time.monotonic()` 但 `circuit_open_until` 字段还是 datetime — 赋值 float 给一个会被 `datetime.now() < self.circuit_open_until` 比较的字段,比较时会 `TypeError: '<' not supported between instances of 'datetime' and 'float'`。所以 test 1 会 fail。

确认 fail 之后进 Step 4。

- [ ] **Step 4: 改 `src/core/llm_gateway.py` — 用 `time.monotonic()`**

修改要点(完整文件较长,我列出**精确变更**):

(a) 顶部 import 加 `import time`(若已有跳过)。**删除** `from datetime import UTC, datetime, timedelta`(不再需要,但只在 wall clock 用法处)。但要小心 — `datetime` 可能在别处使用,检查后再删:

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && grep -n "datetime\|UTC\|timedelta" src/core/llm_gateway.py
```

如果只在 circuit breaker 那 2 行用,可以删整个 import。如果别处用,只删 wall clock 用法,保留 import。

(b) `__init__` 中 `self.circuit_open_until: datetime | None = None` 改为:
```python
self.circuit_open_until: float | None = None
```

(c) `complete()` 入口熔断检查(原):
```python
if self.circuit_open_until is not None:
    now = datetime.now(UTC)
    if now < self.circuit_open_until:
        raise GatewayCircuitOpen(
            f"circuit breaker open until {self.circuit_open_until.isoformat()}"
        )
    # window 已过,关闭熔断,重置 counter,继续尝试
    self.circuit_open_until = None
    self.consecutive_failures = 0
```

改为:
```python
if self.circuit_open_until is not None:
    if time.monotonic() < self.circuit_open_until:
        raise GatewayCircuitOpen(
            f"circuit breaker open (closes in {self.circuit_open_until - time.monotonic():.1f}s)"
        )
    # window 已过,关闭熔断,重置 counter,继续尝试
    self.circuit_open_until = None
    self.consecutive_failures = 0
```

(d) `_record_failure` 中 `self.circuit_open_until = datetime.now(UTC) + timedelta(seconds=self.circuit_window_seconds)` 改为:
```python
self.circuit_open_until = time.monotonic() + self.circuit_window_seconds
```

- [ ] **Step 5: 跑测试,确认 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_llm_gateway.py -v
```

Expected: 全部 PASS(原 7 个)。

- [ ] **Step 6: 跑全套测试**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: 96 passed, 1 skipped(与 Phase B 基线一致,只是 production 改了时钟来源)。

- [ ] **Step 7: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/core/llm_gateway.py tests/test_llm_gateway.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-c: task 1 — LLMGateway monotonic clock 重构

Phase B Task 3 review Important #1 落实:wall clock(datetime.now(UTC))
受 NTP / 时钟回退影响,熔断可能"卡死打开"或"过早关闭"。
改用 time.monotonic() — Python 文档推荐做法,单调递增不受系统时钟变化影响。

变更:
- circuit_open_until 类型 datetime | None → float | None
- complete() 入口比较用 time.monotonic() < self.circuit_open_until
- _record_failure() 设值用 time.monotonic() + circuit_window_seconds
- test_gateway_circuit_closes_after_window_expires 用 time.monotonic() 倒值

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: TurnStore.list_sessions()

**Files:**
- Modify: `src/core/turn_store.py`(加 `list_sessions() -> list[str]`)
- Modify: `tests/test_turn_store.py`(加 4 个 list_sessions 测试)

**目标**(Phase B 完成报告条目 4):Phase D `--resume <session_id>` 需要先让玩家挑可用 session。`list_sessions` 按 mtime 倒序(最新优先)返回所有 jsonl 文件的 session_id(去掉 `.jsonl` 后缀)。忽略非 jsonl 文件。

- [ ] **Step 1: 写 list_sessions 失败测试**

追加到 `tests/test_turn_store.py` 末尾:

```python
def test_turn_store_list_sessions_empty_dir_returns_empty(tmp_path: Path):
    from core.turn_store import TurnStore

    store = TurnStore(data_dir=tmp_path)
    assert store.list_sessions() == []


def test_turn_store_list_sessions_returns_session_ids_without_extension(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="alpha")))
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="beta")))

    sessions = store.list_sessions()
    assert set(sessions) == {"alpha", "beta"}


def test_turn_store_list_sessions_orders_by_mtime_desc(tmp_path: Path):
    """最新写入的 session 排在前面(便于 --resume 默认挑最近的)。"""
    import time

    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    # 写入 3 个 session,间隔小段时间确保 mtime 区分
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="oldest")))
    time.sleep(0.01)
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="middle")))
    time.sleep(0.01)
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="newest")))

    sessions = store.list_sessions()
    assert sessions == ["newest", "middle", "oldest"]


def test_turn_store_list_sessions_ignores_non_jsonl_files(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="real")))

    # 制造干扰文件
    (tmp_path / "random.txt").write_text("noise")
    (tmp_path / "notes.md").write_text("notes")
    (tmp_path / ".DS_Store").write_text("mac junk")

    sessions = store.list_sessions()
    assert sessions == ["real"]  # 只 jsonl,其他全部忽略
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_store.py -v -k "list_sessions"
```

Expected: 4 FAIL with `AttributeError: 'TurnStore' object has no attribute 'list_sessions'`。

- [ ] **Step 3: 实现 `list_sessions`**

在 `src/core/turn_store.py` 的 `TurnStore` class 末尾(`_path_for` 之前)加:

```python
    def list_sessions(self) -> list[str]:
        """返回 data_dir 下所有 jsonl session_id,按 mtime 倒序(最新优先)。
        忽略非 jsonl 文件。"""
        jsonl_files = [p for p in self.data_dir.iterdir() if p.is_file() and p.suffix == ".jsonl"]
        # 按 mtime 倒序
        jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.stem for p in jsonl_files]
```

- [ ] **Step 4: 跑测试,确认 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_store.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 跑全套测试**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: 100 passed (96 prior + 4 new),1 skipped。

- [ ] **Step 6: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/core/turn_store.py tests/test_turn_store.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-c: task 2 — TurnStore.list_sessions() 列出所有 session

Phase B 完成报告条目 4:Phase D --resume <id> 需要先让玩家挑可用 session。
list_sessions() 扫 data_dir,返回所有 .jsonl 文件的 stem(session_id),
按 mtime 倒序(最新优先,便于 default 挑最近 session)。
忽略非 jsonl 文件(.DS_Store / .md / .txt 等干扰)。

4 个新测试覆盖:空 dir / 多 session / mtime 排序 / 忽略非 jsonl。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: _build_references 完整(spec §7.B 顺序 + recent_turns 摘要)

**Files:**
- Modify: `src/core/turn_loop.py`(`_build_references` 重写 + 加 `_summarize_turn_for_reference` helper)
- Modify: `tests/test_turn_loop.py`(加 references 顺序测试 + recent_turns 注入测试)

**目标**(Phase B 完成报告条目 1):当前 `_build_references` 只把 retrieved_memory 转 ReferenceItem。Spec §7.B 要求 references 按以下顺序进入 prompt:

```
1. 硬性规则(rules, 直接来自 config.guard_rules,作为 GuardInput.rules 已传)
2. world_law 类记忆(top 5)
3. 最近 3 轮 turn 摘要(player_state / 当前 location / 出场角色 / response_text 缩略)
4. character 类记忆(只本轮提案提到的角色)
5. event 类记忆(top 3,按时间倒序)
```

Phase C 实现 #2 + #3 + #4 简化版 + #5 简化版(完整版可 Phase D/E 再调)。

**简化策略**:
- `rules` 已经是 GuardInput.rules 字段,**不需要**塞进 references(避免重复)
- world_law / character / event 通过 `r.fragment.metadata["kind"]` 分组排序
- recent_turns:取 `turn_store.load_recent(session_id=..., n=config.recent_turns_count)`,每个 turn 转一个 ReferenceItem,label=`recent_turn:{turn_index}`,content=简短摘要

- [ ] **Step 1: 写 references 顺序测试**

追加到 `tests/test_turn_loop.py`(注意 `_build_components` helper 已经在文件里,不要重复):

```python
@pytest.mark.asyncio
async def test_turn_loop_build_references_orders_world_law_recent_characters_events(tmp_path: Path):
    """spec §7.B references 顺序:world_law > recent_turns > character > event。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig
    from core.world_memory import MemoryRecord

    gateway = FakeStructuredGateway()
    # 仅 1 个 narrative + 1 个 guard accept(我们查 guard 收到的 references 顺序)
    gateway.queue_response(_Beat, _Beat(narration="ok"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    narrative, guard, wm, store = _build_components(gateway=gateway, tmp_path=tmp_path)
    # 写入不同 kind 的记忆,Q 词都包含 "shared" 使所有都被召回
    wm.upsert(MemoryRecord(kind="world_law", content="shared world law text", source="s", session_id="sess_ref"))
    wm.upsert(MemoryRecord(kind="character", content="shared character text", source="s", session_id="sess_ref"))
    wm.upsert(MemoryRecord(kind="event", content="shared event text", source="s", session_id="sess_ref"))

    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=["world_law", "character", "event"],
            guard_rules=[],
        ),
    )
    await loop.run_turn(session_id="sess_ref", raw_text="shared query")

    # Guard 收到的 user message 的 references 部分(在 invocation #2 中)
    guard_user_msg = gateway.invocations[1].messages[1]
    # references 是 GuardInput.references list,序列化进 context JSON
    # 顺序应为 world_law(s) → character(s) → event(s)
    # 检查方式:三个文本在 content 中出现的 index
    world_law_idx = guard_user_msg.content.find("shared world law text")
    character_idx = guard_user_msg.content.find("shared character text")
    event_idx = guard_user_msg.content.find("shared event text")
    assert 0 <= world_law_idx < character_idx < event_idx, (
        f"references 顺序错: world_law@{world_law_idx} character@{character_idx} event@{event_idx}"
    )


@pytest.mark.asyncio
async def test_turn_loop_build_references_includes_recent_turns_summary(tmp_path: Path):
    """recent_turns 摘要应进入 Guard references。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    # 2 轮 turn:第 1 轮 accept,第 2 轮 verify references 含第 1 轮摘要
    for i in range(2):
        gateway.queue_response(_Beat, _Beat(narration=f"narration_{i}_unique_token"))
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
            retrieval_kinds=[],
            guard_rules=[],
            recent_turns_count=3,
        ),
    )

    await loop.run_turn(session_id="sess_recent", raw_text="action 0")
    await loop.run_turn(session_id="sess_recent", raw_text="action 1")

    # 第 2 轮 Guard 应收到第 1 轮的摘要(narration_0_unique_token 或 raw_text "action 0")
    second_guard_msg = gateway.invocations[3].messages[1]  # invocations: [n0, g0, n1, g1]
    assert "action 0" in second_guard_msg.content or "narration_0_unique_token" in second_guard_msg.content


@pytest.mark.asyncio
async def test_turn_loop_build_references_first_turn_has_no_recent_turns(tmp_path: Path):
    """第 1 轮 references 不含 recent_turns(没有历史)。"""
    from core.turn_loop import TurnLoop, TurnLoopConfig

    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="ok"))
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
            retrieval_kinds=[],
            guard_rules=[],
        ),
    )
    await loop.run_turn(session_id="sess_first", raw_text="first turn")

    guard_msg = gateway.invocations[1].messages[1]
    # 第 1 轮不应有 "recent_turn" label 字样(因为没有历史)
    assert "recent_turn:" not in guard_msg.content
```

- [ ] **Step 2: 跑测试,确认 fail**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_loop.py -v -k "build_references"
```

Expected:
- `orders_world_law_recent_characters_events` 可能 fail(因为当前 references 无明确排序,InMemoryRAG 返回的顺序不确定)
- `includes_recent_turns_summary` FAIL(当前 `_build_references` 不读 recent_turns)
- `first_turn_has_no_recent_turns` 可能 PASS(当前 references 也没 recent_turn,但只是因为根本没实现)

- [ ] **Step 3: 改写 `_build_references` 实施完整 spec §7.B 顺序**

打开 `src/core/turn_loop.py`,找到 `_build_references` 方法,完整替换为:

```python
    def _build_references(
        self,
        retrieved: list[RAGQueryResult],
        recent_turns: list[Turn],
    ) -> list[ReferenceItem]:
        """组装 GuardInput.references。spec §7.B 顺序:
        1. world_law(从 retrieved 中过滤 kind=world_law,top 5)
        2. recent_turns 摘要(player input + response_text,最近 N 轮)
        3. character(从 retrieved 中过滤 kind=character)
        4. event(从 retrieved 中过滤 kind=event,top 3)
        5. 其他 kind(retrieved 中剩余,保留兜底信息)

        注:rules 不进 references,作为 GuardInput.rules 单独传(避免重复)。
        """
        refs: list[ReferenceItem] = []

        by_kind: dict[str, list[RAGQueryResult]] = {}
        for r in retrieved:
            kind = r.fragment.metadata.get("kind", "memory")
            by_kind.setdefault(kind, []).append(r)

        # 1. world_law(top 5)
        for r in by_kind.get("world_law", [])[:5]:
            refs.append(ReferenceItem(
                label="world_law",
                content=r.fragment.content,
                score=r.score,
            ))

        # 2. recent_turns 摘要(只数 ok 的 turn,与 turn_index 计数一致)
        recent_ok_turns = [t for t in recent_turns if t.status == "ok"]
        # load_recent 返回的是按存盘顺序,我们要"最近 N",load_recent 已确保
        for turn in recent_ok_turns[-self.config.recent_turns_count:]:
            summary = self._summarize_turn_for_reference(turn)
            if summary:
                refs.append(ReferenceItem(
                    label=f"recent_turn:{turn.input.turn_index}",
                    content=summary,
                    score=None,
                ))

        # 3. character
        for r in by_kind.get("character", []):
            refs.append(ReferenceItem(
                label="character",
                content=r.fragment.content,
                score=r.score,
            ))

        # 4. event(top 3)
        for r in by_kind.get("event", [])[:3]:
            refs.append(ReferenceItem(
                label="event",
                content=r.fragment.content,
                score=r.score,
            ))

        # 5. 其他 kind 兜底(避免漏掉 player_state / relation 等)
        seen_kinds = {"world_law", "character", "event"}
        for kind, items in by_kind.items():
            if kind in seen_kinds:
                continue
            for r in items:
                refs.append(ReferenceItem(
                    label=kind,
                    content=r.fragment.content,
                    score=r.score,
                ))

        return refs

    @staticmethod
    def _summarize_turn_for_reference(turn: Turn) -> str:
        """把一个 Turn 摘要成 Guard reference 用的短文本。
        包含玩家输入 + 当时的 response_text(若有)。"""
        parts: list[str] = [f"player: {turn.input.raw_text}"]
        if turn.response_text:
            parts.append(f"response: {turn.response_text}")
        return " | ".join(parts)
```

注意:`_build_references` 的第二个参数 `recent_turns` 之前 Task 4-6 一直传入但没用。本 step 终于用上 — `recent_turns` 来自 `run_turn` ① 调的 `self.turn_store.load_session(session_id=...)` 的返回。

- [ ] **Step 4: 跑测试,确认 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_loop.py -v
```

Expected: 12 PASS(原 9 + 新 3)。

如果有 fail:
- `orders_world_law_recent_characters_events` fail → 检查 `_build_references` 顺序逻辑;可能要按 `RAGQueryResult.score` 二次排序
- 已有测试 fail → 可能因 references 多了 "recent_turn:N" 含义,影响某些断言;检查 `assert "rule" in content` 之类 — 应该没受影响

- [ ] **Step 5: 跑全套测试**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: 103 passed (100 prior + 3 new),1 skipped。

- [ ] **Step 6: import-graph 仍 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_import_graph.py -v
```

Expected: 2 PASS。注:`character` / `event` 是 `_FORBIDDEN_GAME_TERMS` 里的词,但它们只是 `r.fragment.metadata.get("kind")` 的字符串字面值(由 game 层定义)— 不是 hardcoded 在 core 代码里。让我确认:

在 turn_loop.py 中,`"world_law"` / `"character"` / `"event"` 出现在字符串字面值中(`by_kind.get("world_law", [])` 等)。这**会被 import_graph 测试 catch** — 因为 regex 扫文件文本(注释外)。

**应对**(本 step 写代码前先调整):把这些 kind 字符串抽到 `TurnLoopConfig` 字段作为 config-injected:

```python
class TurnLoopConfig(BaseModel):
    # ... 既有字段 ...
    world_law_kind: str = "world_law"  # game 域 kind 名,默认 "world_law"
    character_kind: str = "character"
    event_kind: str = "event"
```

但这又过度工程化(YAGNI)。**更好的方案**:把 `_build_references` 中的硬编码 kind 字符串改成**从 config 中 pop 出来**:

```python
class TurnLoopConfig(BaseModel):
    # ... 既有字段 ...
    references_priority_kinds: list[str] = Field(
        default_factory=lambda: ["world_law", "character", "event"],
    )
```

然后 `_build_references` 按 `self.config.references_priority_kinds` 排序。这样 core 没有硬编码 game 域词。

**但** `world_law` / `character` / `event` 出现在 default_factory 的 lambda 内部 — 仍然是字面值在 .py 文件里。`character` 在 `_FORBIDDEN_GAME_TERMS` 里!这会 fail。

最终方案:**default_factory 用 `list` 传空,然后 game 层显式注入**:

```python
class TurnLoopConfig(BaseModel):
    references_priority_kinds: list[str] = Field(default_factory=list)
```

core 不知道哪些 kind 优先,完全由 game 注入。Phase D 时 text_adventure 配 `["world_law", "character", "event"]`。

**但 Phase C 的测试用例需要排序,我们必须传 priority_kinds**。让 `TurnLoopConfig.references_priority_kinds` 默认空 list,`_build_references` 按 priority_kinds 顺序输出 + 兜底剩余 kind:

```python
    def _build_references(
        self,
        retrieved: list[RAGQueryResult],
        recent_turns: list[Turn],
    ) -> list[ReferenceItem]:
        """spec §7.B references 顺序由 config.references_priority_kinds 决定。
        recent_turns 摘要(最近 N 个 ok turn)在 priority kinds 第一项后注入。"""
        refs: list[ReferenceItem] = []

        by_kind: dict[str, list[RAGQueryResult]] = {}
        for r in retrieved:
            kind = r.fragment.metadata.get("kind", "memory")
            by_kind.setdefault(kind, []).append(r)

        seen_kinds: set[str] = set()
        priority = self.config.references_priority_kinds

        # 第 1 个 priority kind(典型:world_law)
        if priority:
            first_kind = priority[0]
            for r in by_kind.get(first_kind, []):
                refs.append(ReferenceItem(label=first_kind, content=r.fragment.content, score=r.score))
            seen_kinds.add(first_kind)

        # recent_turns 摘要(只 status=ok)
        recent_ok = [t for t in recent_turns if t.status == "ok"]
        for turn in recent_ok[-self.config.recent_turns_count:]:
            summary = self._summarize_turn_for_reference(turn)
            if summary:
                refs.append(ReferenceItem(
                    label=f"recent_turn:{turn.input.turn_index}",
                    content=summary,
                    score=None,
                ))

        # 后续 priority kinds(典型:character / event)
        for kind in priority[1:]:
            for r in by_kind.get(kind, []):
                refs.append(ReferenceItem(label=kind, content=r.fragment.content, score=r.score))
            seen_kinds.add(kind)

        # 5. 其他兜底
        for kind, items in by_kind.items():
            if kind in seen_kinds:
                continue
            for r in items:
                refs.append(ReferenceItem(label=kind, content=r.fragment.content, score=r.score))

        return refs

    @staticmethod
    def _summarize_turn_for_reference(turn: Turn) -> str:
        parts: list[str] = [f"player: {turn.input.raw_text}"]
        if turn.response_text:
            parts.append(f"response: {turn.response_text}")
        return " | ".join(parts)
```

并相应在 `TurnLoopConfig` 中加 field:

```python
class TurnLoopConfig(BaseModel):
    # ... 既有字段 ...
    references_priority_kinds: list[str] = Field(default_factory=list)
```

**测试必须传 priority_kinds**:

```python
config=TurnLoopConfig(
    narrative_output_schema=_Beat,
    response_text_field="narration",
    retrieval_kinds=["world_law", "character", "event"],
    references_priority_kinds=["world_law", "character", "event"],
    guard_rules=[],
),
```

**这种方式 core 不含游戏域词,但需要回去修测试 — 增加复杂度**。

---

**实务决策**:`_FORBIDDEN_GAME_TERMS` 是 Phase A 拍的禁词,主要为防 "core 不知不觉染上游戏域"。但 `world_law` / `character` / `event` 是 **kind 标签字符串**,本质上是 game 与 core 之间的 contract — game 决定有哪些 kind,core 按 kind 路由记忆。如果 core 完全不知道 kind 字符串,排序就要靠 config 注入,增加 game 层维护成本。

**两条路**:
- (A) 完全 config-driven(references_priority_kinds 由 game 注入,core 不含 kind 字面值)— 严格守原则但更繁琐
- (B) 修改 `_FORBIDDEN_GAME_TERMS` 把 `character` / `event` 从禁词集移除(因为它们是通用 RAG kind 标签,不是游戏域具体概念,跟 "scene / faction / combat" 不同) — 实用务实

**本 plan 采用 (A)** — 保持原则纯净,长期可维护性更好。代价是测试要传 priority_kinds 配置。后面的 Task 4 集成测试也要传。

继续 Step 4 改写:

请实施上面给出的 (A) 方案。`_build_references` 用 `self.config.references_priority_kinds` 决定 kind 顺序。`TurnLoopConfig` 加 `references_priority_kinds: list[str] = Field(default_factory=list)`。

Step 1 写的 3 个测试也需要更新,把 `config` 加 `references_priority_kinds=["world_law", "character", "event"]`(顺序对齐 spec §7.B 期望)。

请实施这两处改动(test config + production code),然后跑测试。

- [ ] **Step 7: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/core/turn_loop.py tests/test_turn_loop.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-c: task 3 — _build_references 完整(spec §7.B 顺序 + recent_turns 摘要)

Phase B 完成报告条目 1 实施。变更:
- TurnLoopConfig.references_priority_kinds: list[str] 由 game 注入,
  决定 references 中 kind 类记忆的输出顺序(spec §7.B:
  world_law > recent_turns > character > event > others)
- _build_references 按 priority_kinds 排,recent_turns 摘要在第一 priority
  kind 后注入(只数 status=ok 的 turn)
- _summarize_turn_for_reference 摘要 player input + response_text
- core/turn_loop.py 仍不含游戏域 kind 字面值(import-graph 仍 PASS)

3 个新测试 + 9 个现有测试全 PASS。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 集成测试 — spec §7.A 一致性失败分类

**Files:**
- Create: `tests/test_turn_loop_integration.py`(5 类一致性失败 + Guard 决策验证)

**目标**(Phase B 完成报告条目 1 + spec §7.A):TurnLoop 应该能在合理 Guard prompt + references 下,识别并 reject 6 类一致性失败。Phase B 已覆盖 accept / revise / reject 决策路径,Phase C 加"**真实场景**的 reject 触发"测试 — 写入 WorldMemory 一条 world_law,让 narrative 提案违反它,验证 references 包含该 world_law,Guard 收到 → reject → 降级。

**Phase C 实施范围**:5 类失败(spec §7.A 列了 6 类,选其中 5 个;选择漏掉的可在 Phase D 集成 text_adventure 后再补):
1. 法则违反(world_law)
2. 事实矛盾(event)
3. 状态遗忘(player_state)
4. 时空错乱(location)
5. 选择无后果(event,选项产生后果未沉淀)

**第 6 类(角色串味)** Phase D 实现,因为它需要 game 层 NPC schema。

测试用 `FakeStructuredGateway` 编排 Narrative 返回有问题的内容 + Guard 返回 reject,验证 TurnLoop 把违反信息正确写到 references / Guard 拿到完整 context。

- [ ] **Step 1: 写 5 个集成测试到新建 `tests/test_turn_loop_integration.py`**

```python
"""Spec §7.A 一致性失败分类集成测试。

每个测试模拟一类一致性失败:WorldMemory 中预存"事实",NarrativeAgent 生成
违反该事实的提案,Guard 收到完整 references(含事实 + recent turns)→ reject
→ TurnLoop 降级。验证 references 装配正确 + 降级路径正确。
"""

from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from core.agents.guard import ConsistencyGuard, GuardDecision, GuardFinding
from core.agents.narrative import NarrativeAgent
from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile
from core.rag_repository import InMemoryRAGRepository
from core.turn_loop import TurnLoop, TurnLoopConfig
from core.turn_store import TurnStore
from core.world_memory import MemoryRecord, WorldMemory
from tests._fakes import FakeStructuredGateway


class _Beat(BaseModel):
    narration: str = Field(min_length=1)
    new_facts: list[str] = Field(default_factory=list)


def _build_loop(*, gateway: FakeStructuredGateway, tmp_path: Path, retrieval_kinds: list[str]) -> tuple[TurnLoop, WorldMemory]:
    """Helper:构造完整 TurnLoop + WorldMemory,统一配 priority_kinds。"""
    runtime = AgentRuntime(gateway=gateway)
    narrative = NarrativeAgent(
        runtime=runtime,
        profile=AgentProfile(id="n", name="N", role="narrator", objective="o"),
    )
    guard = ConsistencyGuard(
        runtime=runtime,
        profile=AgentProfile(id="g", name="G", role="guard", objective="o"),
    )
    wm = WorldMemory(repository=InMemoryRAGRepository())
    store = TurnStore(data_dir=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=retrieval_kinds,
            references_priority_kinds=retrieval_kinds,
            guard_rules=[],
        ),
    )
    return loop, wm


@pytest.mark.asyncio
async def test_consistency_failure_world_law_violation(tmp_path: Path):
    """spec §7.A 法则违反:world_law 中 '魔法需血液代价',narrative 让 NPC 免费施法,Guard reject。"""
    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="NPC Alice 凭空施放火球术,毫无代价。"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(
                severity="error",
                message="violates world_law: 魔法需血液代价",
            )],
        ),
    )

    loop, wm = _build_loop(gateway=gateway, tmp_path=tmp_path, retrieval_kinds=["world_law"])
    wm.upsert(MemoryRecord(
        kind="world_law", content="魔法需血液代价,无血则无法施法",
        source="seed", session_id="sess_law",
    ))

    result = await loop.run_turn(session_id="sess_law", raw_text="让 Alice 施法")

    assert result.turn.status == "degraded"
    # Guard 应收到 world_law 内容在 references 中
    guard_msg = gateway.invocations[1].messages[1]
    assert "魔法需血液代价" in guard_msg.content
    # metadata 记录 reject 原因
    assert "world_law" in str(result.turn.metadata.get("guard_rejection", {}))


@pytest.mark.asyncio
async def test_consistency_failure_event_contradicts_past(tmp_path: Path):
    """spec §7.A 事实矛盾:event 中 '国王 Aldric 已死',narrative 让他出场,Guard reject。"""
    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="国王 Aldric 走进大殿,向你示意。"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(severity="error", message="contradicts event: 国王 Aldric 已死")],
        ),
    )

    loop, wm = _build_loop(gateway=gateway, tmp_path=tmp_path, retrieval_kinds=["event"])
    wm.upsert(MemoryRecord(
        kind="event", content="国王 Aldric 在 turn 3 被暗杀身亡",
        source="turn:3", session_id="sess_event",
    ))

    result = await loop.run_turn(session_id="sess_event", raw_text="进入王宫")

    assert result.turn.status == "degraded"
    guard_msg = gateway.invocations[1].messages[1]
    assert "Aldric" in guard_msg.content
    assert "暗杀" in guard_msg.content or "已死" in guard_msg.content


@pytest.mark.asyncio
async def test_consistency_failure_player_state_forgotten(tmp_path: Path):
    """spec §7.A 状态遗忘:player_state 中 '玩家持有黄铜钥匙',narrative 让玩家再找一次。"""
    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="你在地上发现了一把黄铜钥匙,捡起。"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(severity="error", message="player_state forgotten: 玩家已持有黄铜钥匙")],
        ),
    )

    loop, wm = _build_loop(gateway=gateway, tmp_path=tmp_path, retrieval_kinds=["player_state"])
    wm.upsert(MemoryRecord(
        kind="player_state", content="玩家持有: 黄铜钥匙(turn 2 获得)",
        source="turn:2", session_id="sess_state",
    ))

    result = await loop.run_turn(session_id="sess_state", raw_text="在房间里搜索")

    assert result.turn.status == "degraded"
    guard_msg = gateway.invocations[1].messages[1]
    assert "黄铜钥匙" in guard_msg.content


@pytest.mark.asyncio
async def test_consistency_failure_location_jump(tmp_path: Path):
    """spec §7.A 时空错乱:上一轮 turn 在森林,narrative 把玩家瞬间挪到酒馆。
    通过 recent_turns 引入位置信息,而非 location kind(简化:rely on recent_turn 摘要)。"""
    gateway = FakeStructuredGateway()
    # 第 1 轮:accept,玩家在森林
    gateway.queue_response(_Beat, _Beat(narration="你站在森林深处,四周是高大的橡树。"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))
    # 第 2 轮:narrative 突然让玩家在酒馆 → reject
    gateway.queue_response(_Beat, _Beat(narration="你坐在酒馆吧台前,要了一杯麦酒。"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(
                severity="error",
                message="location jump: 上一轮在森林,本轮跳到酒馆,无移动叙事",
            )],
        ),
    )

    loop, wm = _build_loop(gateway=gateway, tmp_path=tmp_path, retrieval_kinds=[])

    r0 = await loop.run_turn(session_id="sess_loc", raw_text="环顾四周")
    assert r0.turn.status == "ok"

    r1 = await loop.run_turn(session_id="sess_loc", raw_text="说点什么")
    assert r1.turn.status == "degraded"
    # 第 2 轮 Guard 应在 references 中看到第 1 轮的 "森林" 摘要
    second_guard_msg = gateway.invocations[3].messages[1]
    assert "森林" in second_guard_msg.content


@pytest.mark.asyncio
async def test_consistency_failure_choice_without_consequence(tmp_path: Path):
    """spec §7.A 选择无后果:上一轮玩家'杀了 NPC Bob',本轮 narrative 让 Bob 仍出场。
    通过 event 类记忆引入(模拟 Curator 已沉淀 'Bob 已死' 事件)。"""
    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="NPC Bob 笑着走过来跟你打招呼。"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(severity="error", message="choice consequence ignored: Bob 已死")],
        ),
    )

    loop, wm = _build_loop(gateway=gateway, tmp_path=tmp_path, retrieval_kinds=["event"])
    wm.upsert(MemoryRecord(
        kind="event", content="玩家在 turn 5 击杀了 NPC Bob",
        source="turn:5", session_id="sess_choice",
    ))

    result = await loop.run_turn(session_id="sess_choice", raw_text="走进酒馆")

    assert result.turn.status == "degraded"
    guard_msg = gateway.invocations[1].messages[1]
    assert "Bob" in guard_msg.content
    assert "击杀" in guard_msg.content
```

注意:这些测试**不验证 Guard 的实际推理能力**(那是 LLM 行为,需要 live 测试)— 只验证:
1. TurnLoop 把违反相关的 references 正确传给 Guard(即 references 装配工作)
2. Guard 返回 reject 时,TurnLoop 走降级路径正确

实际"Guard 能不能看出 reject"在 Phase D / live smoke 验证。

- [ ] **Step 2: 跑测试,确认 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_turn_loop_integration.py -v
```

Expected: 5 PASS。

- [ ] **Step 3: 跑全套**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: 108 passed (103 prior + 5 new),1 skipped。

- [ ] **Step 4: import-graph 仍 PASS(测试文件不在 src/core 下,不受限制)**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_import_graph.py -v
```

Expected: 2 PASS。

- [ ] **Step 5: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add tests/test_turn_loop_integration.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-c: task 4 — 集成测试覆盖 spec §7.A 5 类一致性失败

5 个集成测试模拟一致性失败场景,验证 TurnLoop 把违反信息正确传给 Guard
(references 装配)+ Guard reject 时降级路径正确:
- 法则违反(world_law):魔法需血液代价 vs 凭空施法
- 事实矛盾(event):国王已死 vs 国王出场
- 状态遗忘(player_state):已持有钥匙 vs 重新发现
- 时空错乱(recent_turn):上轮森林 vs 本轮酒馆
- 选择无后果(event):已击杀 NPC vs NPC 出场

第 6 类(角色串味)需 game-specific NPC schema,留 Phase D 集成 text_adventure
后补。这些测试不验 Guard 的实际推理能力(用 FakeGateway 编排 reject),
只验 references 装配 + 降级路径 — Guard 真正推理由 Phase D / live smoke 验证。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Phase D contract 文档

**Files:**
- Create: `docs/superpowers/specs/extending-the-engine.md`

**目标**(Phase A 完成报告 §F.4 列出的 Phase B/C/D 准备工作):新 game 域开发者要实现 5 个契约就能挂上 core 跑通新 demo。文档列出契约 + mini example(伪 game 域代码,不实际跑)。

- [ ] **Step 1: 写文档**

创建 `/Users/fangkai/ai_work/games/AI_RPG/docs/superpowers/specs/extending-the-engine.md`:

```markdown
# Extending the AI_RPG Engine: New Game Domain Contracts

> 适用读者:为 AI_RPG core 引擎写新 game 域 demo 的开发者(包括未来的 Phase D `text_adventure` 自己)。
> 关联 spec:[2026-05-26-turn-loop-engine-redesign-design.md](2026-05-26-turn-loop-engine-redesign-design.md)
> 关联 Phase 完成报告:[Phase A](../plans/2026-05-26-phase-a-completion-report.md) / [Phase B](../plans/2026-05-27-phase-b-completion-report.md)

## 概览

AI_RPG core 是个 game-agnostic 引擎。任何 game 域只要实现下面 5 个契约,
就能挂上 core 跑通一个完整的 turn 循环:

1. **NarrativeBeat schema**(Pydantic):game 自定义的叙事输出格式
2. **MemoryKind 集合**(Enum / list[str]):game 自定义的记忆类别
3. **NarrativePromptBuilder**(可选):注入 game-specific narrative prompt
4. **MemoryCurator**(可选):从 NarrativeBeat 提取要进 WorldMemory 的 records
5. **CLI app entry**:`python -m game.<my_game>.app` 跑通对话

core 不需要任何 game-specific 代码,Phase D `text_adventure` 是第一个证明性实例。

---

## 契约 1: NarrativeBeat schema

每个 game 域定义自己的 NarrativeBeat(NarrativeAgent.run 的 output_schema)。
约定:必须含**一个返回给玩家看的文本字段**(field name 通过 TurnLoopConfig.response_text_field 配置)。

```python
# game/<my_game>/schemas.py
from pydantic import BaseModel, Field


class MyGameBeat(BaseModel):
    narration: str = Field(min_length=1)         # ← 给玩家看,response_text_field 指向这里
    new_facts: list[str] = Field(default_factory=list)
    # 任意其他字段:choices / npc_dialogues / scene_tags / ...
```

Core 不知道也不关心 `new_facts` 或其他字段长什么样。

## 契约 2: MemoryKind 集合

game 自定义合法的 memory kind(在 WorldMemory.upsert 时打 metadata["kind"])。
Core 用 `kind: str` 不限制具体值,但 `TurnLoopConfig.references_priority_kinds`
和 `MemoryQuery.kinds` 都依赖一致的 kind 字符串集。

```python
# game/<my_game>/schemas.py
from enum import Enum


class MyGameMemoryKind(str, Enum):
    WORLD_LAW = "world_law"
    LOCATION = "location"
    CHARACTER = "character"
    EVENT = "event"
    PLAYER_STATE = "player_state"
```

## 契约 3: NarrativePromptBuilder(可选 — 用 instruction override)

默认 core 自带 `DEFAULT_NARRATIVE_INSTRUCTION`(通用 prose,不含游戏域词)。
game 想注入自己的 prompt:

```python
# game/<my_game>/narrative_agent.py
from core.agents.narrative import NarrativeAgent
from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile


MY_GAME_NARRATIVE_PROMPT = """
你是 <我的游戏> 的叙事 agent。
- 风格:简洁、直接、带轻微悬疑感
- 字数:每段 ≤ 80 字
- 必须输出 JSON 符合 MyGameBeat schema
- 若有新角色出场,记得在 new_facts 列出
"""


def build_my_game_narrative_agent(*, runtime: AgentRuntime) -> NarrativeAgent:
    profile = AgentProfile(
        id="my_game_narrator",
        name="MyGameNarrator",
        role="narrator",
        objective="生成 <我的游戏> 的下一段叙事",
        temperature=0.8,
        max_tokens=2048,
    )
    return NarrativeAgent(
        runtime=runtime,
        profile=profile,
        instruction=MY_GAME_NARRATIVE_PROMPT,  # ← 注入,覆盖 default
    )
```

ConsistencyGuard 同理(`instruction=MY_GAME_GUARD_PROMPT`)。

## 契约 4: MemoryCurator(Phase D 加,Phase C 暂未实现)

把 NarrativeBeat 中 LLM 提到的新事实,经 4 道闸过滤后存进 WorldMemory:

```python
# game/<my_game>/memory_curator.py
from core.world_memory import MemoryRecord, WorldMemory


class MyGameCurator:
    def __init__(self, *, world_memory: WorldMemory) -> None:
        self.world_memory = world_memory

    def curate(self, *, beat: MyGameBeat, session_id: str, turn_index: int) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        for fact in beat.new_facts:
            kind = self._classify(fact)
            if kind is None:
                continue  # confidence too low / 不合法 kind
            existing = self.world_memory.find_similar(content=fact, session_id=session_id)
            if existing:
                continue  # 去重闸
            records.append(MemoryRecord(
                kind=kind.value,
                content=fact,
                source=f"turn:{turn_index}",
                session_id=session_id,
                confidence=0.85,
            ))
        return records

    def _classify(self, fact: str) -> MyGameMemoryKind | None:
        # 简单关键词分类(Phase D 简化版,future 上 LLM)
        if "law" in fact or "rule" in fact:
            return MyGameMemoryKind.WORLD_LAW
        if "location" in fact:
            return MyGameMemoryKind.LOCATION
        # ... 其他规则
        return None  # 没分到 → 丢弃
```

**注意**:Phase B/C 阶段 TurnLoop 的 `curated_records=[]` hardcoded,
Phase D 时需要把 Curator 接进 TurnLoop(或 TurnLoop 之外的 wrapper)。
当前最简集成方式:用 wrapper 函数:

```python
async def run_turn_with_curator(loop, curator, session_id, raw_text):
    result = await loop.run_turn(session_id=session_id, raw_text=raw_text)
    if result.turn.status == "ok" and result.turn.narrative_draft:
        beat = MyGameBeat.model_validate(result.turn.narrative_draft)
        records = curator.curate(
            beat=beat,
            session_id=session_id,
            turn_index=result.turn.input.turn_index,
        )
        curator.world_memory.upsert_many(records)
    return result
```

(Phase D 决定是否把这个 wrapper 提升为 core API。)

## 契约 5: CLI app entry

```python
# game/<my_game>/app.py
import argparse
import asyncio
from pathlib import Path

from core.agents.guard import ConsistencyGuard
from core.agents.narrative import NarrativeAgent
from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile
from core.config import AppSettings
from core.llm_gateway import LLMGateway
from core.rag_repository import InMemoryRAGRepository
from core.turn_loop import TurnLoop, TurnLoopConfig
from core.turn_store import TurnStore
from core.world_memory import WorldMemory

from game.my_game.schemas import MyGameBeat, MyGameMemoryKind


async def async_main(args):
    settings = AppSettings()
    gateway = LLMGateway(
        api_key=settings.mimo_api_key,
        base_url=settings.mimo_base_url,
        default_model=settings.mimo_model,
    )
    runtime = AgentRuntime(gateway=gateway)
    loop = TurnLoop(
        narrative_agent=NarrativeAgent(
            runtime=runtime,
            profile=AgentProfile(id="n", name="Narrator", role="narrator", objective="gen narrative"),
        ),
        guard=ConsistencyGuard(
            runtime=runtime,
            profile=AgentProfile(id="g", name="Guard", role="guard", objective="check consistency"),
        ),
        world_memory=WorldMemory(repository=InMemoryRAGRepository()),
        turn_store=TurnStore(data_dir=Path("data/sessions")),
        config=TurnLoopConfig(
            narrative_output_schema=MyGameBeat,
            response_text_field="narration",
            retrieval_kinds=[k.value for k in MyGameMemoryKind],
            references_priority_kinds=[
                MyGameMemoryKind.WORLD_LAW.value,
                MyGameMemoryKind.LOCATION.value,
                MyGameMemoryKind.CHARACTER.value,
                MyGameMemoryKind.EVENT.value,
            ],
            guard_rules=[
                "不要让已死亡角色出场",
                "不要让玩家凭空获得物品",
            ],
        ),
    )

    session_id = args.resume or "default"
    print(f"=== Session: {session_id} ===")
    while True:
        user_input = input("> ").strip()
        if not user_input or user_input == "/quit":
            break
        result = await loop.run_turn(session_id=session_id, raw_text=user_input)
        print(result.response_text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", help="Resume an existing session_id")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
```

跑:`python -m game.my_game.app` 或 `python -m game.my_game.app --resume <id>`。

## Phase D 准备清单

Phase D 实现 `game/text_adventure/` 时,按上述 5 个契约逐个落地。
预期工作量(参考):
- schemas.py(契约 1+2):~50 行
- narrative_agent.py(契约 3):~30 行
- memory_curator.py(契约 4):~80 行
- app.py(契约 5):~100 行
- guard_rules.py:~20 行
- prompts.py(可拆分 instruction):~50 行
- 测试:每模块对应 ~3-5 个测试,总 ~25-40 个测试

总计 ~330 行 src + ~300 行 test。**Phase D 完成的 success metric**:跑 10 轮玩家自由对话 + Guard accept 率 ∈ [70%, 90%] + 至少一次成功拦截真实矛盾。

## 已知未实现项(Phase C 之后)

- MemoryCurator 没接进 TurnLoop(Phase D 用 wrapper)
- ChromaRAG 没接 live(Phase D 或后期切换)
- Live LLM smoke tests(Phase D 跑通 demo 后做)
- world_init 仍在 core/agents/debate.py(物理移动到 game/world_init/ 留 Phase E)
- TurnTelemetry 缺 new_facts_kept / total_tokens(Phase D 加 Curator 后填)
```

- [ ] **Step 2: 验证文档可读**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && wc -l docs/superpowers/specs/extending-the-engine.md
```

Expected: ~250+ 行。

- [ ] **Step 3: Commit**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add docs/superpowers/specs/extending-the-engine.md
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-c: task 5 — Phase D contract 文档

extending-the-engine.md 列出 game 域要实现的 5 个契约 +
mini example(伪 game 域代码):
1. NarrativeBeat schema
2. MemoryKind 集合
3. NarrativePromptBuilder(可选,用 instruction override)
4. MemoryCurator(Phase D wrapper 接入)
5. CLI app entry

包含 Phase D 实施清单(预估代码量 + success metric)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Phase C 收尾

**Files:**
- 跑 ruff cleanup
- 跑全套测试 + 覆盖率
- 打 `phase-c-complete` tag
- 写 `docs/superpowers/plans/2026-05-27-phase-c-completion-report.md`

- [ ] **Step 1: ruff scan + auto-fix**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/ruff check --select F401,F811 --fix src/ tests/ scripts/
```

Expected: "All checks passed!" 或修若干 unused imports。

- [ ] **Step 2: 全套测试 + 覆盖率**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py --cov=src/core --cov-report=term-missing -q 2>&1 | tail -30
```

Expected: ~108 passed,1 skipped。`src/core/turn_loop.py` 覆盖率应保持 ≥ 95%。

- [ ] **Step 3: import-graph 仍 PASS**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_import_graph.py -v
```

Expected: 2 PASS。

- [ ] **Step 4: Commit cleanup(若 ruff 修了)**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG status
# 若有改动:
git -C /Users/fangkai/ai_work/games/AI_RPG add -A
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "phase-c: task 6 收尾 — ruff F401/F811 清扫"
```

- [ ] **Step 5: 打 tag**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG tag -a phase-c-complete -m "Phase C: references 完整 + 续接能力 + Phase D 契约就位 (6 tasks)"
git -C /Users/fangkai/ai_work/games/AI_RPG tag --list | grep phase
```

- [ ] **Step 6: 写完成报告**

创建 `/Users/fangkai/ai_work/games/AI_RPG/docs/superpowers/plans/2026-05-27-phase-c-completion-report.md`:

```markdown
# Phase C 完成报告

日期:2026-05-27(完成日)
关联 plan:[2026-05-27-phase-c-references-and-extensibility.md](2026-05-27-phase-c-references-and-extensibility.md)
关联 spec:[2026-05-26-turn-loop-engine-redesign-design.md](../specs/2026-05-26-turn-loop-engine-redesign-design.md)
分支:`codex/world-init-live-smoke`
里程碑 tag:`phase-c-complete`

## 概览

Phase C 6 个 task 全部完成,~108 测试 PASS。TurnLoop references 升级到 spec
§7.B 完整顺序(world_law > recent_turns > characters > events),含 recent_turns
摘要。TurnStore 加 list_sessions() 支持 `--resume`。LLMGateway 重构到 monotonic
clock(技术债清理)。5 类一致性失败有集成测试覆盖。Phase D contract 文档落地,
text_adventure 实施可直接照搬。

## 完成的 Task

| Task | 内容 | 主要 commit |
|------|------|------------|
| 1 | LLMGateway monotonic clock 重构 | `<sha>` |
| 2 | TurnStore.list_sessions() | `<sha>` |
| 3 | _build_references 完整 + recent_turns 摘要 | `<sha>` |
| 4 | 集成测试 spec §7.A 5 类一致性失败 | `<sha>` |
| 5 | Phase D contract 文档 | `<sha>` |
| 6 | 收尾(ruff + tag + 报告) | `<sha>` |

## 新增文件

- `tests/test_turn_loop_integration.py`(5 类失败集成测试)
- `docs/superpowers/specs/extending-the-engine.md`(Phase D 契约)

## 修改的文件

- `src/core/llm_gateway.py`(monotonic clock)
- `src/core/turn_store.py`(加 list_sessions)
- `src/core/turn_loop.py`(_build_references 完整 + references_priority_kinds config)
- 对应测试

## 与 Phase B 完成报告"留 Phase C"清单的对照

| Phase B 遗留 | Phase C 处理状态 |
|------|---------|
| `_build_references` 简化版 | ✅ Task 3 完整实施(spec §7.B 顺序 + recent_turns) |
| Curator 完全没沉淀 | ⚠️ 留 Phase D(Curator 是 game 层,Phase D wrapper 接入) |
| Guard prompt 仍 generic | ⚠️ 留 Phase D(text_adventure 通过 instruction override 注入) |
| WorldMemory.find_similar 阈值 | ⚠️ 留 Phase D / E(切 ChromaRAG 时校准) |
| LLMGateway monotonic clock | ✅ Task 1 完成 |

## 已知遗留 / 留给 Phase D

1. **Curator wrapper 接入**:Phase D 实现 MemoryCurator 后,需要在 TurnLoop 外部或内部接入,把 `curated_records=[]` 改为真实沉淀(contract 文档 §4 给出 wrapper 方案)
2. **`extending-the-engine.md` 中 Curator wrapper 是否提升为 core API**:Phase D 实施后根据维护体感决定
3. **text_adventure CLI `--resume <id>` 加交互式 session 选择**(list_sessions 已就位,UI 待加)
4. **LLMGateway code review minor**(Phase B Task 3 review 余项,未在 Phase C 修):
   - `complete()` 末尾 "unreachable" 路径 error message
   - `failure_threshold` docstring 说明计 logical complete() 调用而非 HTTP retry

## 下一步:Phase D 写 plan

Phase D 主要内容(spec §9 + extending-the-engine.md 契约):
- `game/text_adventure/` 全套(5 个契约逐项落地)
  - schemas.py(NarrativeBeat / MemoryKind)
  - narrative_agent.py(instruction 注入)
  - memory_curator.py(四道闸:Schema / Confidence / 去重 / 冲突)
  - guard_rules.py
  - app.py(CLI + --resume)
- 5-10 个 game-specific 测试
- 一次手动 live smoke(MIMO_API_KEY 跑通 1 轮)
- MVP 验收清单初步达成(spec §8.F)
```

- [ ] **Step 7: Commit 报告 + 重打 tag**

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add docs/superpowers/plans/2026-05-27-phase-c-completion-report.md
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "phase-c: 完成报告"
git -C /Users/fangkai/ai_work/games/AI_RPG tag -d phase-c-complete
git -C /Users/fangkai/ai_work/games/AI_RPG tag -a phase-c-complete -m "Phase C: references 完整 + 续接能力 + Phase D 契约就位"
git -C /Users/fangkai/ai_work/games/AI_RPG log --oneline -10
git -C /Users/fangkai/ai_work/games/AI_RPG tag --list | grep phase
```

---

## Phase C 自审

**1. Spec coverage:**
- spec §7.B references 顺序 → Task 3 ✓
- spec §7.A 6 类一致性失败 → Task 4 覆盖 5 类(角色串味留 Phase D 因为需要 NPC schema)
- spec §7.D monotonic clock → Task 1 ✓
- spec §8.C 集成测试 → Task 4 ✓
- spec §6.4 `--resume` 续接基础 → Task 2 list_sessions ✓

**2. Placeholder scan:** 无 TBD / TODO / 模糊步骤。

**3. Type consistency:**
- `TurnLoopConfig.references_priority_kinds: list[str]` 在 Task 3 加,Task 4 测试用
- `TurnStore.list_sessions() -> list[str]` 在 Task 2 加,extending-the-engine.md 引用
- `LLMGateway.circuit_open_until: float | None` 在 Task 1 改,无下游消费(只 _record_failure / complete 内用)

**4. 跨 Phase 一致性:** Phase C plan 与 Phase B 完成报告的"留 Phase C"清单 5 项对应清晰(见 §完成报告对照表)。

---

## Phase C 结束后的衔接

Phase C 完成后,**Phase D 准备就绪**:contract 文档已就位,5 个契约清晰列出,
text_adventure 实施者可以直接照搬 mini example 改 game 域内容。

Phase D 重点不再是"core 该长什么样",而是"text_adventure 玩起来是什么样" —
设计重心从架构转到玩法。
