# Turn Loop Engine 重设计

日期:2026-05-26
状态:草稿(brainstorm 已通过,待用户审阅 spec 全文后转 writing-plans)
关系:**部分取代** `2026-05-22-multi-agent-rpg-framework-design.md`

---

## 0. 缘起与设计取舍

### 原 spec(2026-05-22)的问题

原 spec 已实现到 Phase 6 的 world_init 端到端工作流。重新审视后,从产品与平台双视角发现三类问题:

1. **主链路定位错了**。原 spec 把"开局回答一个世界观问题 → 生成 WorldSeed"当作 MVP 主路径,但这只是一次性的"生成器",玩家在它之后没有可持续做的事 — 既不是游戏循环,也不能验证 LLM 长期一致性。
2. **核心抽象未来导向**。Tick Bus / SimulationNode / DAG Coordinator / 反向生成请求等组件在原 spec §15-§17 是为"未来玩法"设计的,无现存消费者,违反 YAGNI。在"纯文本决策型"的引擎定位下永远用不上。
3. **平台向证明不足**。原 spec 只有一个 game 域(world_init),从单一用例抽出来的"通用 core"必然过拟合;且 core 与 game 边界不清,缺乏"做新 game 域要写多少代码"的衡量。

### 重设计的三点校准(brainstorm 阶段已确认)

1. **目标**:平台向(可复用引擎),不是一次性 demo
2. **子类型边界**:纯文本决策型(AI Dungeon / Zork 类)。不做骰子/数值/战斗/tick 模拟
3. **MVP 价值主张**:**LLM 在 5-10 轮自由对话中保持世界设定不崩**(一致性优先)

### 结论

主链路从"生成世界"切换到"玩世界",即 **Turn Loop**:玩家输入 → 检索记忆 → 生成叙事 → 守卫校验 → 沉淀记忆 → 返回响应。原 spec 中"通用 core"和"world_init"的关系被反转:**core 围绕 Turn Loop 设计,world_init 降级为可选开局插件**。

---

## 1. 设计目标

| 维度 | 目标 |
|------|------|
| 性质 | 纯文本决策型 RPG 引擎 |
| 形态 | 可复用底座 + 1 个完整 game 域 demo(text_adventure) |
| MVP 价值主张 | 跑通 10 轮玩家自由对话,LLM 不忘事、不自相矛盾 |
| 平台性 | 新 game 域开发者只需实现 ≤ 5 个清晰契约即可上线新 demo |
| 性能预算 | 单轮端到端 ≤ 30 秒(M1, MIMO mimo-v2.5-pro),平均 LLM 调用 ≤ 4 次/轮 |
| 成本 | 仓库内零 API key;live 测试 opt-in;单 live smoke < $0.01 |

---

## 2. 设计原则

### 原 spec 5 条铁律全部继承

1. Core Engine 与游戏内容彻底解耦(`core/` 不能有游戏概念)
2. Agent 不能直接修改世界状态,只输出 proposal
3. 所有 LLM 输出必须经 Pydantic 校验
4. RAG 是世界黑板,所有长期记忆走它
5. Multi-agent 必须受监管

### 新增 2 条原则

6. **抽象必须有现存消费者**。任何 core 抽象都必须能指出"今天哪个组件在用它";只为未来想象设计的抽象一律不写。
7. **平台能力先证明"组合性",再扩"功能完备"**。一个 game 域跑稳前不抽第二个域;抽象不动手做第二个 demo,只是占位文字。

---

## 3. 与原 spec 章节对应

| 原 spec 章节 | 处置 | 落到本 spec |
|-------------|------|-----------|
| §1-2 目标与铁律 | 保留 + 补充 | §1, §2 |
| §3 总体架构 | 改写 | §4 |
| §4 外接 LLM 配置 | 不变 | — |
| §5 Thinking Policy | 保留,值表更新 | §7.E |
| §6 Core 通用 Schema | 收敛(删 TickEvent / SimulationNode,加 Turn 系列) | §5 |
| §7 LLM Gateway | 保留 + 收紧重试上限 | §7.D |
| §8 Universal RAG Repository | 保留作为底层 | §5(底层),§4(WorldMemory 是其上的语义封装) |
| §9 Agent Runtime | 保留 | §4, §5 |
| §10 Debate System | **降级**为 game/ 层可选编排器,从 core 移出 | §4 |
| §11 Game World Init Schema | 保留(仍归 game/world_init/) | §4 |
| §12 Canon Guard | **提升**为 core 通用 Guard,Canon 是其在 world_init 的一种实例 | §5, §7.B |
| §13 Memory Curator | game/ 层组件,加四道闸 | §7.C |
| §14 Causality Analyzer | 保留作为 world_init 插件的产出,但**删 delay_ticks / target_type 字段**(简化为"叙事种子") | §10 |
| §15 DAG Generation Pipeline | **删除** | — |
| §16 World Tick Bus | **删除** | — |
| §17 动态 Runtime Entity Agent | **延后到 v2**,不在本 spec | §10 |
| §18 MVP 开发路线图 | 整体重写(新路线见 §9) | §9 |
| §19 测试策略 | 重写 + 加回放测试 + 量化指标 | §8 |
| §20 MVP 验收标准 | 重写(围绕一致性指标) | §8.F |
| §21 已定设计决策 | 增补本次决策(见 §11) | §11 |

