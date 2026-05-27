# Phase B 完成报告

日期:2026-05-27(完成日)
关联 plan:[2026-05-27-phase-b-turn-loop.md](2026-05-27-phase-b-turn-loop.md)
关联 spec:[2026-05-26-turn-loop-engine-redesign-design.md](../specs/2026-05-26-turn-loop-engine-redesign-design.md)
分支:`codex/world-init-live-smoke`
里程碑 tag:`phase-b-complete`

## 概览

Phase B 7 个 task 全部完成,~96 测试 PASS。TurnLoop 主路径完整就位,
4 种执行结果(accept / revise / reject 降级 / circuit_open 熔断降级)均有专属处理。
可观测性 TurnTelemetry 落地(Literal-typed guard_decision)。
Phase C 可基于此引入 References 完整组装 + Curator 真实沉淀。

## 完成的 Task

| Task | 内容 | 主 commit | Cleanup commit |
|------|------|----------|----------------|
| 1 | Phase A 4 risks 清理 | `bad2a8e` | `112a031`(regex 抽 _validators / fullmatch) |
| 2 | Prompt prose 通用化 + game 注入 | `28ccce3` | `a38c880`(DEFAULT verbatim 测试) |
| 3 | LLMGateway circuit breaker | `786be9c` | — |
| 4 | TurnLoop accept happy path | `f6bfb6a` | `d66d618`(unused imports) |
| 5 | Guard revise + reject 分支 | `22e2505` | `73030a6`(assert→RuntimeError + docstrings) |
| 6 | 熔断降级 + TurnTelemetry | `ff47443` | `cfb6c5c`(Literal + 测试 + docstrings) |
| 7 | 收尾(ruff + tag + 报告) | `<本 commit>` | — |

## 新增文件

- `src/core/_validators.py`(Task 1 cleanup)
- `src/core/turn_loop.py`(Task 4-6)
- `tests/test_turn_loop.py`(Task 4-6)

## 修改的文件

- `src/core/schemas.py`(Task 1:删 TurnResult)
- `src/core/turn_store.py`(Task 1:加 TurnResult / 用 _validators)
- `src/core/llm_gateway.py`(Task 3:circuit breaker)
- `src/core/agents/guard.py`(Task 1-2:pattern + DEFAULT_GUARD_INSTRUCTION 通用化 + instruction override)
- `src/core/agents/narrative.py`(Task 1-2:extra Any + DEFAULT_NARRATIVE_INSTRUCTION 通用化 + instruction override)
- `src/core/world_memory.py`(Task 1:pattern)
- 对应测试文件多处扩展

## TurnLoop 4 个执行结果矩阵

| Guard 决策 / Gateway 状态 | Turn.status | response_text | guard_retries | turn_index 前进 | 写 metadata |
|----|----|----|----|----|----|
| accept | ok | proposal.narration | 0 | 是 | telemetry |
| revise | ok | revised_payload.narration | 1 | 是 | telemetry |
| reject | degraded | config.degradation_text | 0 | 否 | telemetry + guard_rejection |
| GatewayCircuitOpen(Narrate) | failed | config.degradation_text | 0 | 否 | telemetry + circuit_open(narrative_draft=None) |
| GatewayCircuitOpen(Guard) | failed | config.degradation_text | 0 | 否 | telemetry + circuit_open(narrative_draft=partial proposal) |

## TurnTelemetry 字段(spec §7.F 已实现部分)

- retrieval_hit_count
- retrieval_top_score
- guard_decision(Literal["accept", "revise", "reject", "circuit_open"])
- guard_findings_count
- guard_retries
- llm_call_count(Narrate + Guard 累计)
- duration_ms(time.monotonic_ns 测量)

**未实现**(Phase C/D):new_facts_kept / new_facts_dropped(需 Curator)/ total_tokens(需 gateway usage 透传)。

## 测试覆盖

- Phase B 新增测试:~15-18 个(Task 1 +8 / Task 2 +4 / Task 3 +4 / Task 4 +3 / Task 5 +3 / Task 6 +2-3 / Task 6 cleanup +1)
- 总测试数(忽略 baseline collection error):**96 passed + 1 skipped**
- `src/core/turn_loop.py` 覆盖率:`98%`
- 全 `src/core/` 覆盖率:`93%`

## 已知遗留 / 留给 Phase C 的事项

1. **`_build_references` 简化版** — 只把 retrieved_memory 转 ReferenceItem,没拼"最近 3 轮 turn 摘要"。Phase C 实现完整 spec §7.B 顺序(rules > world_law > recent_turns > characters > events)。
2. **Curator 完全没沉淀** — `curated_records=[]` hardcoded。Phase D 由 game-specific `MemoryCurator` 替代(spec §7.C 四道闸)。
3. **Guard prompt 模板仍 generic** — Phase D 时 game/text_adventure 应通过 `ConsistencyGuard(instruction=...)` 注入 game-specific guard prompt(spec §7.B)。
4. **WorldMemory.find_similar 阈值 0.92 用 InMemoryRAG 的 TF cosine** — 不是真 embedding。Phase D 上 Chroma + 真 embedding 时,阈值要重新校准。
5. **LLMGateway code review minor 留作 follow-up**(Phase B Task 3 review 提出):
   - monotonic clock(替代 datetime.now 为 wall clock)
   - `complete()` 末尾"unreachable"路径的 error message
   - failure_threshold docstring 说明它计 logical complete() 调用而非 HTTP retry

## 下一步:Phase C 写 plan

Phase C 主要内容(spec §9 + final reviewer 建议):
- 完整 `_build_references` 实施(spec §7.B 顺序,含 recent_turns 摘要)
- 完整集成测试(spec §8.C 覆盖剩余 6 用例,如果有的话)
- TurnLoop 集成测试加 5 项一致性失败分类(spec §7.A 6 类)
- `list_sessions` / `_resume` 续接能力(Phase D `--resume <id>` 需要)
- 准备 Phase D text_adventure 接入的 contract 文档
- LLMGateway monotonic clock 重构(Task 3 review minor)
