# Phase D: text_adventure game 域 demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 `game/text_adventure/` 的 5 个契约(NarrativeBeat schema / MemoryKind / Prompts / Curator / CLI),用 TurnLoop wrapper 集成 Curator,跑通 10 轮对话 demo,完成 spec §8.F MVP 验收(若 `MIMO_API_KEY` 可用,跑一次 live smoke)。

**Architecture:** game/text_adventure/ 完全照 extending-the-engine.md 5 个契约落地。不动 core/,只通过 `instruction` 注入 / `references_priority_kinds` config / Curator wrapper 三种方式扩展 core 行为。中文分词用 `jieba`(game 域依赖,core 仍 game-agnostic),解决 Phase C Task 4 发现的 RAG tokenize 缺陷。

**Tech Stack:** Python 3.11+,Pydantic 2.7+,pytest + pytest-asyncio,**新增 `jieba>=0.42`**(game 域中文分词)。

**Spec 引用:** [docs/superpowers/specs/2026-05-26-turn-loop-engine-redesign-design.md](../specs/2026-05-26-turn-loop-engine-redesign-design.md) §5.5, §7.A, §7.C, §8.F, §9 Phase D。

**Contract 文档:** [extending-the-engine.md](../specs/extending-the-engine.md) — Phase D 实施直接照此 5 个契约落地。

**Phase C 完成报告:** [2026-05-27-phase-c-completion-report.md](2026-05-27-phase-c-completion-report.md)。

---

## File Structure

| 文件 | 类型 | 职责 |
|------|------|------|
| `pyproject.toml` | 修改 | 加 `jieba>=0.42` 到 dependencies |
| `src/game/__init__.py` | 新建 | 空(package 标记) |
| `src/game/text_adventure/__init__.py` | 新建 | 空 |
| `src/game/text_adventure/schemas.py` | 新建 | `TextAdventureMemoryKind` Enum + `NewFact` + `NarrativeBeat` |
| `src/game/text_adventure/tokenize.py` | 新建 | `tokenize_chinese(text: str) -> str` 用 jieba 分词,英文不动 |
| `src/game/text_adventure/prompts.py` | 新建 | `NARRATIVE_INSTRUCTION` / `GUARD_INSTRUCTION` 常量 + `format_narrative_prompt` helper |
| `src/game/text_adventure/guard_rules.py` | 新建 | `TEXT_ADVENTURE_GUARD_RULES: list[str]` 硬性规则列表 |
| `src/game/text_adventure/narrative_agent.py` | 新建 | `build_narrative_agent(*, runtime) -> NarrativeAgent` 与 `build_guard(*, runtime) -> ConsistencyGuard` 工厂 |
| `src/game/text_adventure/memory_curator.py` | 新建 | `TextAdventureCurator` 四道闸 + 中文分词预处理 |
| `src/game/text_adventure/loop_wrapper.py` | 新建 | `run_turn_with_curator(*, loop, curator, ...)` 包装 TurnLoop.run_turn |
| `src/game/text_adventure/app.py` | 新建 | CLI 入口(`python -m game.text_adventure.app`)+ `--resume` / `--session` / `/quit` |
| `tests/game/__init__.py` | 新建 | 空 |
| `tests/game/test_text_adventure_schemas.py` | 新建 | Schemas 边界值测试 |
| `tests/game/test_text_adventure_tokenize.py` | 新建 | jieba 分词 + 英文保留测试 |
| `tests/game/test_text_adventure_prompts.py` | 新建 | Prompt 常量锁定 + format helper 测试 |
| `tests/game/test_text_adventure_curator.py` | 新建 | 四道闸单元测试 + 中文分词预处理 |
| `tests/game/test_text_adventure_loop_wrapper.py` | 新建 | wrapper 集成测试(accept/reject 时 curate 行为) |
| `tests/game/test_text_adventure_app.py` | 新建 | CLI 烟雾测试(mock LLM) |
| `tests/game/test_text_adventure_live_smoke.py` | 新建 | live LLM smoke(opt-in,`pytest -m live`) |
| `pyproject.toml` | 修改 | 加 `markers = ["live: requires MIMO_API_KEY"]`(若未加) |
| `src/main.py` | 修改 | 改为 `text_adventure.app` 的薄入口(原 world_init MVP 入口 Phase E 处理) |

**Phase D 不涉及**:Phase E(world_init/ 物理移动 / debate.py 搬家 / baseline test_world_init_prompts.py 修复)。

---

## Pre-Task: 环境核对 + 安装 jieba

- [ ] **Step 1: 确认 Phase C 基线**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && pwd && git tag | grep phase && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q 2>&1 | tail -3
```

Expected: `phase-a-complete` + `phase-b-complete` + `phase-c-complete` 都在 + 109 passed + 1 skipped。

- [ ] **Step 2: 安装 jieba(后面 Task 1 才真用,但提前装可让所有测试一次跑通)**

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pip install "jieba>=0.42" 2>&1 | tail -3
```

Expected: 安装成功(若已装:`Requirement already satisfied`)。

- [ ] **Step 3: 加 jieba 到 pyproject.toml dependencies**

打开 `pyproject.toml`,在 `dependencies = [...]` 中加 `"jieba>=0.42,<1.0",`。同时确保 `[tool.pytest.ini_options]` 含:
```
markers = ["live: requires MIMO_API_KEY (opt-in)"]
```
(若已有跳过;若没有 markers 项,加上)

---

## Task 1: schemas + tokenize

**Files:**
- Create: `src/game/__init__.py`(空)
- Create: `src/game/text_adventure/__init__.py`(空)
- Create: `src/game/text_adventure/schemas.py`
- Create: `src/game/text_adventure/tokenize.py`
- Create: `tests/game/__init__.py`(空)
- Create: `tests/game/test_text_adventure_schemas.py`
- Create: `tests/game/test_text_adventure_tokenize.py`

### Step 1: 创建 package __init__ 空文件

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && \
  mkdir -p src/game/text_adventure tests/game && \
  touch src/game/__init__.py src/game/text_adventure/__init__.py tests/game/__init__.py
```

### Step 2: 写 schemas 失败测试

Create `tests/game/test_text_adventure_schemas.py`:

```python
import pytest
from pydantic import ValidationError


def test_text_adventure_memory_kind_has_expected_values():
    from game.text_adventure.schemas import TextAdventureMemoryKind

    expected = {"world_law", "location", "character", "event", "player_state", "relation"}
    actual = {k.value for k in TextAdventureMemoryKind}
    assert actual == expected


def test_new_fact_requires_non_empty_statement():
    from game.text_adventure.schemas import NewFact, TextAdventureMemoryKind

    NewFact(kind=TextAdventureMemoryKind.EVENT, statement="something happened", confidence=0.9)
    with pytest.raises(ValidationError):
        NewFact(kind=TextAdventureMemoryKind.EVENT, statement="", confidence=0.9)


def test_new_fact_confidence_in_range():
    from game.text_adventure.schemas import NewFact, TextAdventureMemoryKind

    NewFact(kind=TextAdventureMemoryKind.EVENT, statement="x", confidence=0.0)
    NewFact(kind=TextAdventureMemoryKind.EVENT, statement="x", confidence=1.0)
    with pytest.raises(ValidationError):
        NewFact(kind=TextAdventureMemoryKind.EVENT, statement="x", confidence=1.5)
    with pytest.raises(ValidationError):
        NewFact(kind=TextAdventureMemoryKind.EVENT, statement="x", confidence=-0.1)


def test_narrative_beat_requires_non_empty_narration():
    from game.text_adventure.schemas import NarrativeBeat

    NarrativeBeat(narration="hello")
    with pytest.raises(ValidationError):
        NarrativeBeat(narration="")


def test_narrative_beat_defaults_lists_to_empty():
    from game.text_adventure.schemas import NarrativeBeat

    beat = NarrativeBeat(narration="x")
    assert beat.new_facts == []
    assert beat.follow_up_hooks == []