---

## 4. 架构骨架

```
src/
  core/                          # 不能含任何游戏域概念
    config.py                    # 保留
    schemas.py                   # 收敛:删 TickEvent/SimulationNode,加 Turn/TurnInput/TurnResult
    llm_gateway.py               # 保留(质量高,无须动)
    rag_repository.py            # 保留(Chroma + InMemory 双实现)
    world_memory.py              # 新增:RAG 之上的语义化记忆门面,按 kind 分类的读/写
    turn_loop.py                 # 新增:Turn 编排器,主链路核心
    turn_store.py                # 新增:Turn 整轮序列化存盘(JSONL)
    agents/
      schemas.py                 # 保留(AgentProfile/AgentTask 等)
      runtime.py                 # 保留
      narrative.py               # 新增:单 agent 叙事生成的统一入口
      guard.py                   # 新增:通用"提案 → accept/revise/reject"模式
      debate.py                  # 移出 core,降为 game/ 可选编排器(物理位置改 game/world_init/debate.py)

  game/
    text_adventure/              # 新增:第一个真正的"决策型文字 RPG" demo
      schemas.py                 # NarrativeBeat / NewFact / TextAdventureMemoryKind
      prompts.py                 # 叙事 prompt 模板
      narrative_agent.py         # 配置 NarrativeAgent 的 game-specific profile
      memory_curator.py          # 从 NarrativeBeat 提取 MemoryRecord(含四道闸)
      guard_rules.py             # 注入到 ConsistencyGuard 的硬性规则
      app.py                     # CLI/REPL 入口,跑 10 轮玩家对话
    world_init/                  # 降级:从主路径变为可选开局生成器
      schemas.py                 # 原 PlayerWorldAnswer/WorldLaw/WorldSeed/WorldSeedCandidate
      agents.py / prompts.py / workflow.py / memory.py / debate.py
                                 # 原代码原地保留,只改入口(变成可被 text_adventure 调用的函数)

  main.py                        # 改写为 game.text_adventure.app 的薄入口
```

### 占位清单 / 移动清单(明确)

**原 spec §3/§15/§16 列在目录树里但代码从未新建的占位** — 不要新建:
- `src/core/tick_bus.py`
- `src/core/dag/`(整个子包)
- `src/core/agents/supervisor.py`(受监管职责由 TurnLoop 承担,无需独立 supervisor)
- `src/core/agents/guards.py`(由 `core/agents/guard.py` 取代)

**真实存在,需要物理移动**:
- `src/core/agents/debate.py` → `src/game/world_init/debate.py`(只有 world_init 用它,降级到 game 层。更新所有 import。)

### 边界铁律(可被静态检查)

- `core/*` 不能 `import game.*`
- `core/*` 不能出现游戏域名词(world law / character / location / faction / combat / npc 等)
- 通过 import-graph 测试静态校验(见 §8.B)

---

## 5. 核心 Schema

### 5.1 `core/schemas.py`(收敛)

保留:`Message` / `ThinkingPolicy` / `LLMRequest` / `LLMResponse` / `MemoryFragment` / `RAGQueryResult`

删除:`TickEvent` / `SimulationNode`

新增 Turn 相关:

