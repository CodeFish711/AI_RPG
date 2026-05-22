# Tick Loop v0 实现计划

日期：2026-05-22
对应 spec：`docs/superpowers/specs/2026-05-22-multi-agent-rpg-framework-design.md` 第 16.1 节、Phase 7

## 目标

把世界初始化产出的静态 `WorldSeed` + `CausalImpactPacket` 变成一个能逐 tick
推进的世界：延迟影响包按计划引爆、节点被唤醒推理、产出新影响、循环发酵。

工程模型：离散事件模拟。主循环是确定性代码，LLM 只在节点回合被调用一次，
输出经 Pydantic 校验后才允许提交。LLM 失败不阻断 tick 推进。

## 范围边界

**做**：确定性 tick 调度器、因果包 bootstrap、节点回合推理、提交与重新调度、
停止条件、端到端离线测试、live 演示脚本。

**不做（推后）**：真语义 embedding（v0 用 metadata 路由）、DAG 生成管线、
常驻 Runtime Entity Agent、语义缓存、熔断、Chroma 之外的持久化。

## 新增 / 改动文件

| 文件 | 职责 |
|---|---|
| `src/core/tick_bus.py` | 确定性调度器 `TickBus`，只认 node/event/tick |
| `src/game/world_sim/__init__.py` | 新包 |
| `src/game/world_sim/schemas.py` | `NodeTickOutcome`、`TickRecord`、`WorldTickResult` |
| `src/game/world_sim/agents.py` | 节点 agent profile |
| `src/game/world_sim/prompts.py` | `build_node_tick_task` |
| `src/game/world_sim/memory.py` | `node_outcome_to_fragments` |
| `src/game/world_sim/tick_workflow.py` | `WorldTickWorkflow`：bootstrap + 循环 |
| `src/core/agents/debate.py` | 改动：`DebateSession` 回填 `unresolved_tensions` |
| `scripts/live_world_sim.py` | live 演示：世界初始化 → 推演 N tick |
| `CLAUDE.md` | 补充 world_sim 架构说明与命令 |

## Schema 设计

**`game/world_sim/schemas.py`**

```python
class NodeTickOutcome(BaseModel):
    node_id: str = Field(min_length=1)
    tick: int = Field(ge=0)
    narrative: str = Field(min_length=1)
    proposed_changes: list[ProposedChange] = Field(default_factory=list)
    new_impacts: list[CausalImpact] = Field(default_factory=list)

class TickRecord(BaseModel):
    tick: int = Field(ge=0)
    event_ids: list[str]
    outcomes: list[NodeTickOutcome]

class WorldTickResult(BaseModel):
    world_seed_id: str
    final_tick: int
    records: list[TickRecord]
```

`ProposedChange` / `CausalImpact` 复用 `core/agents/schemas.py` 与
`game/world_init/schemas.py` 既有定义，不重复造。

## 实现步骤（按依赖顺序，每步自带测试，逐步 `python -m pytest` 保持绿色）

### 步骤 1 — `core/tick_bus.py`

`TickBus`（纯确定性，无 LLM、无领域概念）：

- `__init__`：`current_tick = 0`；`_nodes: dict[str, SimulationNode]`；
  `_scheduled: dict[int, list[TickEvent]]`（fire tick → 事件，保持插入顺序）。
- `register_node(node)` / `get_node(node_id) -> SimulationNode | None`。
- `schedule_event(event, fire_at_tick)`：要求 `fire_at_tick > current_tick`，
  否则抛 `ValueError`（不允许往过去调度）。
- `advance() -> list[TickEvent]`：`current_tick += 1`，弹出并返回本 tick 到期
  事件（无则空列表）。
- `pending_count() -> int`：剩余未引爆事件总数。

测试 `tests/test_tick_bus.py`：调度到未来 tick 后 `advance` 在正确 tick 引爆；
多事件保持插入顺序；`pending_count` 随引爆递减；往过去调度抛错。

### 步骤 2 — `game/world_sim/schemas.py`

按上文定义三个 schema，测试 `tests/test_world_sim_schemas.py` 覆盖必填校验、
默认值、`tick`/`final_tick` 的 `ge` 约束。

### 步骤 3 — `game/world_sim/agents.py` + `prompts.py`

- `agents.py`：`build_node_agent_profile()` — 角色是"模拟节点推演者"，
  `thinking=enabled`，复用 `world_init/agents.py` 的 `_profile` 风格。
- `prompts.py`：`build_node_tick_task(node, event, context_fragments) -> AgentTask`
  - `instruction`：让节点根据传入事件推演本回合发生了什么。
  - `context`：`{"node": node.model_dump(), "incoming_event": event.model_dump(),
    "retrieved_memory": [f.model_dump() for f in context_fragments]}`。
  - `required_output`：描述 `NodeTickOutcome` 字段；要求新影响只埋抽象
    `target_hint`，不直接改世界状态。