def test_narrative_beat_round_trip_with_new_facts():
    from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind

    original = NarrativeBeat(
        narration="你站在森林。",
        new_facts=[
            NewFact(kind=TextAdventureMemoryKind.LOCATION, statement="森林深处", confidence=0.9),
        ],
        follow_up_hooks=["远处有狼嚎"],
    )
    restored = NarrativeBeat.model_validate_json(original.model_dump_json())
    assert restored.narration == "你站在森林。"
    assert len(restored.new_facts) == 1
    assert restored.new_facts[0].kind == TextAdventureMemoryKind.LOCATION
```

### Step 3: 跑测试,确认 fail

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_schemas.py -v
```

Expected: 6 FAIL with `No module named 'game.text_adventure.schemas'`。

### Step 4: 实现 schemas.py

Create `src/game/text_adventure/schemas.py`:

```python
"""text_adventure game 域 schemas — 契约 1+2(NarrativeBeat / MemoryKind)。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TextAdventureMemoryKind(str, Enum):
    """game 域定义的合法 memory kind。core/ 用 kind: str 不限制具体值,
    但 game 内部用这个 Enum 保证一致。"""

    WORLD_LAW = "world_law"
    LOCATION = "location"
    CHARACTER = "character"
    EVENT = "event"
    PLAYER_STATE = "player_state"
    RELATION = "relation"


class NewFact(BaseModel):
    """NarrativeAgent 在 NarrativeBeat 中提名的新事实,Curator 决定是否入 WorldMemory。"""

    kind: TextAdventureMemoryKind
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class NarrativeBeat(BaseModel):
    """NarrativeAgent.run 的 output_schema。response_text_field 指向 narration。"""

    narration: str = Field(min_length=1)       # 给玩家看的散文段
    new_facts: list[NewFact] = Field(default_factory=list)
    follow_up_hooks: list[str] = Field(default_factory=list)  # 留给后续 turn 的钩子
```

### Step 5: 跑测试,确认 PASS

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_schemas.py -v
```

Expected: 6 PASS。

### Step 6: 写 tokenize 失败测试

Create `tests/game/test_text_adventure_tokenize.py`:

```python
def test_tokenize_chinese_splits_continuous_chinese_with_spaces():
    """连续中文短语被 jieba 分词,各词之间加空格。"""
    from game.text_adventure.tokenize import tokenize_chinese

    result = tokenize_chinese("魔法需要血液代价")
    # jieba 应该拆出 "魔法 / 需要 / 血液 / 代价" 或类似(具体分词可能小变,只验证有空格)
    assert " " in result, f"分词后应含空格: {result!r}"
    # 原 token "魔法" / "需要" / "血液" / "代价" 应都能在结果中找到
    assert "魔法" in result
    assert "代价" in result


def test_tokenize_english_unchanged():
    """纯英文短语不变(英文自带空格分词)。"""
    from game.text_adventure.tokenize import tokenize_chinese

    text = "magic requires blood as cost"
    result = tokenize_chinese(text)
    assert result == text


def test_tokenize_mixed_chinese_english():
    """中英混合:中文部分分词,英文部分不变。"""
    from game.text_adventure.tokenize import tokenize_chinese

    text = "NPC Alice 施放火球术"
    result = tokenize_chinese(text)
    assert "NPC" in result or "Alice" in result  # 英文 token 至少有一个保留
    assert "火球" in result or "施放" in result  # 中文 token 至少一个被识别


def test_tokenize_empty_string():
    from game.text_adventure.tokenize import tokenize_chinese

    assert tokenize_chinese("") == ""


def test_tokenize_only_whitespace():
    from game.text_adventure.tokenize import tokenize_chinese

    # 全空白返回原值或精简后的空白(无害,关键是不抛错)
    result = tokenize_chinese("   ")
    assert isinstance(result, str)
```

### Step 7: 跑测试,确认 fail

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_tokenize.py -v
```

Expected: 5 FAIL with `No module named 'game.text_adventure.tokenize'`。

### Step 8: 实现 tokenize.py

Create `src/game/text_adventure/tokenize.py`:

```python
"""中文分词 helper — 解决 Phase C Task 4 review 发现的 RAG tokenize 缺陷。

`src/core/rag_repository.py` 的 _terms() 用 `re.findall(r"[\\w]+", text.lower())`,
把连续中文当成单 token。query 与 stored content 加空格分词后才能 token overlap,
RAG 召回才能工作。

ChromaRAGRepository.hashed_text_embedding() 内部也调 _terms() — 同样缺陷,
Phase D 切到 Chroma 不会自动解决。本 helper 适用所有 RAG backend。
"""

from __future__ import annotations

import jieba


def tokenize_chinese(text: str) -> str:
    """对文本做中文分词,英文不动。返回各 token 用空格分隔的字符串。

    示例:
        "魔法需要血液代价" → "魔法 需要 血液 代价"
        "magic requires blood" → "magic requires blood"(英文不变)
        "NPC Alice 施放火球术" → "NPC   Alice   施放 火球 术"(粗略,jieba 自然分词)
    """
    if not text:
        return text
    tokens = jieba.cut(text, cut_all=False)
    return " ".join(tokens)
```

### Step 9: 跑测试,确认 PASS

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_tokenize.py -v
```

Expected: 5 PASS。jieba 首次加载会打印 building prefix dict 日志,无关测试结果。

### Step 10: 跑全套测试

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: 120 passed (109 prior + 11 new),1 skipped。

### Step 11: import-graph 仍 PASS

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_import_graph.py -v
```

Expected: 2 PASS。新建的 `src/game/text_adventure/*.py` 不影响 import-graph(它只扫 `src/core/`)。

### Step 12: Commit

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add pyproject.toml src/game/ tests/game/
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-d: task 1 — text_adventure schemas + tokenize helper

contract 1+2(NarrativeBeat / MemoryKind):
- TextAdventureMemoryKind Enum:world_law / location / character / event /
  player_state / relation
- NewFact:kind + statement(min_length=1)+ confidence ∈ [0,1]
- NarrativeBeat:narration(min_length=1)+ new_facts + follow_up_hooks

中文分词 workaround:
- tokenize_chinese(text) 用 jieba 做中文分词,英文不变
- 解决 RAG tokenize 缺陷(InMemoryRAG / ChromaRAG 都用 _terms() 把连续
  中文当单 token,空格 query 无 overlap)
- 加 jieba>=0.42 到 pyproject dependencies

11 个新测试覆盖:Enum 值 / NewFact 边界 / NarrativeBeat 默认 / 中英混合分词。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: prompts + guard_rules

**Files:**
- Create: `src/game/text_adventure/prompts.py`
- Create: `src/game/text_adventure/guard_rules.py`
- Create: `tests/game/test_text_adventure_prompts.py`

### Step 1: 写 prompts 失败测试

Create `tests/game/test_text_adventure_prompts.py`:

```python
def test_narrative_instruction_mentions_narrative_beat_schema():
    from game.text_adventure.prompts import NARRATIVE_INSTRUCTION

    assert "NarrativeBeat" in NARRATIVE_INSTRUCTION
    assert "narration" in NARRATIVE_INSTRUCTION


def test_narrative_instruction_specifies_style_rules():
    from game.text_adventure.prompts import NARRATIVE_INSTRUCTION

    # 必须有"字数"或"长度"约束
    assert "字" in NARRATIVE_INSTRUCTION or "long" in NARRATIVE_INSTRUCTION.lower()


def test_guard_instruction_mentions_three_decisions():
    from game.text_adventure.prompts import GUARD_INSTRUCTION

    assert "accept" in GUARD_INSTRUCTION
    assert "revise" in GUARD_INSTRUCTION
    assert "reject" in GUARD_INSTRUCTION


def test_guard_instruction_mentions_revised_payload_requirement():
    from game.text_adventure.prompts import GUARD_INSTRUCTION

    assert "revised_payload" in GUARD_INSTRUCTION


def test_guard_rules_is_non_empty_list_of_strings():
    from game.text_adventure.guard_rules import TEXT_ADVENTURE_GUARD_RULES

    assert isinstance(TEXT_ADVENTURE_GUARD_RULES, list)
    assert len(TEXT_ADVENTURE_GUARD_RULES) >= 3
    assert all(isinstance(r, str) and r for r in TEXT_ADVENTURE_GUARD_RULES)


def test_guard_rules_contains_dead_character_rule():
    from game.text_adventure.guard_rules import TEXT_ADVENTURE_GUARD_RULES

    # 至少有一条规则提到"死"或"dead"
    has_dead_rule = any("死" in r or "dead" in r.lower() for r in TEXT_ADVENTURE_GUARD_RULES)
    assert has_dead_rule
```