```python
class TurnInput(BaseModel):
    raw_text: str = Field(min_length=1)            # 玩家本轮原始输入
    intent_hint: str | None = None                 # 可选:玩家自己标的意图(say/do/think)
    turn_index: int = Field(ge=0)                  # 第几轮(从 0 计)
    session_id: str = Field(min_length=1)


class Turn(BaseModel):                             # 一次完整闭环的快照,可序列化存盘
    id: str = Field(default_factory=lambda: uuid4().hex)
    input: TurnInput
    retrieved_memory: list[RAGQueryResult] = Field(default_factory=list)
    narrative_draft: dict[str, Any] | None = None  # 由 game 层指定具体 schema,这里只保 dict
    guard_decision: GuardDecision | None = None
    curated_records: list[MemoryRecord] = Field(default_factory=list)
    response_text: str | None = None
    status: Literal["ok", "degraded", "failed"] = "ok"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TurnResult(BaseModel):                       # 对 game 层暴露的返回值
    turn: Turn
    response_text: str
    guard_retries: int = 0
```

### 5.2 `core/world_memory.py`(新)

```python
class MemoryRecord(BaseModel):                     # MemoryFragment 的语义化封装
    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: str = Field(min_length=1)                # 由 game 层自定义,core 不枚举
    content: str = Field(min_length=1)
    source: str = Field(min_length=1)              # "turn:42" / "world_init" / "manual"
    session_id: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryQuery(BaseModel):
    query_text: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    kinds: list[str] | None = None                 # None = 不限 kind
    top_k: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class WorldMemory:
    """RAG 之上的语义化记忆门面。core 只暴露这个接口,Repository 是实现细节。"""

    def __init__(self, repository: UniversalRAGRepository): ...

    def query(self, q: MemoryQuery) -> list[RAGQueryResult]: ...
    def upsert(self, record: MemoryRecord) -> str: ...
    def upsert_many(self, records: list[MemoryRecord]) -> list[str]: ...
    def find_similar(self, content: str, session_id: str, threshold: float = 0.92) -> MemoryRecord | None: ...
```

**关键决策**:
- `kind` 用 `str` 不用 `Enum`,让 game 层自定义合法集合。Repository 不校验 kind。
- `WorldMemory` 处理 metadata filter / kind 路由 / session_id 隔离 / score 阈值;`UniversalRAGRepository` 只做"向量库"原语。

### 5.3 `core/agents/guard.py`(新)

```python
class GuardFinding(BaseModel):
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1)
    path: str | None = None                        # 提案 payload 的 JSONPath


class GuardDecision(BaseModel):
    decision: Literal["accept", "revise", "reject"]
    findings: list[GuardFinding] = Field(default_factory=list)
    revised_payload: dict[str, Any] | None = None  # decision=revise 时必填(模型校验)


class ReferenceItem(BaseModel):
    label: str                                     # "world_law" / "recent_turn:42" / "character:Aria"
    content: str
    score: float | None = None


class GuardInput(BaseModel):
    proposal: dict[str, Any]
    references: list[ReferenceItem]                # 已排序,Guard prompt 按顺序注入
    rules: list[str]                               # 硬性规则,game 层注入
    session_id: str


class ConsistencyGuard:
    def __init__(self, runtime: AgentRuntime, profile: AgentProfile): ...
    async def check(self, input: GuardInput) -> GuardDecision: ...
```

### 5.4 `core/agents/narrative.py`(新)

```python
class NarrativeContext(BaseModel):
    player_input: TurnInput
    retrieved_memory: list[RAGQueryResult]
    extra: dict[str, Any] = Field(default_factory=dict)  # game 注入场景摘要等


class NarrativeAgent:
    def __init__(self, runtime: AgentRuntime, profile: AgentProfile): ...

    async def run[T: BaseModel](
        self,
        context: NarrativeContext,
        output_schema: type[T],
    ) -> T: ...
```

泛型 `output_schema` 由 game 层指定(text_adventure 用 `NarrativeBeat`)。core 不知道游戏域 schema 长什么样。

### 5.5 `game/text_adventure/schemas.py`(新,示意)

```python
class TextAdventureMemoryKind(str, Enum):
    WORLD_LAW = "world_law"
    LOCATION = "location"
    CHARACTER = "character"
    EVENT = "event"
    PLAYER_STATE = "player_state"
    RELATION = "relation"


class NewFact(BaseModel):
    kind: TextAdventureMemoryKind
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class NarrativeBeat(BaseModel):                    # NarrativeAgent 的 output_schema
    narration: str = Field(min_length=1)           # 给玩家看的散文段落
    new_facts: list[NewFact] = Field(default_factory=list)
    follow_up_hooks: list[str] = Field(default_factory=list)
```

---

## 6. Turn Loop 数据流

### 6.1 单轮时序

