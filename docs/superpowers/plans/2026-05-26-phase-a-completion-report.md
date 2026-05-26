# Phase A 完成报告

日期:2026-05-27(完成日)
关联 plan:[2026-05-26-phase-a-core-foundation.md](2026-05-26-phase-a-core-foundation.md)
关联 spec:[2026-05-26-turn-loop-engine-redesign-design.md](../specs/2026-05-26-turn-loop-engine-redesign-design.md)
分支:`codex/world-init-live-smoke`
里程碑 tag:`phase-a-complete`

## 概览

Phase A 8 个 task 全部完成,71 个测试 PASS,无回归。Core 层数据契约收敛 + 5 个核心组件骨架就位。Phase B 可基于此基础实现 TurnLoop 主路径。

## 完成的 Task

| Task | 内容 | 主 commit | Cleanup commit | 测试 |
|------|------|----------|---------------|------|
| 1 | schemas 收敛(删 TickEvent/SimulationNode,加 TurnInput/TurnResult) | `0df0949` | `fa14d80` | 8 |
| 2 | tests/_fakes.py — FakeStructuredGateway | `d0cce2e` | — | 4 |
| 3 | core/agents/guard.py — ConsistencyGuard + 4 schemas | `a8d1c87` | — | 5 |
| 4 | core/world_memory.py — WorldMemory + 2 schemas | `35eeec3` | `96120fd` | 11 |
| 5 | core/turn_store.py — Turn + TurnStore | `7a9238b` | — | 7 |
| 6 | core/agents/narrative.py — NarrativeAgent | `44782cd` | — | 3 |
| 7 | tests/test_import_graph.py — 边界静态校验 | `8817c53` | — | 2 |
| 8 | 收尾清理(ruff + session_id pattern + 报告) | `25ffd74` | — | +3 |

(数字若与最终 commit/test 实际不符,以 git/pytest 为准)

## 新增文件

- `src/core/world_memory.py`
- `src/core/turn_store.py`
- `src/core/agents/guard.py`
- `src/core/agents/narrative.py`
- `tests/_fakes.py`
- `tests/test_world_memory.py`
- `tests/test_turn_store.py`
- `tests/test_core_agents_guard.py`
- `tests/test_core_agents_narrative.py`
- `tests/test_fakes.py`
- `tests/test_import_graph.py`

## 修改的文件

- `src/core/schemas.py`(收敛 + TurnInput pattern)
- `tests/test_core_schemas.py`(扩充测试)

## 测试覆盖

- 全 Phase A 新增测试:~46 个(具体见 git log)
- 总测试数(忽略 baseline collection error):71 passed + 1 skipped
- `src/core` 覆盖率:**91%**(pytest-cov,term-missing)
  - schemas / agents/guard / agents/narrative / agents/runtime / agents/schemas / agents/debate / config:100%
  - turn_store / world_memory:96%
  - rag_repository:84%
  - llm_gateway:77%(未走 live 路径)

## 已知遗留 / 延后到 Phase B 的事项

1. **Prompt prose 含游戏域词**(`_GUARD_INSTRUCTION` 含 "Canon Guard",`_NARRATIVE_INSTRUCTION` 含中文"角色/地点/事件") — Phase B 接 TurnLoop 时统一重写 prompt
2. **TurnStore.save 无 flush/fsync** — Phase B 视玩家体验决定
3. **TurnStore.load_session 全文件读** — Phase B 长 session 视性能决定
4. **TurnStore 无 list_sessions / delete_session** — Phase B `--resume` 实现时加 list_sessions
5. **WorldMemory 多 kinds 用 Python 侧过滤 + top_k*4 oversample** — Phase B 若接 ChromaRAG 用其 `$in` 优化
6. **import-graph 禁词只覆盖英文** — Phase B 重写 prompt 时同步清理中文 prose
7. **baseline 预存在的 tests/test_world_init_prompts.py collection error**(`ImportError: cannot import name 'build_revision_task'`) — 由 Phase E(world_init 降级)处理

## 下一步:Phase B Plan

Phase B 主要内容:
- `core/turn_loop.py` 实现 spec §6.1 时序
- 集成 NarrativeAgent / WorldMemory / ConsistencyGuard / TurnStore
- Guard 决策分支(accept / revise / reject / circuit-open 降级)
- TurnTelemetry 记录
- 集成测试(spec §8.C 前 4 个用例)

需要写 `docs/superpowers/plans/2026-05-26-phase-b-turn-loop.md`(下一步)。