### Step 2: 跑测试,确认 fail

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_prompts.py -v
```

Expected: 6 FAIL with `No module named 'game.text_adventure.prompts'` / `.guard_rules`。

### Step 3: 实现 prompts.py

Create `src/game/text_adventure/prompts.py`:

```python
"""text_adventure prompts — 契约 3(NarrativePromptBuilder)。

通过 ConsistencyGuard / NarrativeAgent 的 instruction override 注入。
Phase D 初版,根据 live smoke + 玩家测试调整。
"""


NARRATIVE_INSTRUCTION = """\
你是文字冒险游戏的叙事 agent。基于玩家本轮输入与检索到的相关记忆,
生成符合 NarrativeBeat schema 的下一段叙事 JSON。

【风格】
- 简洁直接,每段叙事 narration 字段 ≤ 200 字
- 第二人称("你看到 / 你听到")
- 不替玩家做决定,让玩家选下一步行动
- 不剧透长远剧情

【输出】
- narration:给玩家看的散文段,必填,非空
- new_facts:本轮叙事引入的新事实,每条带 kind / statement / confidence
  - kind:world_law / location / character / event / player_state / relation
  - confidence:你对该事实"应该长期记忆"的把握度(0-1)
  - 不确定的事实(< 0.5)不要列
- follow_up_hooks:留给后续 turn 的伏笔(可选,字符串列表)

【一致性原则】
- 严格尊重 references 中的 world_law / character / event:不要凭空免除代价、
  让已死角色出场、忽略玩家既有状态
- 若 references 中含 recent_turn 摘要,新叙事必须与上轮位置 / 角色情绪连贯
"""


GUARD_INSTRUCTION = """\
你是文字冒险游戏的一致性裁决 agent。
根据"参考材料 / 硬性规则"判定"提案"是否合规,返回 GuardDecision JSON。

【三档决策】
- accept = 提案与参考一致,放行
- revise = 提案存在可修复的小矛盾(NPC 名字拼错 / 数字略偏 / 措辞不当),
  必须给出 revised_payload(修订后完整提案,严格符合 NarrativeBeat schema)
- reject = 提案存在不可修复矛盾(违反 world_law / 复活死人 / 凭空物品 /
  跳跃场景 / 状态遗忘)

【判定要点】
- 先看硬性规则(rules):任一明示违反 → reject
- 再比对 world_law / character / event references:实质冲突 → reject
- recent_turn 摘要:位置/状态突变无叙事衔接 → reject
- 小瑕疵(NPC 名字、数字、措辞):revise + 给修订版

【输出】
- decision:"accept" / "revise" / "reject"
- findings:违反项列表,每项含 severity / message
- revised_payload:仅 revise 时必填,内容必须符合 NarrativeBeat schema
"""
```

### Step 4: 实现 guard_rules.py

Create `src/game/text_adventure/guard_rules.py`:

```python
"""text_adventure 硬性规则 — Guard 看到的"绝对不能做的事"。

Phase D 初版,根据 live smoke 调整。
"""


TEXT_ADVENTURE_GUARD_RULES: list[str] = [
    "不要让已经死亡的角色再次出场或说话",
    "不要让玩家凭空获得物品、能力或属性变化",
    "不要忽略已经记录在 player_state 中的玩家状态(已持有物品 / 已学技能 / 已受伤等)",
    "不要让场景位置跳变,除非 narration 中有明确移动叙事",
    "不要违反 world_law 中已确立的世界法则(如魔法代价、神灵规则)",
]
```

### Step 5: 跑测试,确认 PASS

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_prompts.py -v
```

Expected: 6 PASS。

### Step 6: 跑全套 + Commit

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: 126 passed (120 prior + 6 new),1 skipped。

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/game/text_adventure/prompts.py src/game/text_adventure/guard_rules.py tests/game/test_text_adventure_prompts.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-d: task 2 — text_adventure prompts + guard_rules

contract 3(NarrativePromptBuilder)初版:
- NARRATIVE_INSTRUCTION:风格(第二人称、≤200字)+ NarrativeBeat schema 字段
  说明 + 一致性原则
- GUARD_INSTRUCTION:三档决策 accept/revise/reject + 判定要点 + revised_payload
  schema 要求

guard_rules.py:5 条硬性规则(死人不出场 / 凭空物品 / 状态遗忘 / 场景跳变 /
world_law 违反)

6 个测试锁定 prompt 关键字段。Phase D 初版,Task 7 live smoke 后根据效果调整。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: narrative_agent 工厂

**Files:**
- Create: `src/game/text_adventure/narrative_agent.py`
- Create: `tests/game/test_text_adventure_narrative_agent.py`

### Step 1: 写测试

Create `tests/game/test_text_adventure_narrative_agent.py`:

```python
import pytest


def test_build_narrative_agent_injects_text_adventure_instruction():
    from core.agents.runtime import AgentRuntime
    from core.schemas import LLMRequest
    from game.text_adventure.narrative_agent import build_narrative_agent
    from game.text_adventure.prompts import NARRATIVE_INSTRUCTION

    class _NoOpGateway:
        async def complete_and_parse(self, request: LLMRequest, output_schema):
            raise NotImplementedError

    runtime = AgentRuntime(gateway=_NoOpGateway())
    agent = build_narrative_agent(runtime=runtime)
    assert agent.instruction == NARRATIVE_INSTRUCTION


def test_build_narrative_agent_profile_id_is_text_adventure_narrator():
    from core.agents.runtime import AgentRuntime
    from core.schemas import LLMRequest
    from game.text_adventure.narrative_agent import build_narrative_agent

    class _NoOpGateway:
        async def complete_and_parse(self, request: LLMRequest, output_schema):
            raise NotImplementedError

    runtime = AgentRuntime(gateway=_NoOpGateway())
    agent = build_narrative_agent(runtime=runtime)
    assert agent.profile.id == "text_adventure_narrator"


def test_build_guard_injects_text_adventure_instruction():
    from core.agents.runtime import AgentRuntime
    from core.schemas import LLMRequest
    from game.text_adventure.narrative_agent import build_guard
    from game.text_adventure.prompts import GUARD_INSTRUCTION

    class _NoOpGateway:
        async def complete_and_parse(self, request: LLMRequest, output_schema):
            raise NotImplementedError

    runtime = AgentRuntime(gateway=_NoOpGateway())
    guard = build_guard(runtime=runtime)
    assert guard.instruction == GUARD_INSTRUCTION


def test_build_guard_profile_id_is_text_adventure_guard():
    from core.agents.runtime import AgentRuntime
    from core.schemas import LLMRequest
    from game.text_adventure.narrative_agent import build_guard

    class _NoOpGateway:
        async def complete_and_parse(self, request: LLMRequest, output_schema):
            raise NotImplementedError

    runtime = AgentRuntime(gateway=_NoOpGateway())
    guard = build_guard(runtime=runtime)
    assert guard.profile.id == "text_adventure_guard"
```

