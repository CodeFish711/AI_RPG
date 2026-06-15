# Phase E + MVP 完成报告

日期:2026-05-27(完成日)
关联 plan:[2026-05-27-phase-e-world-init-and-mvp-acceptance.md](2026-05-27-phase-e-world-init-and-mvp-acceptance.md)
关联 spec:[2026-05-26-turn-loop-engine-redesign-design.md](../specs/2026-05-26-turn-loop-engine-redesign-design.md)
分支:`codex/world-init-live-smoke`
里程碑 tags:`phase-e-complete` + `mvp-complete`

## 概览

Phase E 6 个 task 全部完成,完成 spec §4 占位/移动清单的最后一项
(debate.py 移动)+ 3 个 baseline 测试清理 + text_adventure CLI 加
`--with-world-init` flag + CausalImpactPacket 简化(spec §11 决策)+
MVP 验收 script 就位。

**整体 MVP**:Turn Loop Engine 重设计完成 — 5 个 Phase(A→E),
**最终测试数 151 passed(+2 skipped,1 deselected live),src/ 整体覆盖率 92%**,**Phase A→E
总 commit 数 37**。

## Phase E 完成的 Task

| Task | 内容 | 主要 commit |
|------|------|------------|
| 1 | debate.py 物理移动到 game/world_init/ | `901bdf1` |
| 2 | 3 baseline 测试清理 | `836eadb` |
| 3 | text_adventure --with-world-init flag + world_init_bridge | `6092b5f` |
| 4 | CausalImpactPacket 简化 | `c0d7bbc` |
| 5 | MVP 验收 script | `ad90472` |
| 6 | 收尾(ruff + tag + 报告) | `c1fc0f7` |

## 全 Phase A→E 累计成果

| Phase | tag | 主要交付 |
|-------|-----|---------|
| A | `phase-a-complete` | core 底座 + 5 组件骨架(WorldMemory / Guard / Narrative / TurnStore / FakeStructuredGateway)+ import-graph 校验 |
| B | `phase-b-complete` | TurnLoop 主路径 4 执行结果(accept/revise/reject/circuit_open)+ TurnTelemetry + LLMGateway circuit breaker + Phase A 4 risks 清理 + prompt prose 通用化 |
| C | `phase-c-complete` | `_build_references` 完整(spec §7.B)+ TurnStore.list_sessions + monotonic clock + 5 类一致性失败集成测试 + extending-the-engine.md |
| D | `phase-d-complete` | `game/text_adventure/` 5 契约全套 + Curator 四道闸 + CLI app + live smoke 框架 + jieba 中文分词 |
| E | `phase-e-complete` + `mvp-complete` | world_init 降级到 game/ + 3 baseline 测试清理 + --with-world-init flag + CausalImpact 简化 + MVP acceptance script |

## MVP 验收清单(spec §8.F)

**功能性**:
- [x] `python -m game.text_adventure.app` 启动框架就位
- [ ] **跑通 10 轮玩家自由对话**(待 user 跑 acceptance script with MIMO_API_KEY 实测)
- [x] `--with-world-init` flag 实现(可选开局生成器)
- [ ] 每轮 ≤ 30 秒(待 user 跑实测确认)
- [x] `--resume <id>` 续接

**一致性**(核心价值主张 — 留 user 实测填):
- [ ] 5 个 demo × Guard accept 率 ∈ [70%, 90%]
- [ ] revise 率 10-25%
- [ ] reject 率 < 5%
- [ ] 至少 1 个 demo 拦截真实矛盾

**工程性**(全部达成):
- [x] `pytest -m "not live"` 全绿(无 baseline ignore!)
- [x] `pytest -m live` 框架就位
- [x] 仓库内无 API key
- [x] JSONL 可被 `Turn.model_validate_json` 解回
- [x] import-graph 测试通过

**平台性**(全部达成):
- [x] `core/turn_loop.py` 不含游戏域词
- [x] world_init 作为非 text_adventure 的 game/ 域反例(已物理在 game/ 下)
- [x] `extending-the-engine.md` 契约文档完整

## 关键最终数字

- 总测试数:**151 passed**(+2 skipped,1 deselected live)
- `src/` 整体覆盖率:**92%**
- `src/core/` 覆盖率:**93%**
- `src/game/` 覆盖率:**89%**
  - `src/game/text_adventure/`:**82%**(app.py 59% 是 CLI 主交互未自动化测,其余文件 100%)
  - `src/game/world_init/`:**99%**
- Phase A→E 总 commit 数:**37** 个

## 后续工作(MVP 之外)

1. **用户实际跑 MVP acceptance script**(`MIMO_API_KEY=... .venv/bin/python scripts/run_mvp_acceptance.py`),填一致性指标
2. 跑 Phase D 的 live smoke 测试 + 用 CLI 手动跑 1-2 demo 验证整链路
3. 据实测结果调 `prompts.py` 的 `NARRATIVE_INSTRUCTION` / `GUARD_INSTRUCTION`

**v2 待办**(留 future plan):
- MemoryCurator pending 队列(0.5-0.8 confidence 区间)
- 冲突闸(spec §7.C 四道闸的第 4 道)
- LLMGateway code review minor(`failure_threshold` docstring 等)
- `TurnStore.save_or_update`(替换当前 wrapper 二次 save 导致的 JSONL 重复)
- ChromaRAG 真实 embedding(目前 `hashed_text_embedding` 仍受中文 tokenize 限制)
- 第二个 game/ 域(验证 platform 复用性)

## 设计回顾

完整 MVP 印证了 brainstorm 阶段的 3 个核心判断:

1. **平台向 core 设计可成立**:5 个契约的 game 层接入 core 而无需改 core。
   extending-the-engine.md 文档化了契约,Phase D 落地证明可行。
2. **Turn Loop 主路径正确**:accept / revise / reject / circuit_open 四种执行
   结果稳定,Phase B 实施,Phase C-E 完善,无重大重构。
3. **一致性优先的 MVP 价值主张**:references + Guard + Curator 三件套构成
   一致性闸门。Phase C 集成测试覆盖 5 类失败,Phase D Curator 四道闸
   实施完成。

完整文档链(可追溯):
spec(2026-05-26 turn loop engine redesign)
  → Phase A plan + completion report
  → Phase B plan + completion report
  → Phase C plan + completion report + extending-the-engine.md(契约)
  → Phase D plan + completion report
  → Phase E plan + 本完成报告

## 致谢

Co-designed with Claude Opus 4.7 (1M context):
- Brainstorming(2 轮澄清,3 方向 A/B/C,推荐 A)
- Spec(823 行设计文档)
- 5 个 Phase plan(共 ~7000 行)
- Subagent-driven 执行(~35 个 task,每个 implementer + spec reviewer + code quality reviewer 三重审查)
- 跨 task / 跨 Phase final review