```
玩家输入 raw_text
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ TurnLoop.run_turn(session_id, input: TurnInput) -> TurnResult       │
│                                                                     │
│  ① 构造 TurnInput(turn_index = session.next_index())                │
│                                                                     │
│  ② Retrieve:  WorldMemory.query(MemoryQuery(                        │
│                  query_text = input.raw_text,                       │
│                  kinds = game.retrieval_kinds(),                    │
│                  session_id, top_k = 8))                            │
│                                                                     │
│  ③ Narrate:   NarrativeAgent.run(                                   │
│                  context = NarrativeContext(input,                  │
│                                              retrieved_memory,      │
│                                              extra = game.scene_summary()), │
│                  output_schema = game.narrative_schema())           │
│                → NarrativeBeat                                      │
│                                                                     │
│  ④ Guard:     ConsistencyGuard.check(GuardInput(                    │
│                  proposal = beat.model_dump(),                      │
│                  references = build_references(retrieved_memory,    │
│                                                 turn_store.recent(N=3))), │
│                  rules = game.guard_rules()))                       │
│                → GuardDecision                                      │
│                                                                     │
│      ┌─ accept  → 进 ⑤                                              │
│      ├─ revise  → 采用 revised_payload(不重跑 Narrate),进 ⑤        │
│      │           (若 revise 但无 payload,异常 → reject 分支)       │
│      └─ reject  → 走"安全降级"(见 §6.3)                            │
│                                                                     │
│  ⑤ Curate:    records = game.curator.extract(accepted_beat, turn)   │
│                world_memory.upsert_many(records)                    │
│                                                                     │
│  ⑥ Persist:   turn_store.save(turn)  ← 整轮 JSONL 入盘               │
│                                                                     │
│  ⑦ Return:    TurnResult(turn, response_text, guard_retries)        │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 组件职责边界

| 组件 | 归属 | 职责 | 不做的事 |
|------|------|------|---------|
| `TurnLoop` | core | 编排 ①-⑦,装配 references,处理 Guard 决策分支,统一异常 | 不知道游戏域、不写 prompt、不解释玩家意图 |
| `WorldMemory` | core | 按 `MemoryQuery` 检索 / `upsert_many` 写入 | 不决定"写什么内容"(那是 Curator 的事) |
| `NarrativeAgent` | core | 把 `NarrativeContext` + `output_schema` 喂给 `AgentRuntime` | 不知道游戏域 schema 长什么样 |
| `ConsistencyGuard` | core | 把 GuardInput 组装成 prompt,跑 LLM,返回 `GuardDecision` | 不决定规则内容(game 注入)、不重跑 Narrate |
| `TurnStore` | core | 把 `Turn` 序列化 JSONL,支持 `load_recent(session, n)` | 不做语义检索 |
| `MemoryCurator` | **game** | 从 `NarrativeBeat` 提取 `MemoryRecord`(含 kind 分类、四道闸) | 不直接写库 |
| `NarrativePromptBuilder` | **game** | 构造 game-specific prompt 模板与场景摘要 | — |
| `GuardRulesProvider` | **game** | 提供硬性规则字符串列表 | — |

### 6.3 Guard 决策分支细则

- **accept**:直接采用 `proposal`,进 ⑤
- **revise**:
  - 必须返回 `revised_payload`(Pydantic 校验,缺失则视为协议违规,降级为 reject)
  - 直接采用 `revised_payload` 进 ⑤,**不重跑 NarrativeAgent**(避免无界重试)
  - `guard_retries = 1`
- **reject**(或 revise 无 payload):
  - 写入"降级响应":`response_text = game.degradation_text()`(text_adventure 默认 "画面有些模糊,试试换种方式描述你想做的事。")
  - `turn.status = "degraded"`
  - `turn.metadata["guard_rejection"] = findings`
  - **`turn_index` 不前进**(下一轮仍是同一 index)
  - **不写 Curator 输出到 WorldMemory**(避免污染)
  - 仍保存 turn JSONL 供 debug

### 6.4 关键数据流约定

1. **检索范围由 game 注入**:`game.retrieval_kinds()` 决定本轮捞哪些 kind。core 不写死。
2. **Guard references = `retrieved_memory` + `recent_turns(N=3)`**:长期事实从 WorldMemory 来,短期连续性从 TurnStore 来。
3. **NarrativeBeat.new_facts 不直接入库**:必须经 Curator 四道闸(见 §7.C)。
4. **整轮入盘**:`data/sessions/<session_id>.jsonl`,每行一个 Turn。便于续接、debug、回放测试。

---

## 7. 一致性策略 + 错误处理

### 7.A 一致性失败的分类

| 失败类别 | 例子 | 主要防御点 |
|---------|---------|-----------|
| 法则违反 | 第 2 轮定下"魔法需血液代价",第 5 轮 NPC 免费施法 | Guard 必须看到 `world_law` 类记忆 |
| 事实矛盾 | 第 3 轮"国王已死",第 7 轮国王又出场 | Guard 必须看到 `event` + `character` 类记忆 |
| 状态遗忘 | 玩家 5 轮前拿到钥匙,LLM 让他再找一次 | Retrieve 必须捞 `player_state`;Curator 沉淀状态变化 |
| 时空错乱 | 玩家在森林,LLM 描写他回到酒馆 | 当前 `location` + 最近 3 轮 `event` 强制注入 Narrative |
| 角色串味 | 沉默 NPC 突然演讲 | 出现的 character.persona 摘要必须注入 |
| 选择无后果 | 玩家"杀了 NPC",下一轮 NPC 又出现 | new_facts 必须 curated 入库,confidence 阈值合理 |

**核心洞察**:一致性是 Retrieve / Narrate prompt 注入 / Guard 校验 / Curate 沉淀**四环节协同**的结果。任何一环疏漏 Guard 都救不回来。

### 7.B ConsistencyGuard 具体设计

**输入**见 §5.3 `GuardInput`。

**References 组装顺序**(决定 prompt 中的呈现顺序):

```
1. 硬性规则(game.guard_rules,3-5 条,自由文本)
2. world_law 类记忆(top 5,按 score 排序)
3. 最近 3 轮 turn 摘要(player_state / 当前 location / 出场角色)
4. character 类记忆(只含本轮提案提到的角色名)
5. event 类记忆(top 3,按时间倒序)
```

为什么硬性规则最前:LLM 对 prompt 头尾敏感度高于中段,不可妥协的东西压最前。

**Guard prompt 模板**(简化示意):

```
你是 Canon Guard。判断"提案"是否违反"参考材料",返回 accept / revise / reject。