### Step 2: 跑测试,确认 fail

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_narrative_agent.py -v
```

Expected: 4 FAIL with `No module named 'game.text_adventure.narrative_agent'`。

### Step 3: 实现 narrative_agent.py

Create `src/game/text_adventure/narrative_agent.py`:

```python
"""text_adventure 工厂 — 契约 3。

构造 NarrativeAgent / ConsistencyGuard 并注入 game-specific instruction。
"""

from __future__ import annotations

from core.agents.guard import ConsistencyGuard
from core.agents.narrative import NarrativeAgent
from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile
from core.schemas import ThinkingPolicy

from game.text_adventure.prompts import GUARD_INSTRUCTION, NARRATIVE_INSTRUCTION


def build_narrative_agent(*, runtime: AgentRuntime) -> NarrativeAgent:
    """构造 text_adventure 的 NarrativeAgent。注入 NARRATIVE_INSTRUCTION。"""
    profile = AgentProfile(
        id="text_adventure_narrator",
        name="TextAdventureNarrator",
        role="叙事 agent",
        objective="生成符合 NarrativeBeat schema 的下一段叙事",
        temperature=0.8,
        max_tokens=2048,
        thinking=ThinkingPolicy(type="enabled"),
    )
    return NarrativeAgent(
        runtime=runtime,
        profile=profile,
        instruction=NARRATIVE_INSTRUCTION,
    )


def build_guard(*, runtime: AgentRuntime) -> ConsistencyGuard:
    """构造 text_adventure 的 ConsistencyGuard。注入 GUARD_INSTRUCTION。"""
    profile = AgentProfile(
        id="text_adventure_guard",
        name="TextAdventureGuard",
        role="一致性裁决 agent",
        objective="判定提案是否合规",
        temperature=0.2,
        max_tokens=2048,
        thinking=ThinkingPolicy(type="enabled"),
    )
    return ConsistencyGuard(
        runtime=runtime,
        profile=profile,
        instruction=GUARD_INSTRUCTION,
    )
```

### Step 4: 跑测试,确认 PASS + 全套

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_narrative_agent.py -v
```

Expected: 4 PASS。

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: 130 passed (126 prior + 4 new), 1 skipped。

### Step 5: Commit

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/game/text_adventure/narrative_agent.py tests/game/test_text_adventure_narrative_agent.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-d: task 3 — text_adventure narrative_agent 工厂

contract 3 实施完毕:
- build_narrative_agent(*, runtime) → NarrativeAgent,注入 NARRATIVE_INSTRUCTION,
  profile id "text_adventure_narrator",thinking=enabled,temp=0.8
- build_guard(*, runtime) → ConsistencyGuard,注入 GUARD_INSTRUCTION,
  profile id "text_adventure_guard",thinking=enabled,temp=0.2

4 个测试锁定:instruction override + profile id 一致。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: MemoryCurator(四道闸)

**Files:**
- Create: `src/game/text_adventure/memory_curator.py`
- Create: `tests/game/test_text_adventure_curator.py`

### Step 1: 写测试

Create `tests/game/test_text_adventure_curator.py`:

```python
import pytest


def _make_curator(tmp_path=None):
    from core.rag_repository import InMemoryRAGRepository
    from core.world_memory import WorldMemory
    from game.text_adventure.memory_curator import TextAdventureCurator

    wm = WorldMemory(repository=InMemoryRAGRepository())
    return TextAdventureCurator(world_memory=wm), wm


def test_curator_drops_facts_below_low_threshold():
    """confidence < 0.5 直接丢弃。"""
    from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind

    curator, wm = _make_curator()
    beat = NarrativeBeat(
        narration="x",
        new_facts=[
            NewFact(kind=TextAdventureMemoryKind.EVENT, statement="低置信", confidence=0.3),
        ],
    )
    records = curator.curate(beat=beat, session_id="s", turn_index=0)
    assert records == []


def test_curator_accepts_high_confidence_facts():
    """confidence >= 0.8 直接入库。"""
    from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind

    curator, wm = _make_curator()
    beat = NarrativeBeat(
        narration="x",
        new_facts=[
            NewFact(kind=TextAdventureMemoryKind.WORLD_LAW, statement="魔法需血液", confidence=0.95),
        ],
    )
    records = curator.curate(beat=beat, session_id="s", turn_index=0)
    assert len(records) == 1
    assert records[0].kind == "world_law"
    assert records[0].confidence == 0.95


def test_curator_dedups_by_similarity():
    """已存在相似 record 时去重(find_similar 命中)。"""
    from core.world_memory import MemoryRecord
    from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind

    curator, wm = _make_curator()
    # 预存一条
    wm.upsert(MemoryRecord(
        kind="world_law", content="魔法 需 血液",
        source="seed", session_id="s",
    ))
    # 新 fact 与已存相似(完全一致 cosine=1.0,远超 default 阈值 0.92)
    beat = NarrativeBeat(
        narration="x",
        new_facts=[
            NewFact(kind=TextAdventureMemoryKind.WORLD_LAW, statement="魔法 需 血液", confidence=0.95),
        ],
    )
    records = curator.curate(beat=beat, session_id="s", turn_index=0)
    assert records == []  # 去重


def test_curator_tokenizes_chinese_before_upserting():
    """statement 含连续中文时,Curator 应该用 tokenize_chinese 预处理后再入库。"""
    from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind

    curator, wm = _make_curator()
    beat = NarrativeBeat(
        narration="x",
        new_facts=[
            NewFact(
                kind=TextAdventureMemoryKind.WORLD_LAW,
                statement="魔法需要血液代价",  # 连续中文,Curator 应分词
                confidence=0.95,
            ),
        ],
    )
    records = curator.curate(beat=beat, session_id="s", turn_index=0)
    assert len(records) == 1
    # 入库内容应已分词(含空格)
    assert " " in records[0].content


def test_curator_records_have_correct_source_label():
    """source = 'turn:{turn_index}'。"""
    from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind

    curator, wm = _make_curator()
    beat = NarrativeBeat(
        narration="x",
        new_facts=[
            NewFact(kind=TextAdventureMemoryKind.EVENT, statement="something", confidence=0.9),
        ],
    )
    records = curator.curate(beat=beat, session_id="s", turn_index=7)
    assert records[0].source == "turn:7"


def test_curator_upserts_after_curate():
    """curate 自己负责把通过 4 道闸的 record 写入 WorldMemory。"""
    from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind
    from core.world_memory import MemoryQuery

    curator, wm = _make_curator()
    beat = NarrativeBeat(
        narration="x",
        new_facts=[
            NewFact(
                kind=TextAdventureMemoryKind.EVENT,
                statement="国王被刺",
                confidence=0.9,
            ),
        ],
    )
    curator.curate(beat=beat, session_id="s", turn_index=0)

    # 验证已入 WorldMemory
    results = wm.query(MemoryQuery(query_text="国王 被 刺", session_id="s", top_k=5))
    assert len(results) >= 1
```

### Step 2: 跑测试,确认 fail

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_curator.py -v
```

Expected: 6 FAIL with `No module named 'game.text_adventure.memory_curator'`。

### Step 3: 实现 memory_curator.py

Create `src/game/text_adventure/memory_curator.py`:

```python
"""text_adventure MemoryCurator — 契约 4。

实施 spec §7.C 四道闸 + 中文分词预处理:
1. Schema 校验(Pydantic 已挡)
2. Confidence 闸:>=0.8 直入,0.5-0.8 入 pending(MVP 简化:丢弃),<0.5 丢弃
3. 去重闸:embedding 相似度 > 0.92 视为重复
4. 冲突闸:MVP 不实现,留 v2

中文分词:`statement` 含连续中文时,用 jieba 分词后再入库,
确保 RAG 检索能命中(参 extending-the-engine.md ⚠ 章节)。
"""

from __future__ import annotations

from core.world_memory import MemoryRecord, WorldMemory

from game.text_adventure.schemas import NarrativeBeat, NewFact
from game.text_adventure.tokenize import tokenize_chinese


