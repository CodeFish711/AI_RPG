# Extending the AI_RPG Engine: New Game Domain Contracts

> 适用读者:为 AI_RPG core 引擎写新 game 域 demo 的开发者(包括未来的 Phase D `text_adventure` 自己)。
>
> 关联 spec:[2026-05-26-turn-loop-engine-redesign-design.md](2026-05-26-turn-loop-engine-redesign-design.md)
>
> 关联 Phase 完成报告:[Phase A](../plans/2026-05-26-phase-a-completion-report.md) / [Phase B](../plans/2026-05-27-phase-b-completion-report.md) / [Phase C](../plans/2026-05-27-phase-c-completion-report.md)(Phase C 完成后回填)

## 概览

AI_RPG core 是个 game-agnostic 引擎。任何 game 域只要实现下面 **5 个契约**,就能挂上 core 跑通一个完整的 turn 循环:

1. **NarrativeBeat schema**(Pydantic):game 自定义的叙事输出格式
2. **MemoryKind 集合**(Enum / list[str]):game 自定义的记忆类别
3. **NarrativePromptBuilder**(可选):注入 game-specific narrative prompt
4. **MemoryCurator**(可选):从 NarrativeBeat 提取要进 WorldMemory 的 records
5. **CLI app entry**:`python -m game.<my_game>.app` 跑通对话

core 不需要任何 game-specific 代码,Phase D `text_adventure` 将是第一个证明性实例。

---

## ⚠ 关键已知问题:中文 tokenize 缺陷

**位置**:`src/core/rag_repository.py:196` 的 `_terms()` 用 `re.findall(r"[\w]+", text.lower())` 做 tokenize。

**症状**:
- 连续中文短语(如 `"魔法需血液代价"`)被识别为**单一 token**
- 空格分词的 query(如 `"魔法 需 血液 代价"`)与上面的 stored content **无 token overlap**
- `InMemoryRAGRepository.hybrid_search` 计算 cosine score = 0,该 record 被过滤
- `ChromaRAGRepository.hashed_text_embedding()` **内部也调 `_terms()`** — 同样缺陷,Phase D 切到 Chroma **不会自动解决**

**Phase C 集成测试的 workaround**:`tests/test_turn_loop_integration.py` 中所有中文 stored memory 与 query 都刻意加空格(`"魔法 需 血液 代价"` 而非 `"魔法需血液代价"`),让 tokenize 出现 overlap。详见该文件 module docstring。

**对 game 域开发者的影响**:
- 若 stored memory / query 含连续中文短语,RAG 检索可能召回率极差
- **暂行建议**:在 Curator(契约 4)沉淀 memory 时,**自己负责加空格分词**(或用 jieba 之类的中文分词工具预处理)
- query 同理 — 给 `WorldMemory.query(query_text=...)` 传文本时也分好词

**彻底解法**:换成支持 CJK 的真实 embedding model(如 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 或 BGE),或引入 jieba 分词。**留 Phase D / E 处理**,Phase D 实现时若觉得阻碍 demo 质量,可主动提前。

---

## 契约 1: NarrativeBeat schema

每个 game 域定义自己的 NarrativeBeat(`NarrativeAgent.run` 的 `output_schema`)。
约定:必须含**一个返回给玩家看的文本字段**(field name 通过 `TurnLoopConfig.response_text_field` 配置)。

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

game 自定义合法的 memory kind(在 `WorldMemory.upsert` 时打 `metadata["kind"]`)。
Core 用 `kind: str` 不限制具体值,但 `TurnLoopConfig.references_priority_kinds` 和 `MemoryQuery.kinds` 都依赖一致的 kind 字符串集。

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

## 契约 3: NarrativePromptBuilder(可选,用 instruction override)

默认 core 自带 `DEFAULT_NARRATIVE_INSTRUCTION` / `DEFAULT_GUARD_INSTRUCTION`(通用 prose,不含游戏域词)。game 想注入自己的 prompt:

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
- 若有新角色出场,在 new_facts 列出
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
            # 注:fact 含连续中文时,请用 jieba 或手动加空格(见顶部 ⚠ 章节)
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
        if "law" in fact or "rule" in fact:
            return MyGameMemoryKind.WORLD_LAW
        if "location" in fact:
            return MyGameMemoryKind.LOCATION
        return None
```

**注意**:Phase B/C 阶段 TurnLoop 的 `curated_records=[]` hardcoded,
Phase D 时需要把 Curator 接进 TurnLoop(或 TurnLoop 之外的 wrapper)。
最简集成方式:wrapper 函数:

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
    turn_store = TurnStore(data_dir=Path("data/sessions"))

    # --resume 处理:list_sessions 提供历史 session_id 列表(按 mtime 倒序)
    if args.resume:
        available = turn_store.list_sessions()
        if args.resume not in available:
            print(f"Session '{args.resume}' not found. Available: {available[:5]}")
            return
        session_id = args.resume
    else:
        session_id = args.session or "default"

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
        turn_store=turn_store,
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

    print(f"=== Session: {session_id} ===")
    while True:
        user_input = input("> ").strip()
        if not user_input or user_input == "/quit":
            break
        result = await loop.run_turn(session_id=session_id, raw_text=user_input)
        print(result.response_text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", help="New session id (defaults to 'default')")
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

总计 ~330 行 src + ~300 行 test。**Phase D 完成的 success metric**:
跑 10 轮玩家自由对话 + Guard accept 率 ∈ [70%, 90%] + 至少一次成功拦截真实矛盾。

## 已知未实现项(Phase C 之后)

- MemoryCurator 没接进 TurnLoop(Phase D 用 wrapper)
- ChromaRAG 仍用 hashed_text_embedding(基于 _terms 的同一 tokenize 缺陷,见顶部 ⚠ 章节)
- Live LLM smoke tests(Phase D 跑通 demo 后做)
- world_init 仍在 core/agents/debate.py(物理移动到 game/world_init/ 留 Phase E)
- TurnTelemetry 缺 new_facts_kept / total_tokens(Phase D 加 Curator 后填)
