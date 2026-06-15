# Phase D 完成报告

日期:2026-05-27(完成日)
关联 plan:[2026-05-27-phase-d-text-adventure.md](2026-05-27-phase-d-text-adventure.md)
关联 contract:[extending-the-engine.md](../specs/extending-the-engine.md)
分支:`codex/world-init-live-smoke`
里程碑 tag:`phase-d-complete`

## 概览

Phase D 7 个 task 全部完成,~144 测试 PASS(忽略 baseline 3 个 world_init 相关 file)。
`game/text_adventure/` 5 个契约落地,TurnLoop wrapper 集成 Curator,CLI app 可
跑通(若有 MIMO_API_KEY)。live smoke 测试框架就位(opt-in,`pytest -m live`)。
Phase E 准备就绪 — 只剩 world_init 物理移动 + baseline 测试清理 + 5 个 demo 实测。

## 完成的 Task

| Task | 内容 | 主 commit |
|------|------|----------|
| 1 | schemas + tokenize(jieba) | `4639efe` |
| 2 | prompts + guard_rules | `5883f21` |
| 3 | narrative_agent 工厂 | `70e0485` |
| 4 | TextAdventureCurator 四道闸 | `1f5ba8e` |
| 5 | TurnLoop + Curator wrapper | `14907d5` |
| 6 | CLI app + main.py 薄入口 | `f3b4ecf` |
| 7 | live smoke + 收尾 | `ac26e2c` |

## 新增文件

- `src/game/__init__.py` / `src/game/text_adventure/__init__.py`
- `src/game/text_adventure/{schemas,tokenize,prompts,guard_rules,narrative_agent,memory_curator,loop_wrapper,app}.py`
- `tests/game/test_text_adventure_*.py`(7 个测试文件)+ `tests/game/test_text_adventure_live_smoke.py`(opt-in)

## 修改的文件

- `pyproject.toml`(加 jieba>=0.42,<1.0 dependency + live marker)
- `src/main.py`(改为 text_adventure.app 薄入口)

## 测试结果

- 全套(non-live,忽略 3 个 world_init baseline):**144 passed, 1 skipped, 1 deselected**
- live smoke:framework 就位,本 task 不跑(需 MIMO_API_KEY,用户手动 `pytest -m live` 跑)
- `src/game/text_adventure/` 覆盖率:
  - `app.py` 69%(CLI 交互分支留 Phase E demo 实测覆盖)
  - `guard_rules.py` / `loop_wrapper.py` / `memory_curator.py` / `narrative_agent.py` / `prompts.py` / `schemas.py` / `tokenize.py`:**100%**
- `src/game/` 总覆盖:**92%**
- import-graph(`test_core_does_not_import_game` + `test_core_files_do_not_mention_game_domain_terms`):**2/2 PASS**

## 5 契约对照表

| 契约 | 文件 | 完成状态 |
|------|------|---------|
| 1. NarrativeBeat schema | `schemas.py` | ✅ |
| 2. MemoryKind 集合 | `schemas.py`(`TextAdventureMemoryKind`) | ✅ |
| 3. NarrativePromptBuilder | `prompts.py` + `narrative_agent.py` 工厂注入 | ✅ |
| 4. MemoryCurator | `memory_curator.py` 四道闸 + `loop_wrapper.py` 接 TurnLoop | ✅ |
| 5. CLI app entry | `app.py` + `main.py` 薄入口 | ✅ |

## MVP 验收清单状态(spec §8.F)

**功能性**:
- [x] CLI app 可启动(`python -m game.text_adventure.app`),framework 就位
- [ ] 10 轮玩家自由对话(留 Phase E 实测)
- [ ] 每轮端到端 ≤ 30 秒(留 Phase E 实测)
- [x] `--resume <session_id>` framework 就位

**一致性**(核心价值主张):
- 留 Phase E 跑 5 个 demo 实测

**工程性**:
- [x] `pytest -m "not live"` 全绿(忽略 3 个 baseline)
- [x] `pytest -m live` framework 就位(需 KEY)
- [x] 仓库内无 API key
- [x] JSONL 可被 Turn.model_validate_json 解回
- [x] import-graph 测试通过

**平台性**:
- [x] `core/turn_loop.py` 不含 `text_adventure` 字样
- [x] world_init 仍存在(Phase E 处理),作为非 text_adventure 的 game 域反例

## 已知遗留 / 留给 Phase E

1. **tests/test_main_mvp.py / test_live_world_init_script.py / test_world_init_prompts.py** — 3 个 baseline 测试因 world_init MVP 入口退役而 fail at collection。Phase E 决定:保留(改写)/ 移到 game/world_init/ / 删除
2. **scripts/live_world_init.py** — 内部仍 import 旧 main.py 符号。Phase E 一并清理
3. **world_init 物理移动**:`core/agents/debate.py` → `game/world_init/debate.py`,更新 workflow.py import
4. **`--with-world-init` flag**:挂载 world_init 工作流作为开局生成器
5. **TurnStore.save 在 wrapper 二次调用 → JSONL 重复条目** — Phase E 视情况优化为 `save_or_update`
6. **Curator pending 队列(0.5-0.8 confidence)** — MVP 简化为丢弃,v2 实现"下一轮被引用时正式入库"
7. **5 个 10 轮 demo 实测**:Phase E 跑(需 MIMO_API_KEY),统计 Guard 决策率 + 一致性指标

## 下一步:Phase E

Phase E 内容:
- world_init/ debate.py 物理移动
- main.py 加 `--with-world-init` flag
- 修 3 个 baseline 测试(改写 / 移走 / 删除)
- 简化 CausalImpactPacket(删 delay_ticks / target_type)
- 跑 5 个完整 demo,统计 spec §8.F 一致性指标
- MVP 验收清单全部 16 项达成