_HIGH_CONFIDENCE_THRESHOLD = 0.8
_LOW_CONFIDENCE_THRESHOLD = 0.5
_DEDUP_SIMILARITY_THRESHOLD = 0.92


class TextAdventureCurator:
    """从 NarrativeBeat 提取要进 WorldMemory 的 MemoryRecord。"""

    def __init__(self, *, world_memory: WorldMemory) -> None:
        self.world_memory = world_memory

    def curate(
        self,
        *,
        beat: NarrativeBeat,
        session_id: str,
        turn_index: int,
    ) -> list[MemoryRecord]:
        """对 beat.new_facts 过 4 道闸,过的 fact 转 MemoryRecord 并写入 WorldMemory。
        返回实际入库的 records(供 telemetry / debug)。"""
        accepted: list[MemoryRecord] = []
        for fact in beat.new_facts:
            record = self._curate_fact(fact, session_id=session_id, turn_index=turn_index)
            if record is None:
                continue
            self.world_memory.upsert(record)
            accepted.append(record)
        return accepted

    def _curate_fact(
        self,
        fact: NewFact,
        *,
        session_id: str,
        turn_index: int,
    ) -> MemoryRecord | None:
        # 闸 1:Schema 已由 Pydantic 校验(NewFact 构造时挡了 statement 空 / confidence 越界)

        # 闸 2:Confidence
        if fact.confidence < _LOW_CONFIDENCE_THRESHOLD:
            return None
        if fact.confidence < _HIGH_CONFIDENCE_THRESHOLD:
            # 0.5-0.8 区间:MVP 简化为丢弃。v2 可入 pending,下一轮被引用时正式入库。
            return None

        # 中文分词预处理(在去重检查之前 — 用同样形式比对相似度)
        content = tokenize_chinese(fact.statement)

        # 闸 3:去重
        existing = self.world_memory.find_similar(
            content=content,
            session_id=session_id,
            threshold=_DEDUP_SIMILARITY_THRESHOLD,
        )
        if existing is not None:
            return None

        # 闸 4:冲突(MVP 不实现,直接通过)

        return MemoryRecord(
            kind=fact.kind.value,
            content=content,
            source=f"turn:{turn_index}",
            session_id=session_id,
            confidence=fact.confidence,
        )
```

### Step 4: 跑测试,确认 PASS

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_curator.py -v
```

Expected: 6 PASS。

如有 fail:
- `test_curator_dedups_by_similarity` fail → 检查 fact.statement 与预存 content 是否完全一致(本测试要求 cosine ≥ 0.92)
- `test_curator_tokenizes_chinese_before_upserting` fail → 检查 _curate_fact 是否真调了 tokenize_chinese

### Step 5: 全套 + Commit

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: 136 passed (130 prior + 6 new), 1 skipped。

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/game/text_adventure/memory_curator.py tests/game/test_text_adventure_curator.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-d: task 4 — TextAdventureCurator 四道闸 + 中文分词

contract 4 实施:spec §7.C 四道闸
- 闸 1:Schema(Pydantic 已挡)
- 闸 2:Confidence 三档 — >=0.8 直入,0.5-0.8 MVP 丢弃,<0.5 丢弃
- 闸 3:去重 — WorldMemory.find_similar 阈值 0.92
- 闸 4:冲突 — MVP 不实现,v2 处理

statement 用 tokenize_chinese 预处理后入库,解决 RAG tokenize 缺陷。
curate() 自己负责 upsert 入库,返回实际入库 records(供 telemetry)。

6 个测试覆盖:低置信丢弃 / 高置信入库 / 相似去重 / 中文分词 / source 标签 / upsert 完成。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: TurnLoop wrapper(集成 Curator)

**Files:**
- Create: `src/game/text_adventure/loop_wrapper.py`
- Create: `tests/game/test_text_adventure_loop_wrapper.py`

### Step 1: 写测试

Create `tests/game/test_text_adventure_loop_wrapper.py`:

```python
from pathlib import Path

import pytest

from core.agents.guard import GuardDecision, GuardFinding
from core.agents.runtime import AgentRuntime
from core.rag_repository import InMemoryRAGRepository
from core.turn_loop import TurnLoop, TurnLoopConfig
from core.turn_store import TurnStore
from core.world_memory import MemoryQuery, WorldMemory
from tests._fakes import FakeStructuredGateway

from game.text_adventure.memory_curator import TextAdventureCurator
from game.text_adventure.narrative_agent import build_guard, build_narrative_agent
from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind


def _build_wrapper_components(*, gateway: FakeStructuredGateway, tmp_path: Path):
    runtime = AgentRuntime(gateway=gateway)
    wm = WorldMemory(repository=InMemoryRAGRepository())
    store = TurnStore(data_dir=tmp_path)
    loop = TurnLoop(
        narrative_agent=build_narrative_agent(runtime=runtime),
        guard=build_guard(runtime=runtime),
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=NarrativeBeat,
            response_text_field="narration",
            retrieval_kinds=[k.value for k in TextAdventureMemoryKind],
            references_priority_kinds=[k.value for k in TextAdventureMemoryKind],
            guard_rules=[],
        ),
    )
    curator = TextAdventureCurator(world_memory=wm)
    return loop, curator, wm


@pytest.mark.asyncio
async def test_loop_wrapper_curates_when_status_ok(tmp_path: Path):
    """status=ok 时 Curator 接收 beat,通过的 fact 入 WorldMemory。"""
    from game.text_adventure.loop_wrapper import run_turn_with_curator

    gateway = FakeStructuredGateway()
    gateway.queue_response(
        NarrativeBeat,
        NarrativeBeat(
            narration="你站在森林。",
            new_facts=[
                NewFact(kind=TextAdventureMemoryKind.LOCATION, statement="森林深处", confidence=0.9),
            ],
        ),
    )
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    loop, curator, wm = _build_wrapper_components(gateway=gateway, tmp_path=tmp_path)
    result = await run_turn_with_curator(
        loop=loop, curator=curator, session_id="s_ok", raw_text="环顾",
    )

    assert result.turn.status == "ok"
    # WorldMemory 应已写入 "森林" 相关
    found = wm.query(MemoryQuery(query_text="森林", session_id="s_ok", top_k=5))
    assert len(found) >= 1


@pytest.mark.asyncio
async def test_loop_wrapper_skips_curate_when_status_degraded(tmp_path: Path):
    """status=degraded(Guard reject)时 Curator 不运行,WorldMemory 不被污染。"""
    from game.text_adventure.loop_wrapper import run_turn_with_curator

    gateway = FakeStructuredGateway()
    gateway.queue_response(
        NarrativeBeat,
        NarrativeBeat(
            narration="违反法则。",
            new_facts=[
                NewFact(kind=TextAdventureMemoryKind.WORLD_LAW, statement="violation", confidence=0.95),
            ],
        ),
    )
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(severity="error", message="violates law")],
        ),
    )

    loop, curator, wm = _build_wrapper_components(gateway=gateway, tmp_path=tmp_path)
    result = await run_turn_with_curator(
        loop=loop, curator=curator, session_id="s_deg", raw_text="x",
    )

    assert result.turn.status == "degraded"
    # WorldMemory 应保持空,reject 不沉淀
    found = wm.query(MemoryQuery(query_text="violation", session_id="s_deg", top_k=5))
    assert found == []


@pytest.mark.asyncio
async def test_loop_wrapper_records_curated_count_in_turn_metadata(tmp_path: Path):
    """wrapper 应把 curated 数量记录到 turn.metadata["curated_count"](供 telemetry 补全)。"""
    from game.text_adventure.loop_wrapper import run_turn_with_curator

    gateway = FakeStructuredGateway()
    gateway.queue_response(
        NarrativeBeat,
        NarrativeBeat(
            narration="x",
            new_facts=[
                NewFact(kind=TextAdventureMemoryKind.EVENT, statement="高置信事件", confidence=0.9),
                NewFact(kind=TextAdventureMemoryKind.EVENT, statement="低置信", confidence=0.3),  # 丢弃
            ],
        ),
    )
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))

    loop, curator, wm = _build_wrapper_components(gateway=gateway, tmp_path=tmp_path)
    result = await run_turn_with_curator(
        loop=loop, curator=curator, session_id="s_count", raw_text="x",
    )

    # 注:result.turn 已存盘,metadata 包含 telemetry + curated_count
    assert result.turn.metadata.get("curated_count") == 1  # 只 1 个通过四道闸
```