规则:
- accept:提案与参考一致,直接放行
- revise:存在可修复的小矛盾(NPC 名字拼错、用词不准),
         必须给出 revised_payload(修订后的完整提案)
- reject:存在不可修复的矛盾(违反世界法则、复活死人、凭空物品)

【硬性规则】{rules}
【世界法则】{world_laws}
【最近 3 轮】{recent_turns}
【相关角色】{characters}
【相关事件】{events}
【待审提案】{proposal}

返回 GuardDecision JSON。
```

**Guard 配置**:`thinking=enabled` / `temperature=0.2` / `max_tokens=2048`。

### 7.C MemoryCurator 四道闸

Curator 是 game 层组件,但受 core 强制约束。入库前过 4 道闸:

1. **Schema 校验** — `MemoryRecord` 字段完整且 `kind ∈ game.allowed_kinds()`
2. **Confidence 闸**:
   - `≥ 0.8` → 直接入库
   - `0.5-0.8` → 入 `pending_facts`,下一轮被引用时正式入库("双重确认")
   - `< 0.5` → 丢弃
3. **去重闸**:embedding cosine > 0.92 视为重复,合并(更新 source,不新建)
4. **冲突闸**(MVP 不实现,留 v2):cosine > 0.85 但陈述矛盾(简单关键词 "不是 / 改为 / 其实")→ 抛 `MemoryConflictError`

**MVP 简化**:Curator 第一版**完全不调 LLM**,纯规则从 `NarrativeBeat.new_facts` 转 `MemoryRecord`。省 1/3 LLM 成本。

### 7.D LLM Gateway 错误处理

继承原 spec §7,以下收紧 / 新增:

| 错误 | 处理 |
|------|------|
| Pydantic 校验失败 | 反馈错误 + schema 重试,**上限 2 次** |
| `finish_reason=length` 且正文为空 | `max_tokens × 2`,上限 8192,重试 1 次 |
| 供应商 5xx / timeout | 指数退避(1s/3s/9s),最多 3 次 |
| 连续 5 次调用失败 | 触发熔断,15 分钟内 NarrativeAgent / Guard 直接抛 `GatewayCircuitOpen` |
| Schema 重试时 | **强制 `thinking=disabled` + `temperature=0.1`** |

**TurnLoop 捕获 `GatewayCircuitOpen`** → 走 §6.3 降级分支,turn 标记 `failed`,turn_index 不前进。绝不让玩家看到技术错误信息。

### 7.E Thinking Policy 配置矩阵

| 步骤 | thinking | temperature | max_tokens | 理由 |
|------|---------|-------------|-----------|------|
| ② Retrieve | — | — | — | 无 LLM |
| ③ NarrativeAgent | `enabled` | 0.8 | 4096 | 创作主路径 |
| ④ ConsistencyGuard | `enabled` | 0.2 | 2048 | 关键推理,要稳 |
| ⑤ MemoryCurator(MVP 不调 LLM) | — | — | — | 纯规则 |
| ⑤ MemoryCurator(v2 若调 LLM) | `disabled` | 0.3 | 1024 | 摘要+分类,格式优先 |
| Schema 修复重试 | `disabled` | 0.1 | 同原值 | 格式收敛 |

### 7.F 可观测性:TurnTelemetry

每个 Turn 强制记录,进 `Turn.metadata.telemetry`:

```python
class TurnTelemetry(BaseModel):
    retrieval_hit_count: int
    retrieval_top_score: float
    guard_decision: str                  # accept / revise / reject
    guard_findings_count: int
    guard_retries: int                   # 0 或 1
    new_facts_kept: int
    new_facts_dropped: int
    llm_call_count: int
    total_tokens: int
    duration_ms: int
