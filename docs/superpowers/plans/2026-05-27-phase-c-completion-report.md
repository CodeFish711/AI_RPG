# Phase C 完成报告

日期:2026-05-27(完成日)
关联 plan:[2026-05-27-phase-c-references-and-extensibility.md](2026-05-27-phase-c-references-and-extensibility.md)
关联 spec:[2026-05-26-turn-loop-engine-redesign-design.md](../specs/2026-05-26-turn-loop-engine-redesign-design.md)
关联 contract:[extending-the-engine.md](../specs/extending-the-engine.md)
分支:`codex/world-init-live-smoke`
里程碑 tag:`phase-c-complete`

## 概览

Phase C 6 个 task 全部完成,~109 测试 PASS。TurnLoop references 升级到 spec
§7.B 完整顺序(world_law > recent_turns > characters > events),含 recent_turns
摘要。TurnStore 加 list_sessions() 支持 --resume。LLMGateway 重构到 monotonic
clock(技术债清理)。5 类一致性失败有集成测试覆盖。Phase D contract 文档落地,
text_adventure 实施可直接照搬。**Phase D 准备完毕**。

## 完成的 Task

| Task | 内容 | 主要 commit | Cleanup commit |
|------|------|------------|----------------|
| 1 | LLMGateway monotonic clock 重构 | `285c208` | — |
| 2 | TurnStore.list_sessions() | `05e682b` | — |
| 3 | _build_references 完整(spec §7.B 顺序 + recent_turns) | `956f5f9` | `832254d`(修 `[-0:]` 切片 bug) |
| 4 | 集成测试 spec §7.A 5 类一致性失败 | `99bfe1c` | `26dbec1`(module docstring + 中文 tokenize 说明) |
| 5 | Phase D contract 文档 extending-the-engine.md | `dc8a099` | — |
| 6 | 收尾(ruff + tag + 报告) | `<本 commit>` | — |

## 新增文件

- `tests/test_turn_loop_integration.py`(5 类一致性失败集成测试)
- `docs/superpowers/specs/extending-the-engine.md`(Phase D 5 个契约 + mini example)

## 修改的文件

- `src/core/llm_gateway.py`(monotonic clock)
- `src/core/turn_store.py`(加 list_sessions)
- `src/core/turn_loop.py`(_build_references 完整 + references_priority_kinds config + recent_turns_count=0 守护)
- 对应测试

## 与 Phase B 完成报告"留 Phase C"清单对照

| Phase B 遗留 | Phase C 处理状态 |
|------|---------|
| `_build_references` 简化版 | ✅ Task 3 完整实施 |
| Curator 完全没沉淀 | ⚠ 留 Phase D(contract 文档已给 wrapper 集成方案) |
| Guard prompt 仍 generic | ⚠ 留 Phase D(text_adventure 通过 instruction override 注入) |
| WorldMemory.find_similar 阈值校准 | ⚠ 留 Phase D / E(切 ChromaRAG 时校准) |
| LLMGateway monotonic clock | ✅ Task 1 完成 |

## 关键 Cross-Phase 信号(Phase D 必看)

### ⚠ 中文 tokenize 缺陷不会随 RAG backend 切换自动解决

Phase C Task 4 review 时发现:`ChromaRAGRepository.hashed_text_embedding()` 内部也调
`rag_repository._terms()`(`re.findall(r"[\w]+", text.lower())`),把连续中文当成单
token。Phase D 切到 ChromaRAG **不会自动修这个问题**。详见 extending-the-engine.md
顶部 ⚠ 章节。

**对 Phase D 的影响**:
- Curator 沉淀 memory 时,自己负责加空格分词(或用 jieba)
- query 同理
- 彻底解法:换 multilingual embedding model(BGE / sentence-transformers MiniLM-multilingual)
  或引入 jieba,Phase D 视 demo 质量决定是否提前

### plan 设计要复盘的事(给后续 Phase plan 用)

Phase C Task 4 review 时 implementer 跑测试发现 plan 设计 2 个缺陷:
- 中文 stored memory 没考虑 InMemoryRAG tokenize 限制(我 plan 写的 fixture 测试不
  跑通)
- Test 3 断言用 `"黄铜钥匙"` 同时在 narration 出现,假阳性(plan-level 风险)

**经验**:**写测试时刻意选只在某一处出现的 substring 做断言**,确保测试真正验证目标
路径,而非被 surface payload 假阳性满足。Phase D plan 时引以为戒。

## 测试覆盖

- Phase C 新增测试:~12-13 个(Task 1 无新 / Task 2 +4 / Task 3 +3 cleanup +1 / Task 4 +5)
- 总测试数(忽略 baseline collection error):**109 passed, 1 skipped**
- `src/core/turn_loop.py` 覆盖率:**98%**
- 全 `src/core/` 覆盖率:**94%**

## 已知遗留(留给 Phase D)

1. **MemoryCurator wrapper 接入**:contract 文档已给 wrapper 方案,Phase D 实施后决定是否提升为 core API
2. **WorldMemory.find_similar 阈值校准**:换真实 embedding model 时一并校准
3. **中文 tokenize 缺陷的彻底解法**:换 multilingual embedding 或加 jieba 分词,留 Phase D 视质量决定提前
4. **LLMGateway code review minor**(Phase B Task 3 review 余项,未在 Phase C 修):
   - `complete()` 末尾"unreachable"路径 error message
   - `failure_threshold` docstring 说明它计 logical complete() 调用而非 HTTP retry
5. **Phase E**:world_init/ 现仍在 core/agents/debate.py,物理移动到 game/world_init/

## 下一步:Phase D 写 plan

Phase D 主要内容(参 extending-the-engine.md + spec §9):
- `game/text_adventure/` 全套(5 个契约逐项落地)
  - schemas.py(NarrativeBeat + MemoryKind)
  - narrative_agent.py(instruction 注入)
  - memory_curator.py(spec §7.C 四道闸 + 中文分词预处理)
  - guard_rules.py(game-specific 硬性规则)
  - app.py(CLI + --resume,list_sessions 已就位可直接用)
- TurnLoop wrapper 接 Curator(contract 文档给的方案)
- 5-10 个 game-specific 测试 + 5 类一致性失败的 game 实例化
- 一次手动 live smoke(MIMO_API_KEY 跑通 1 轮真实 LLM)
- MVP 验收清单初步达成(spec §8.F)