### Step 2: 跑测试,确认 fail

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_loop_wrapper.py -v
```

Expected: 3 FAIL with `No module named 'game.text_adventure.loop_wrapper'`。

### Step 3: 实现 loop_wrapper.py

Create `src/game/text_adventure/loop_wrapper.py`:

```python
"""TurnLoop + Curator 集成 wrapper — 契约 4 接入 core TurnLoop。

extending-the-engine.md 给出的方案:函数式 wrapper,在 status=ok 时调用 Curator,
status != ok 时跳过 Curator(避免污染 WorldMemory)。
"""

from __future__ import annotations

from core.turn_loop import TurnLoop
from core.turn_store import TurnResult

from game.text_adventure.memory_curator import TextAdventureCurator
from game.text_adventure.schemas import NarrativeBeat


async def run_turn_with_curator(
    *,
    loop: TurnLoop,
    curator: TextAdventureCurator,
    session_id: str,
    raw_text: str,
) -> TurnResult:
    """跑一轮 TurnLoop,accept 时把 NarrativeBeat 交给 Curator 沉淀。

    实现说明:
    - status=ok:NarrativeBeat 通过 Curator,records 入 WorldMemory
    - status=degraded(Guard reject)/failed(circuit_open):跳过 Curator
    - turn.metadata["curated_count"] 记录实际入库 record 数(供 MVP 验收统计)
    """
    result = await loop.run_turn(session_id=session_id, raw_text=raw_text)

    if result.turn.status != "ok" or not result.turn.narrative_draft:
        # 把 0 也写一下,避免下游 .get 时 None
        result.turn.metadata["curated_count"] = 0
        loop.turn_store.save(result.turn)  # 更新存盘
        return result

    beat = NarrativeBeat.model_validate(result.turn.narrative_draft)
    curated = curator.curate(
        beat=beat,
        session_id=session_id,
        turn_index=result.turn.input.turn_index,
    )
    result.turn.metadata["curated_count"] = len(curated)
    # 重新存盘以记录 curated_count(TurnLoop 已经存过一次,这里覆盖最新)
    loop.turn_store.save(result.turn)
    return result
```

**注意**:`loop.turn_store.save(result.turn)` 会**追加**一行到 JSONL(不是覆盖),所以会造成重复条目。这是简化方案的代价。MVP 阶段可接受,Phase E 视情况优化(可以加 `save_or_update` 方法)。

### Step 4: 跑测试,确认 PASS

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_loop_wrapper.py -v
```

Expected: 3 PASS。

如果 `test_loop_wrapper_records_curated_count_in_turn_metadata` 因 turn.metadata 已被 TurnLoop 写过 telemetry 而 curated_count 未出现,需要确认 `result.turn.metadata` 是同一个 dict 对象(Pydantic model 的 dict 字段在 model_dump 后是新 dict,但**实例的字段访问**返回原 dict 引用)。如果实测确实出问题,改为 `result.turn.metadata.update({"curated_count": len(curated)})`。

### Step 5: 全套 + import-graph + Commit

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_import_graph.py -v
```

Expected: 139 passed (136 prior + 3 new), 1 skipped。import-graph 2 PASS。

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/game/text_adventure/loop_wrapper.py tests/game/test_text_adventure_loop_wrapper.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-d: task 5 — TurnLoop + Curator 集成 wrapper

contract 4 接入 core:函数式 wrapper run_turn_with_curator
- status=ok:NarrativeBeat 通过 Curator 四道闸,records 入 WorldMemory
- status=degraded/failed:跳过 Curator,不污染 WorldMemory
- turn.metadata["curated_count"] 记录实际入库 record 数(MVP 验收统计)

简化方案:wrapper 用 turn_store.save() 追加一次以记 curated_count。
JSONL 会有 2 行重复,MVP 可接受;Phase E 视情况优化为 save_or_update。

3 个测试覆盖:accept 时 curate / reject 时不 curate / curated_count 正确。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: CLI app.py(契约 5)

**Files:**
- Create: `src/game/text_adventure/app.py`
- Create: `tests/game/test_text_adventure_app.py`
- Modify: `src/main.py`(改为 text_adventure.app 的薄入口)

### Step 1: 写测试

Create `tests/game/test_text_adventure_app.py`:

```python
import asyncio
from pathlib import Path
from unittest.mock import patch

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

    # 应输出 2 轮 narration(第 3 轮是 /quit,不调 LLM)
    assert "第 1 轮回复" in outputs
    assert "第 2 轮回复" in outputs


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
    assert "real reply" in outputs
    # 空 / 空白输入没产 output
    assert len([o for o in outputs if "reply" in o or "回复" in o]) == 1


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
```

### Step 2: 跑测试,确认 fail

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_app.py -v
```

Expected: 6 FAIL with `No module named 'game.text_adventure.app'`。

### Step 3: 实现 app.py

Create `src/game/text_adventure/app.py`:

```python
"""text_adventure CLI app — 契约 5。

入口:`python -m game.text_adventure.app` 或 `python -m game.text_adventure.app --resume <id>`。
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Callable

from core.agents.runtime import AgentRuntime
from core.config import AppSettings
from core.llm_gateway import LLMGateway
from core.rag_repository import InMemoryRAGRepository
from core.turn_loop import TurnLoop, TurnLoopConfig
from core.turn_store import TurnStore
from core.world_memory import WorldMemory

from game.text_adventure.guard_rules import TEXT_ADVENTURE_GUARD_RULES
from game.text_adventure.loop_wrapper import run_turn_with_curator
from game.text_adventure.memory_curator import TextAdventureCurator
from game.text_adventure.narrative_agent import build_guard, build_narrative_agent
from game.text_adventure.schemas import NarrativeBeat, TextAdventureMemoryKind


def resolve_session(
    *,
    turn_store: TurnStore,
    resume: str | None,
    new_session: str | None,
) -> str:
    """解析 session_id:--resume / --session / default。
    --resume 时校验 id 必须在 list_sessions 中存在。"""
    if resume is not None:
        available = turn_store.list_sessions()
        if resume not in available:
            raise ValueError(
                f"Session not found: {resume!r}. Available: {available[:5]}"
            )
        return resume
    return new_session or "default"


async def run_session(
    *,
    session_id: str,
    data_dir: Path,
    gateway,  # LLMGateway or test gateway
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    """跑一轮交互式 session。input_fn / output_fn 可注入便于测试。"""
    runtime = AgentRuntime(gateway=gateway)
    wm = WorldMemory(repository=InMemoryRAGRepository())
    turn_store = TurnStore(data_dir=data_dir)
    loop = TurnLoop(
        narrative_agent=build_narrative_agent(runtime=runtime),
        guard=build_guard(runtime=runtime),
        world_memory=wm,
        turn_store=turn_store,
        config=TurnLoopConfig(
            narrative_output_schema=NarrativeBeat,
            response_text_field="narration",
            retrieval_kinds=[k.value for k in TextAdventureMemoryKind],
            references_priority_kinds=[
                TextAdventureMemoryKind.WORLD_LAW.value,
                TextAdventureMemoryKind.LOCATION.value,
                TextAdventureMemoryKind.CHARACTER.value,
                TextAdventureMemoryKind.EVENT.value,
                TextAdventureMemoryKind.PLAYER_STATE.value,
            ],
            guard_rules=TEXT_ADVENTURE_GUARD_RULES,
        ),
    )
    curator = TextAdventureCurator(world_memory=wm)

    output_fn(f"=== Session: {session_id} ===")
    output_fn("输入指令(或 /quit 退出):")

    while True:
        try:
            user_input = input_fn("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input == "/quit":
            break
        result = await run_turn_with_curator(
            loop=loop, curator=curator, session_id=session_id, raw_text=user_input,
        )
        output_fn(result.response_text)


def _build_gateway_from_env() -> LLMGateway:
    settings = AppSettings()
    if not settings.mimo_api_key:
        raise SystemExit(
            "MIMO_API_KEY is required. 在 .env.local 设置或 export 后再跑。"
        )
    return LLMGateway(
        api_key=settings.mimo_api_key,
        base_url=settings.mimo_base_url,
        default_model=settings.mimo_model,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="text_adventure")
    parser.add_argument("--session", help="新 session id(默认 'default')")
    parser.add_argument("--resume", help="续接已有 session_id")
    parser.add_argument("--data-dir", default="data/sessions", help="JSONL 存盘目录")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    turn_store = TurnStore(data_dir=data_dir)
    try:
        session_id = resolve_session(
            turn_store=turn_store, resume=args.resume, new_session=args.session,
        )
    except ValueError as exc:
        raise SystemExit(str(exc))

    gateway = _build_gateway_from_env()
    asyncio.run(run_session(
        session_id=session_id, data_dir=data_dir, gateway=gateway,
    ))


if __name__ == "__main__":
    main()
```