```

是 MVP 验收的量化基础。

---

## 8. 测试策略 + MVP 验收

### 8.A 测试金字塔

```
                  ▲
                  │  ① Live smoke(opt-in,真 LLM,~3 个)
                  │  ② 回放测试(真 session JSONL 当 fixture,~5 个)
                  │  ③ 集成测试(假 LLM,全 TurnLoop,~10 个)
                  │  ④ 单元测试(每个 core/game 模块)
                  ▼
```

### 8.B 单元测试覆盖矩阵

| 模块 | 必测的契约 |
|------|----------|
| `core/schemas.py` | Turn / TurnInput / MemoryRecord / MemoryQuery 的 Pydantic 边界值 |
| `core/llm_gateway.py` | mock provider 下:成功 / Pydantic 失败重试 / `finish_reason=length` 重试 / 5xx 退避 / 熔断打开 |
| `core/rag_repository.py` | `InMemoryRAGRepository.upsert / hybrid_search` 的 filter / top_k / score 排序 |
| `core/world_memory.py` | kinds 过滤 / session_id 隔离 / min_score 阈值 / upsert_many 返回 id 列表 |
| `core/agents/runtime.py` | 系统消息含 schema_json / 用户消息含 instruction+context / thinking_override 生效 |
| `core/agents/narrative.py` | 泛型 output_schema 透传 / NarrativeContext 序列化进 prompt |
| `core/agents/guard.py` | references 顺序 / revise 必须含 revised_payload / reject 不含 |
| `core/turn_loop.py` | accept 一次过 / revise 直接采用 payload / revise 无 payload 降级 / reject 降级 / `GatewayCircuitOpen` 降级 / turn_index 在降级时不前进 |
| `core/turn_store.py` | JSONL 序列化往返一致 / `load_recent(n)` 返回最近 n 条 |
| `game/text_adventure/memory_curator.py` | confidence 三档闸 / 去重(embedding) / kind 非法时抛错 |
| `game/text_adventure/narrative_agent.py` | game 注入的 prompt 模板正确装配 / scene_summary 进 extra |
| **import-graph 测试** | `core/*` 不 import `game/*`;`core/*` 文件文本不含游戏域名词集合(world_law/character/location/faction/combat/npc/scene 等) |

约定:
- 所有 LLM 测试用 `FakeLLMGateway`(返回预编排响应),不 mock httpx
- 所有 RAG 测试用 `InMemoryRAGRepository`,不起 Chroma
- `pytest` + `pytest-asyncio`(已配)

### 8.C 集成测试(全链路,假 LLM,~10 用例)

每个测试一个完整 TurnLoop,`FakeLLMGateway` 编排各 agent 响应。覆盖 §7.A 的 6 类失败 + 4 类边界:

- `test_turn_loop_accepts_consistent_narrative`
- `test_turn_loop_guard_revises_npc_name_typo`
- `test_turn_loop_rejects_law_violation_and_degrades`
- `test_turn_loop_rejects_revives_dead_character_and_degrades`
- `test_turn_loop_rejects_player_state_violation_and_degrades`
- `test_turn_loop_rejects_location_jump_and_degrades`
- `test_turn_loop_rejects_character_voice_drift_and_degrades`
- `test_turn_loop_circuit_open_degrades_gracefully`
- `test_turn_loop_persists_full_turn_jsonl`
- `test_turn_loop_curator_double_confirms_medium_confidence_fact`

### 8.D 回放测试(MVP 后期加,spec 留接口)

```python
@pytest.mark.replay
async def test_replay_session_01_consistency_invariants():
    session = load_session_fixture("session_01.jsonl")
    # 不重跑 LLM,只检查不变量:
    # - 任意 turn 的 retrieved_memory 与那一刻 WorldMemory 内容一致
    # - 所有 accepted beat 的 new_facts 都能在后续 turn 的 retrieved_memory 找到
    # - 没有"已死亡角色"出现在后续 turn 的 character refs
```

不消耗 LLM token,可入 CI。

### 8.E Live smoke(opt-in,默认不入 CI)

`pyproject.toml`:`markers = ["live: requires MIMO_API_KEY"]`

```python
@pytest.mark.live
@pytest.mark.skipif(not os.getenv("MIMO_API_KEY"), reason="needs live key")
async def test_live_single_narrative_smoke(): ...   # 1 次 Narrative 调用
async def test_live_single_guard_smoke(): ...       # 1 次 Guard 调用
async def test_live_one_turn_end_to_end(): ...      # 完整 1 Turn(最贵,手动触发)
```

- 默认 / CI:`pytest -m "not live"`
- 手动:`pytest -m live`
- 每个 live 测试单次成本 < $0.01

### 8.F MVP 验收清单(可量化)

**全部**达成才算 MVP:

**功能性**
- [ ] `python -m game.text_adventure.app` 可跑通 10 轮玩家自由对话
- [ ] 启动可选 `--with-world-init`(挂载 world_init 工作流作为开局生成器),证明 world_init 已成功降级为可选插件
- [ ] 每轮玩家输入到响应 ≤ 30 秒(M1 + MIMO mimo-v2.5-pro)
- [ ] session 中途 Ctrl-C 后,`--resume <session_id>` 能续接

**一致性**(核心价值主张)
- [ ] 跑 5 个不同的 10 轮 demo,每个 demo:
  - Guard accept 率 ∈ [70%, 90%]
  - Guard revise 率 ∈ [10%, 25%]
  - Guard reject 率 < 5%
- [ ] 至少 1 个 demo 中,Guard 成功拦截真实矛盾(NPC 复活 / 凭空物品 / 场景错乱任一)
- [ ] 没有 demo 出现"已死亡 NPC 重新出场"或"玩家两次找到同一把钥匙"

**工程性**
- [ ] `pytest -m "not live"` 全绿,覆盖率 ≥ 80%(只统计 `src/`)
- [ ] `pytest -m live` 全绿(手动跑,3 个 smoke 全过)
- [ ] 仓库内无 API key
- [ ] `data/sessions/<id>.jsonl` 可被 `Turn.model_validate_json` 逐行解回
- [ ] import-graph 测试通过(`core/*` 不 import `game/*`,不含游戏域名词)

**平台性**(为下一步 game 域做准备)
- [ ] `core/turn_loop.py` 文件文本不含 `text_adventure` 字样
- [ ] `docs/superpowers/specs/extending-the-engine.md` 已写(MVP 收官前补,不阻塞 MVP 主功能),列出"新 game 域要实现的 5 个契约":narrative schema / prompts / memory curator / guard rules / app entry
- [ ] world_init 作为"非 text_adventure 的 game/ 域使用 core"的反例存在,可被 import 但不必被主入口调用

---

## 9. 实施路线图(为下一步 writing-plans 提供蓝图)

按"先底座、再主链路、再 game 域"的顺序,5 个 Phase 串联。每个 Phase 都是**可独立 commit + 可独立跑测试**的 milestone。

### Phase A:底座清理 + core schema 收敛

- `core/schemas.py`:删 `TickEvent` / `SimulationNode`,加 `TurnInput` / `Turn` / `TurnResult`
- 新建 `core/agents/guard.py`(`GuardFinding` / `GuardDecision` / `ReferenceItem` / `GuardInput` / `ConsistencyGuard`)
- 新建 `core/agents/narrative.py`(`NarrativeContext` / `NarrativeAgent`)
- 新建 `core/world_memory.py`(`MemoryRecord` / `MemoryQuery` / `WorldMemory`)
- 新建 `core/turn_store.py`(JSONL 序列化)
- 单元测试同步落地

注:`supervisor.py` / `guards.py` / `tick_bus.py` / `dag/` 在原 spec 仅是目录树占位文字,代码从未新建,本 Phase 不需要"删除动作"。

### Phase B:Turn Loop 主路径

- 新建 `core/turn_loop.py`,实现 §6.1 时序
- 实现 Guard 决策分支(§6.3)、降级路径
- 实现 `FakeLLMGateway` 测试工具
- 集成测试(§8.C)前 4 个用例(accept / revise / reject / circuit open)

### Phase C:一致性子系统完整化

- 实现 References 组装(§7.B)
- 实现 Telemetry 记录(§7.F)
- 实现 import-graph 测试(§8.B 最后一项)
- 集成测试剩余 6 个用例

### Phase D:text_adventure game 域 MVP

- `game/text_adventure/schemas.py`(`NarrativeBeat` / `NewFact` / `TextAdventureMemoryKind`)
- `game/text_adventure/prompts.py`(叙事 prompt 模板)
- `game/text_adventure/narrative_agent.py`(配置 game-specific profile)
- `game/text_adventure/memory_curator.py`(四道闸 §7.C)
- `game/text_adventure/guard_rules.py`(硬性规则)
- `game/text_adventure/app.py`(CLI 入口,跑 10 轮)
- `main.py` 改写为 `text_adventure.app` 薄入口

### Phase E:world_init 降级 + 续接能力 + 收尾

- **物理移动**:`src/core/agents/debate.py` → `src/game/world_init/debate.py`,更新所有 import 引用(`workflow.py` 是当前唯一使用方)
- `game/world_init/` 其余代码原地保留,只调整入口(变成可被 text_adventure.app 调用的函数)
- `text_adventure.app` 加 `--with-world-init` flag
- 实现 `--resume <session_id>` 续接
- 简化 `CausalImpactPacket`(删 `delay_ticks` / `target_type`,改为"叙事种子")
- 写 `docs/superpowers/specs/extending-the-engine.md`
- 跑 5 个真实 demo,统计 §8.F 一致性指标
- 达成 MVP 验收清单全部条目

每个 Phase 结束都跑 `pytest -m "not live"` 全绿 + 提交 commit。

---

## 10. 不在本 spec 范围(明确剪枝)

- NPC 永生 / Combat / Inventory / Skill 数值系统
- Tick Bus / SimulationNode / 持续模拟
- 多个 game/ 域(只先做 text_adventure)
- Multi-Agent Debate 作为 core 能力(仅在 world_init 插件内保留)
- Web UI / 多人 / 存档版本管理
- Causality 的因果传播(只保留"叙事种子"作为开局副产物)
- Runtime Entity Agent(NPC 实时对话)— 延后到 v2

---

## 11. 已定设计决策

承接原 spec §21,本次新增 / 修订:

1. 主链路从"world_init 生成"切换到"Turn Loop"
2. world_init 整体降级为 game 层可选开局插件
3. Tick Bus / SimulationNode / DAG Coordinator / 反向生成请求 / 动态 Runtime Entity Agent 全部删除或延后
4. `MemoryKind` 用 `str`,不在 core 枚举,让 game 层自定义
5. `Turn` 完全可序列化,JSONL 存盘,便于续接 / debug / 回放测试
6. Guard 提升为 core 通用组件;Canon Guard 是其在 world_init 的实例
7. Guard 决策分支:accept 直进、revise 直接采用 revised_payload(不重跑 Narrate)、reject 降级
8. Guard 重试上限 1 次,失败走"安全降级"(turn_index 不前进,不污染 WorldMemory)
9. MemoryCurator MVP 不调 LLM,纯规则;v2 再加 LLM 摘要能力
10. Curator 四道闸:Schema / Confidence(三档)/ 去重 / 冲突(冲突闸 v2 实现)
11. References 顺序:硬性规则 > world_law > 最近 3 轮 > 相关角色 > 相关事件
12. NarrativeAgent thinking=enabled + temperature=0.8;Guard thinking=enabled + temperature=0.2
13. LLM Gateway 熔断阈值:连续 5 次失败 → 15 分钟熔断
14. 一致性是 4 环节(Retrieve / Narrate / Guard / Curate)协同结果,不是单点责任
15. core 与 game 边界由 import-graph 静态校验,且 core 文件文本不含游戏域名词
16. 平台性证明先做"组合性"(同一 core 同时支持 text_adventure 主路径 + world_init 插件),不抽第二个 game 域