测试 `tests/test_world_sim_prompts.py`：context 携带节点与事件、`required_output`
含 `NodeTickOutcome`。

### 步骤 4 — `game/world_sim/memory.py`

`node_outcome_to_fragments(outcome, *, world_seed_id) -> list[MemoryFragment]`：
确定性转换，1 个 fragment，`metadata={"kind": "tick_outcome", "world_seed_id": ...,
"node_id": outcome.node_id, "tick": outcome.tick}`，content 含 narrative 与变更摘要。

测试 `tests/test_world_sim_memory.py`：fragment 数量、metadata、content 包含
narrative。

### 步骤 5 — `game/world_sim/tick_workflow.py`

`WorldTickWorkflow`：

- `__init__(self, *, runtime, repository, bus=None, max_ticks=8)`。
- `_node_from_impact(impact) -> SimulationNode`：`id` 由 `target_hint` 确定性
  slug 化（同 hint 复用同一节点，实现天然去重）；`node_type = impact.target_type`。
- `_event_from_impact(impact, node, world_seed_id) -> TickEvent`：
  `event_type="causal_impact"`，`source_id=world_seed_id`，`target_ids=[node.id]`，
  `payload=impact.model_dump()`。
- `bootstrap(causal_packet, world_seed_id)`：对每个 impact 派生节点 → 注册 →
  `schedule_event(event, current_tick + 1 + impact.delay_ticks)`。
- `run(causal_packet, world_seed_id) -> WorldTickResult`：
  ```text
  bootstrap
  for _ in range(max_ticks):
      if bus.pending_count() == 0: break
      due = bus.advance()
      for event in due:
          node = bus.get_node(event.target_ids[0])
          ctx = repository.hybrid_search("", metadata_filter={"world_seed_id": world_seed_id})
          outcome = runtime.run_agent(node_profile, build_node_tick_task(node, event, ctx), NodeTickOutcome)
          repository.upsert_batch(node_outcome_to_fragments(outcome, world_seed_id=...))
          for impact in outcome.new_impacts:
              派生节点 -> register -> schedule(current_tick + 1 + delay_ticks)
      记录 TickRecord
  return WorldTickResult(...)
  ```

测试 `tests/test_tick_workflow.py`（`FakeRuntime` + `InMemoryRAGRepository`，全离线）：
- 给定一个含 2 个 impact 的 `CausalImpactPacket`，bootstrap 后 `pending_count == 2`。
- 跑完后 `records` 非空、每个 outcome 通过校验、`tick_outcome` fragment 写入 RAG。
- FakeRuntime 在某个 outcome 里返回 `new_impacts` → 验证新事件被重新调度且后续
  tick 被处理。
- 队列清空时在 `max_ticks` 之前停止。

### 步骤 6 — 顺手修复 `unresolved_tensions` 死输入

`core/agents/debate.py` `DebateSession.run`：构造 `DebateSessionResult` 时把各
`DebateTurn.concerns` 聚合进 `unresolved_tensions`（去重、保序）。这样
`WorldInitWorkflow` 传给因果分析的 tensions 不再恒为空。`consensus_points` v0
暂不处理。扩展 `tests/test_debate.py` 覆盖聚合。

### 步骤 7 — `scripts/live_world_sim.py`

仿 `scripts/live_world_init.py`：`--live` 开关 + `--ticks` 参数；先跑
`run_world_init_mvp`，再用其 `causal_packet` 驱动 `WorldTickWorkflow`，打印每个
tick 的 narrative。新增 `tests/test_live_world_sim_script.py` 测参数解析与
未加 `--live` 时拒绝运行。

### 步骤 8 — 更新 `CLAUDE.md`

架构段补 `game/world_sim/` 与 `core/tick_bus.py` 说明；命令段补 live 推演脚本。

## 验收标准

1. `python -m pytest` 全绿，新增测试全部通过。
2. `WorldTickWorkflow` 能从一个 `CausalImpactPacket` bootstrap 并推进多个 tick。
3. 节点 outcome 里的 `new_impacts` 被重新调度，后续 tick 能继续处理。
4. 每个 tick outcome 以 `kind=tick_outcome` 写入 RAG。
5. 队列清空或达到 `max_ticks` 时干净停止。
6. 全流程离线可测；live 脚本仅 `--live` opt-in。
7. `core/tick_bus.py` 不出现任何领域名词，铁律 1 不破。

## 风险与注记

- **metadata 路由的局限**：v0 检索按 `world_seed_id` 过滤，节点拿到的是整个
  世界的记忆，不区分相关性。节点变多后需要真 embedding 或更细的 metadata
  （node_id / tags）路由 —— 列为 v0 之后第一优先项。
- **节点爆炸**：每个 outcome 都可能产新影响新节点。`max_ticks` 是硬上限；
  后续可加节点数 / 队列长度上限。
- **target_hint 去重**：靠 slug 化，措辞不同的同义 hint 会被当成不同节点。
  这是 metadata 路由阶段可接受的已知误差，真 embedding 阶段解决。