### Step 4: 修改 `src/main.py` 为 text_adventure.app 薄入口

读 `src/main.py` 当前内容,完整替换为:

```python
"""主入口 — 转发到 game.text_adventure.app.main()。

原 world_init MVP 入口已 Phase D 退役。world_init 工作流降级为
text_adventure 的可选开局插件,留 Phase E 处理 --with-world-init flag。
"""

from game.text_adventure.app import main


if __name__ == "__main__":
    main()
```

### Step 5: 跑测试,确认 PASS

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/game/test_text_adventure_app.py -v
```

Expected: 6 PASS。

如有 fail:
- `test_app_run_session_processes_inputs_until_quit` fail with StopIteration → `iter([...])` 用完了,可能 LLM 调用多于预期;检查 inputs 列表长度
- `test_app_run_session_handles_empty_input` fail with StopIteration → 同上

### Step 6: 验证现有 main.py / world_init 测试是否被打断

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest --ignore=tests/test_world_init_prompts.py -q
```

Expected: 145 passed (139 prior + 6 new), 1 skipped。

**特别留意**:`tests/test_main_mvp.py` 可能依赖 main.py 的原 world_init 逻辑,会 fail。这是预期 — 该测试需要 Phase E 一并清理(原 world_init MVP 测试已与新主入口语义不符)。**STOP 报告** 若 `test_main_mvp.py` fail,等指示决定改测试还是 add 到 baseline skip 列表。

### Step 7: Commit

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add src/game/text_adventure/app.py src/main.py tests/game/test_text_adventure_app.py
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "$(cat <<'EOF'
phase-d: task 6 — text_adventure CLI app + main.py 薄入口

contract 5 实施:
- run_session(*, session_id, data_dir, gateway, input_fn, output_fn):
  交互式 REPL,空输入忽略 / "/quit" 退出
- resolve_session(*, turn_store, resume, new_session) -> str:
  --resume 时用 list_sessions 校验 id 存在,否则 default
- main():argparse + AppSettings + LLMGateway + asyncio.run(run_session)
- src/main.py 改为转发到 text_adventure.app.main(),原 world_init MVP
  入口已退役(world_init 留 Phase E 作为可选开局插件)

input_fn / output_fn 注入可测试。6 个测试覆盖:多轮处理 / 空输入 /
resume 有效 id / default fallback / --session arg / resume 无效 id 抛错。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Live smoke + Phase D 收尾

**Files:**
- Create: `tests/game/test_text_adventure_live_smoke.py`
- 跑 ruff,跑全套测试,打 tag,写完成报告

### Step 1: 创建 live smoke 测试

Create `tests/game/test_text_adventure_live_smoke.py`:

```python
"""Live LLM smoke test — opt-in,需 MIMO_API_KEY env var。

跑 `pytest -m live` 才会执行。默认 / CI 跑 `pytest -m "not live"` 跳过。

每个 smoke 单次成本约 < $0.01(thinking=disabled / max_tokens 512)。
"""

import os
from pathlib import Path

import pytest

from core.agents.runtime import AgentRuntime
from core.llm_gateway import LLMGateway
from core.rag_repository import InMemoryRAGRepository
from core.schemas import ThinkingPolicy
from core.turn_loop import TurnLoop, TurnLoopConfig
from core.turn_store import TurnStore
from core.world_memory import WorldMemory

from game.text_adventure.loop_wrapper import run_turn_with_curator
from game.text_adventure.memory_curator import TextAdventureCurator
from game.text_adventure.narrative_agent import build_guard, build_narrative_agent
from game.text_adventure.schemas import NarrativeBeat, TextAdventureMemoryKind


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("MIMO_API_KEY"), reason="needs MIMO_API_KEY")
@pytest.mark.asyncio
async def test_live_one_turn_smoke(tmp_path: Path):
    """跑 1 个真实 Turn,验证 NarrativeBeat 能 parse + Guard 有合理决策。
    不验内容质量(那要更多轮)。"""
    gateway = LLMGateway(
        api_key=os.environ["MIMO_API_KEY"],
        # 控制单次成本:thinking 关闭(快速 smoke,非创作)
        default_thinking=ThinkingPolicy(type="disabled"),
    )
    runtime = AgentRuntime(gateway=gateway)
    wm = WorldMemory(repository=InMemoryRAGRepository())
    store = TurnStore(data_dir=tmp_path)
    loop = TurnLoop(
        narrative_agent=build_narrative_agent(runtime=runtime),
        guard=build_guard(runtime=runtime),
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=NarrativeBeat,
            response_text_field="narration",
            retrieval_kinds=[k.value for k in TextAdventureMemoryKind],
            references_priority_kinds=[
                TextAdventureMemoryKind.WORLD_LAW.value,
                TextAdventureMemoryKind.LOCATION.value,
                TextAdventureMemoryKind.CHARACTER.value,
                TextAdventureMemoryKind.EVENT.value,
            ],
            guard_rules=[],
        ),
    )
    curator = TextAdventureCurator(world_memory=wm)

    result = await run_turn_with_curator(
        loop=loop, curator=curator, session_id="live_smoke", raw_text="环顾四周,描述我看到什么",
    )

    # 基本不变量:turn 跑通,response_text 非空
    assert result.response_text
    assert result.turn.status in {"ok", "degraded"}  # circuit_open 不接受
    # telemetry 写入
    assert result.turn.metadata.get("telemetry") is not None
```

### Step 2: 跑 ruff + 全套(non-live)+ import-graph

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/ruff check --select F401,F811 --fix src/ tests/ scripts/
```

Expected: All checks passed,或修若干 unused imports。

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest -m "not live" --ignore=tests/test_world_init_prompts.py -q
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest tests/test_import_graph.py -v
```

Expected: 全套 ~145 passed(可能含 test_main_mvp 的 fail,需要处理);import-graph 2 PASS。

### Step 3: 跑覆盖率

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && .venv/bin/pytest -m "not live" --ignore=tests/test_world_init_prompts.py --cov=src/game --cov-report=term-missing -q 2>&1 | tail -20
```

记录 `src/game/text_adventure/` 各模块覆盖率。

### Step 4: 跑 live smoke(若 MIMO_API_KEY 可用)

```bash
cd /Users/fangkai/ai_work/games/AI_RPG && [ -n "$MIMO_API_KEY" ] && .venv/bin/pytest tests/game/test_text_adventure_live_smoke.py -m live -v
```

Expected: 1 PASS(若有 KEY)或 1 SKIPPED(若无 KEY)。

如果 PASS 但 narration 内容有问题(prompt 质量不行 / format 异常),记录到完成报告作为 Phase E 的 prompt 调整事项,不阻塞 Task 7。

### Step 5: 若 ruff 修了或 test_main_mvp 需要处理,Commit

如有 changes:
```bash
git -C /Users/fangkai/ai_work/games/AI_RPG status
git -C /Users/fangkai/ai_work/games/AI_RPG add -A
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "phase-d: task 7 收尾清理"
```

### Step 6: 打 tag

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG tag -a phase-d-complete -m "Phase D: text_adventure demo + 5 契约 + live smoke"
git -C /Users/fangkai/ai_work/games/AI_RPG tag --list | grep phase
```

### Step 7: 写完成报告

Create `/Users/fangkai/ai_work/games/AI_RPG/docs/superpowers/plans/2026-05-27-phase-d-completion-report.md`:

```markdown
# Phase D 完成报告

日期:2026-05-27(完成日)
关联 plan:[2026-05-27-phase-d-text-adventure.md](2026-05-27-phase-d-text-adventure.md)
关联 contract:[extending-the-engine.md](../specs/extending-the-engine.md)
分支:`codex/world-init-live-smoke`
里程碑 tag:`phase-d-complete`

## 概览

Phase D 7 个 task 全部完成,~145+ 测试 PASS。`game/text_adventure/` 5 个契约
落地,TurnLoop wrapper 集成 Curator,CLI app 可跑通(若有 MIMO_API_KEY)。
Phase E 准备就绪 — 只剩 world_init 物理移动 + baseline 测试清理。

## 完成的 Task

| Task | 内容 | 主要 commit |
|------|------|------------|
| 1 | schemas(MemoryKind + NewFact + NarrativeBeat)+ tokenize(jieba) | `<sha>` |
| 2 | prompts.py(NARRATIVE / GUARD INSTRUCTION)+ guard_rules.py | `<sha>` |
| 3 | narrative_agent 工厂(build_narrative_agent / build_guard) | `<sha>` |
| 4 | TextAdventureCurator 四道闸 + 中文分词预处理 | `<sha>` |
| 5 | run_turn_with_curator wrapper | `<sha>` |
| 6 | CLI app.py + main.py 薄入口 | `<sha>` |
| 7 | live smoke + 收尾(ruff + tag + 报告) | `<sha>` |

## 新增文件

- `src/game/__init__.py` / `src/game/text_adventure/__init__.py`
- `src/game/text_adventure/{schemas,tokenize,prompts,guard_rules,narrative_agent,memory_curator,loop_wrapper,app}.py`
- `tests/game/__init__.py` / `tests/game/test_text_adventure_*.py`(7 个测试文件)
- `tests/game/test_text_adventure_live_smoke.py`(opt-in)

## 修改的文件

- `pyproject.toml`(加 jieba dependency + live marker)
- `src/main.py`(改为 text_adventure.app 薄入口)

## 测试结果

- 全套(non-live):`<具体数>` passed, 1 skipped, `<baseline 状态>`
- live smoke:`<状态:PASS / SKIPPED / 未跑>`
- `src/game/text_adventure/` 覆盖率:`<具体数>`

## MVP 验收清单状态(spec §8.F)

**功能性**:
- [ ] `python -m game.text_adventure.app` 可跑通 10 轮玩家自由对话(留 Phase E / 实际玩家测试)
- [ ] 每轮端到端 ≤ 30 秒(留 Phase E 性能测试)
- [ ] session 中途 Ctrl-C 后,`--resume <session_id>` 能续接(框架就位,实际验证留 Phase E)

**一致性**(核心价值主张):
- 5 个 demo / Guard 决策率统计 → 留 Phase E 跑

**工程性**:
- [x] `pytest -m "not live"` 全绿(除 baseline)
- [x] `pytest -m live` 框架就位
- [x] 仓库内无 API key
- [x] JSONL 可被 Turn.model_validate_json 解回
- [x] import-graph 测试通过

**平台性**:
- [x] `core/turn_loop.py` 文件文本不含 `text_adventure` 字样
- [x] world_init 仍存在(Phase E 处理),作为非 text_adventure 的 game 域反例

## 已知遗留 / 留给 Phase E

1. **`tests/test_main_mvp.py` 可能 fail** — 原 world_init MVP 测试与新主入口语义不符。Phase E 处理(删 / 改 / 移到 game/world_init/)
2. **`test_world_init_prompts.py` baseline collection error** — Phase E 修
3. **world_init 物理移动**:`core/agents/debate.py` → `game/world_init/debate.py`
4. **`--with-world-init` flag**:挂载 world_init 工作流作为开局生成器
5. **TurnStore.save 在 wrapper 二次调用导致 JSONL 重复条目** — Phase E 视情况优化为 `save_or_update`
6. **Curator pending 队列(0.5-0.8 confidence)** — MVP 简化为丢弃,v2 实现"下一轮被引用时正式入库"
7. **Live demo 实测**:Phase E 跑 5 个 10 轮 demo 统计 Guard 决策率 + 一致性指标

## 下一步:Phase E plan

Phase E 主要内容:
- world_init/ debate.py 物理移动 + import 更新
- main.py 加 --with-world-init flag,挂载 world_init 工作流为可选开局生成器
- 修 baseline test_world_init_prompts.py / test_main_mvp.py
- 简化 CausalImpactPacket(删 delay_ticks / target_type)
- 跑 5 个完整 demo,统计 spec §8.F 一致性指标
- MVP 验收清单全部 16 项达成
```

### Step 8: Commit 报告 + 重打 tag

```bash
git -C /Users/fangkai/ai_work/games/AI_RPG add docs/superpowers/plans/2026-05-27-phase-d-completion-report.md
git -C /Users/fangkai/ai_work/games/AI_RPG commit -m "phase-d: 完成报告"
git -C /Users/fangkai/ai_work/games/AI_RPG tag -d phase-d-complete
git -C /Users/fangkai/ai_work/games/AI_RPG tag -a phase-d-complete -m "Phase D: text_adventure demo 完成"
git -C /Users/fangkai/ai_work/games/AI_RPG log --oneline -10
git -C /Users/fangkai/ai_work/games/AI_RPG tag --list | grep phase
```

---

## Phase D 自审

**1. Spec coverage:**
- contract 1 (NarrativeBeat) → Task 1 ✓
- contract 2 (MemoryKind) → Task 1 ✓
- contract 3 (NarrativePromptBuilder) → Task 2-3 ✓
- contract 4 (MemoryCurator) → Task 4-5 ✓
- contract 5 (CLI app) → Task 6 ✓
- spec §7.C 四道闸 → Task 4 ✓(冲突闸 MVP 不实现)
- 中文 tokenize workaround → Task 1 (jieba) ✓
- live smoke → Task 7 ✓

**2. Placeholder scan:** 无 TBD / TODO / 模糊步骤。

**3. Type consistency:**
- `NarrativeBeat.narration` 字段名贯穿(Task 1 定义,Task 5 wrapper 用,Task 6 app config 配)
- `TextAdventureMemoryKind.X.value` 用法贯穿(Task 1 / Task 6 app config)
- `run_turn_with_curator` 签名(Task 5 定义,Task 6 / Task 7 用)
- `resolve_session(*, turn_store, resume, new_session) -> str`(Task 6 定义,测试一致)

**4. 跨 Phase 一致性:**
- 严格按 extending-the-engine.md 5 个契约落地
- jieba 是 game 域依赖(不污染 core)
- import-graph 不受影响(`core/` 仍 clean)

---

## Phase D 结束后

Phase D 完成后,**核心功能 demo 全套就位**。Phase E 主要是清理 + world_init 降级 + MVP 验收实际跑 5 个 demo。
