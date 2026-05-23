# Multi-Agent RPG 框架设计

日期：2026-05-22

## 1. 目标

构建一个 AI 驱动的高自由度 RPG 框架：创意推理由多智能体完成，但运行时底座必须保持确定性、可审计、可校验、可降级。

MVP 第一闭环：

```text
玩家回答一个世界观问题
-> 多个 Debate Agent 分别推理
-> Synthesizer 融合为结构化 WorldSeedCandidate
-> CanonGuard 做一致性裁决
-> MemoryCurator 写入 Chroma
-> CausalityAnalyzer 生成第一批因果影响包
```

本阶段优先跑通一条完整链路，不追求一开始覆盖所有玩法系统。

## 2. 架构铁律

1. Core Engine 与游戏内容彻底解耦。
   - `core/` 不能包含具体游戏机制或设定实体。
   - `core/` 只能使用 node、event、memory、task、agent、schema、state、change 等通用概念。
   - world law、character、location、faction、combat 等领域概念只允许出现在 `game/`。

2. Agent 不能直接修改世界状态。
   - Agent 只输出 proposal。
   - Core 负责校验 proposal。
   - 只有被接受的 proposal 才能进入状态存储或 RAG。

3. 所有 LLM 输出必须经过 Pydantic 校验。
   - 结构化输出统一使用 Pydantic。
   - 校验失败时由 LLM Gateway 自动注入错误反馈并重试。
   - 多次失败后返回受控错误，不能让幻觉导致引擎崩溃。

4. RAG 是世界黑板。
   - 长期记忆、世界法则、历史事件、摘要、因果影响包都沉淀为结构化 memory fragment。
   - MVP 先实现语义检索，接口预留关键词/BM25 混合检索。

5. Multi-agent 必须受监管。
   - Agent 负责创意推理、冲突发现、摘要整理、因果分析。
   - Core 负责调度、重试、持久化、校验、审计。

## 3. 总体架构

```text
src/
  core/
    config.py
    schemas.py
    llm_gateway.py
    rag_repository.py
    tick_bus.py
    dag/
      schemas.py
      skill.py
      coordinator.py
    agents/
      schemas.py
      runtime.py
      debate.py
      supervisor.py
      guards.py

  game/
    world_init/
      schemas.py
      questions.py
      agents.py
      workflow.py
    npc/
      schemas.py
      interaction.py

  main.py
tests/
data/
```

`core/` 拥有通信、校验、编排、检索、调度能力。`game/` 拥有 prompt、世界 Schema、初始化逻辑、领域技能。

## 4. 外接 LLM 配置

MVP 使用 OpenAI 兼容协议。

```text
base_url: https://token-plan-cn.xiaomimimo.com/v1
chat_url: https://token-plan-cn.xiaomimimo.com/v1/chat/completions
model: mimo-v2.5-pro
```

实测结论：

- `MiMo-V2.5-Pro` 这个大小写形式会返回模型不支持。
- `/v1/models` 返回的可用 ID 是 `mimo-v2.5-pro`。
- 使用 `mimo-v2.5-pro` 的 chat completion 可以成功返回内容。
- 短结构化 smoke test 建议附带 `thinking: {"type": "disabled"}`，否则输出预算可能被隐藏 reasoning 消耗。
- 关键推理任务不应全局关闭 thinking，应由 request 或 agent task 显式选择。
- `thinking: {"type": "enabled"}` 已实测可用；但 `max_tokens=128` 时正文可能为空，因为 token 被 reasoning 消耗。
- 开启 thinking 的结构化任务应使用更高 `max_tokens`，MVP 建议不低于 1024，世界构建和辩论默认 4096。

API Key 必须通过环境变量传入，不能写入仓库。

## 5. Thinking Policy

Thinking 不能做成全局开关。MVP 使用三档策略，在每次请求或 Agent 任务上选择推理深度。

```text
disabled  # 快速、便宜，适合高频或格式稳定任务
auto      # 默认策略，由任务类型和 Agent profile 决定
enabled   # 深推理，适合世界构建、辩论、裁决、因果分析
```

推荐映射：

| 场景 | Thinking |
|---|---|
| 开局世界构建 | enabled |
| Multi-Agent Debate | enabled |
| Synthesizer 融合世界种子 | enabled |
| CanonGuard 一致性裁决 | enabled |
| CausalityAnalyzer 蝴蝶效应分析 | enabled |
| MemoryCurator 摘要入库 | auto |
| 普通高频对话 | disabled |
| 关键运行时决策 | enabled |
| Schema 修复重试 | disabled |

Token 预算规则：

- `thinking=enabled` 时，Gateway 应保证 `max_tokens` 不低于配置下限。
- 若供应商返回 `finish_reason=length`、正文为空、且 usage 中 reasoning token 明显大于 0，Gateway 应自动用更高 `max_tokens` 重试一次。
- Schema 修复重试优先关闭 thinking，因为修复阶段目标是格式收敛，不是重新推理。

策略优先级：

```text
AgentTask.thinking_override
-> AgentProfile.thinking
-> LLMGateway default_thinking
```

Token 预算优先级：

```text
AgentTask.max_tokens_override
-> AgentProfile.max_tokens
-> LLMRequest.max_tokens
-> LLMGateway minimum_for_thinking_enabled
```

Gateway 只负责把策略翻译成 provider payload，不负责判断某个游戏场景是否重要。场景重要性由 `game/` 层或 Agent profile 声明。

## 6. Core 通用 Schema

`core/schemas.py` 只定义内容无关的数据契约。

```python
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ThinkingPolicy(BaseModel):
    type: Literal["disabled", "auto", "enabled"] = "auto"


class LLMRequest(BaseModel):
    messages: list[Message]
    model: str = "mimo-v2.5-pro"
    temperature: float = 0.7
    max_tokens: int = 4096
    thinking: ThinkingPolicy = Field(default_factory=ThinkingPolicy)
    extra: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: dict[str, Any] = Field(default_factory=dict)
    cached: bool = False


class MemoryFragment(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class RAGQueryResult(BaseModel):
    fragment: MemoryFragment
    score: float


class TickEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    tick_id: str | None = None
    event_type: str
    source_id: str
    target_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SimulationNode(BaseModel):
    id: str
    node_type: str
    active: bool = True
    last_tick: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
```

这些 Schema 不包含游戏业务名词。

## 7. LLM Gateway

`core/llm_gateway.py` 是唯一直接访问外部模型供应商的底层组件。

职责：

- 构造 OpenAI 兼容 chat completion 请求。
- 根据 `LLMRequest.thinking` 构造 provider payload。
- 在付费调用前查询语义缓存。
- 从 LLM 原始输出中提取 JSON。
- 使用 Pydantic 校验结构化响应。
- Schema 校验失败时自动反馈错误并重试。
- 供应商连续失败时触发熔断。

公共接口：

```python
class LLMGateway:
    async def complete(self, request: LLMRequest) -> LLMResponse:
        ...

    async def complete_and_parse[T: BaseModel](
        self,
        request: LLMRequest,
        output_schema: type[T],
    ) -> T:
        ...
```

语义缓存策略：

- 使用 `sentence-transformers/all-MiniLM-L6-v2` 对任务 prompt 做 embedding。
- embedding 归一化。
- 使用 cosine similarity。
- 相似度超过阈值时返回缓存。
- 对必须保持新鲜度的任务允许跳过缓存。

失败恢复流程：

```text
call model
-> extract JSON
-> Pydantic validate
-> 如果失败，把校验错误和目标 schema 写回上下文
-> 降低 temperature，并把 thinking 切到 disabled 后重试
-> 如果 thinking enabled 导致正文为空且 finish_reason=length，提高 max_tokens 后重试
-> 多次失败后抛出 GatewaySchemaError
-> 供应商连续失败后打开 circuit breaker
```

Provider payload 规则：

```text
ThinkingPolicy(type="disabled") -> {"thinking": {"type": "disabled"}}
ThinkingPolicy(type="enabled")  -> {"thinking": {"type": "enabled"}}
ThinkingPolicy(type="auto")     -> 不强制覆盖供应商默认，或使用配置中的默认策略
```

## 8. Universal RAG Repository

`core/rag_repository.py` 封装 Chroma，只暴露统一记忆接口。

```python
class UniversalRAGRepository:
    def upsert(self, fragment: MemoryFragment) -> str:
        ...

    def upsert_batch(self, fragments: list[MemoryFragment]) -> list[str]:
        ...

    def hybrid_search(
        self,
        query: str,
        top_k: int = 8,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RAGQueryResult]:
        ...
```

MVP 实现：

- Chroma persistent client，数据目录为 `data/chroma`。
- 本地 embedding 模型：`all-MiniLM-L6-v2`。
- metadata filter 用于限制检索范围。
- 先做语义检索。
- 之后在同一个 `hybrid_search` 接口下加入关键词/BM25。

Repository 存储的是 memory fragment，不是领域对象。领域对象由 `game/` 工作流转换为文本和 metadata 后写入。

## 9. Agent Runtime

`core/agents/` 提供受监管的多智能体执行能力。

### 9.1 Agent Schema

```python
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from core.schemas import Message, ThinkingPolicy


class AgentProfile(BaseModel):
    id: str
    name: str
    role: str
    objective: str
    style_rules: list[str] = Field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    thinking: ThinkingPolicy = Field(default_factory=ThinkingPolicy)
    output_schema_name: str | None = None


class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    instruction: str
    context: dict[str, Any] = Field(default_factory=dict)
    required_output: str
    thinking_override: ThinkingPolicy | None = None
    max_tokens_override: int | None = None


class AgentRunResult(BaseModel):
    agent_id: str
    task_id: str
    raw_content: str
    parsed: dict[str, Any] | None = None
    messages: list[Message] = Field(default_factory=list)


class ProposedChange(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    change_type: str
    subject_id: str | None = None
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    source_agent_ids: list[str] = Field(default_factory=list)
    status: Literal["proposed", "accepted", "rejected"] = "proposed"
```

### 9.2 AgentRuntime 接口

```python
class AgentRuntime:
    def __init__(self, gateway: LLMGateway):
        self.gateway = gateway

    async def run_agent[T: BaseModel](
        self,
        profile: AgentProfile,
        task: AgentTask,
        output_schema: type[T],
    ) -> T:
        ...
```

Runtime 将 profile 和 task 组装为 messages，调用 `LLMGateway.complete_and_parse()`，返回经过 Pydantic 校验的对象。

Runtime 不知道 world law、character、location、faction 等领域概念。

## 10. Debate System

`core/agents/debate.py` 提供通用辩论编排。具体 prompt 由 `game/` 注入。

```python
class DebateTurn(BaseModel):
    agent_id: str
    position: str
    claims: list[str]
    concerns: list[str] = Field(default_factory=list)
    proposed_changes: list[ProposedChange] = Field(default_factory=list)


class DebateSessionResult(BaseModel):
    turns: list[DebateTurn]
    consensus_points: list[str]
    unresolved_tensions: list[str]
```

MVP Debate Agents：

- Expander：扩展玩家回答的潜力和后果。
- Critic：发现逻辑漏洞、代价缺口和矛盾。
- Drama Designer：提炼长期张力和未来冲突压力。
- Synthesizer：把辩论结果融合为一个候选 WorldSeed。

Debate System 只产生结构化中间产物，不直接持久化。

## 11. Game World Initialization Schema

`game/world_init/schemas.py` 定义领域层世界种子。

```python
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class PlayerWorldAnswer(BaseModel):
    question_id: str
    question_text: str
    answer_text: str


class WorldLaw(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    statement: str
    cost: str | None = None
    limitation: str | None = None
    contradiction_risks: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class WorldSeedCandidate(BaseModel):
    premise: str
    laws: list[WorldLaw]
    tensions: list[str]
    open_questions: list[str]
    source_summary: str


class WorldSeed(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    version: int = 1
    premise: str
    laws: list[WorldLaw]
    tensions: list[str]
    accepted_sources: list[str] = Field(default_factory=list)


class CausalImpact(BaseModel):
    target_type: Literal["node", "group", "region", "rule", "unknown"]
    target_hint: str
    impact_summary: str
    intensity: float = Field(ge=0.0, le=1.0)
    delay_ticks: int = Field(ge=0)
    tags: list[str] = Field(default_factory=list)


class CausalImpactPacket(BaseModel):
    source_world_seed_id: str
    trigger_summary: str
    impacts: list[CausalImpact]
```

领域 Schema 可以包含游戏概念，因为它们不属于 Core Engine。

## 12. Canon Guard

Guard 职责：

- 检查内部一致性。
- 检查每条生成法则是否有明确限制或代价。
- 检查候选结果是否违背玩家回答。
- 检查输出是否足够具体，能支持后续模拟。
- 返回 accept、revise 或 reject。

Schema（MVP 实现，位于 `game/world_init/workflow.py`）：

```python
class GuardDecision(BaseModel):
    decision: Literal["accept", "revise", "reject"]
    findings: list[str] = Field(default_factory=list)
```

MVP 行为：

- accept：把 `WorldSeedCandidate` 转为 `WorldSeed`。
- revise：将 `findings` 通过 `build_revision_task` 反馈给 Synthesizer 重新合成，
  由 `WorldInitWorkflow.max_revisions` 限定修订轮数（默认一轮）。
- reject：抛出明确校验错误；修订预算耗尽后仍为 revise 同样抛错。

> 已实现说明：spec 早期设想的 `GuardFinding`（severity/path）与
> `revised_payload`、以及 `core/agents/guards.py` 通用 guard 抽象尚未落地。
> 当 Tick Loop 引入更多 guard 时再统一抽象，届时 `findings` 升级为结构化类型。

## 13. Memory Curator

Memory Curator 防止 RAG 变成原始对话垃圾堆。

已实现说明：对 `WorldSeed`、`WorldLaw`、`CausalImpactPacket`、`NodeTickOutcome`
这类**结构化产物**，MVP 使用确定性转换函数（`game/*/memory.py`）把对象转成
带 metadata 的 `MemoryFragment`，不调用 LLM —— 确定、可复现、零额外成本。
基于 Agent 的摘要式 Curator 仅在处理**自由文本运行时事件**时才需要，推后实现。

职责（转换函数 + 未来的摘要 Curator 共同覆盖）：

- 把结构化领域对象转成可长期保存的 fragment。
- 添加 metadata：`kind`、`source`、`world_seed_id`、`question_id`、`created_by`。
- 将筛选后的 fragment 写入 Chroma。
- 避免存储密钥或供应商凭证。
- （推后）总结自由文本辩论 / 交互结果。

示例 fragment：

```text
kind=world_seed
content=<canonical premise and accepted laws>

kind=world_law
content=<one accepted law with cost, limitation, and tags>

kind=causal_seed
content=<initial causal impact packet summary>
```

Curator 可以调用 Agent 做摘要，但真正写入由 Repository 在校验后执行。

## 14. Causality Analyzer

Causality Analyzer 是第一版“多影响因子下的蝴蝶效应”机制。

它不是中央剧情导演。它只生成延迟影响包，后续由 Tick Bus 投递给模拟节点。

输入：

- 已接受的 `WorldSeed`。
- 玩家回答。
- Debate 中留下的 tensions。

输出：

- `CausalImpactPacket`。

规则：

- 每个 impact 必须有强度。
- 每个 impact 必须有延迟 tick。
- 每个 impact 只指向抽象 target hint，不保证目标实体已经存在。
- 后续系统通过 RAG 和生成技能把 hint 解析为具体节点。

这样能保留长期因果发酵，同时避免 Agent 直接改世界。

## 15. DAG Generation Pipeline

DAG 系统仍然是插件化生成管线。它负责协调普通生成技能和 Agent 工作流。

```python
class GenerationDependency(BaseModel):
    skill_name: str
    required: bool = True
    reason: str


class SkillRequest(BaseModel):
    skill_name: str
    input: dict[str, Any] = Field(default_factory=dict)


class SkillResult(BaseModel):
    skill_name: str
    output: dict[str, Any]
    proposed_requests: list[SkillRequest] = Field(default_factory=list)


class IGenerationSkill(Protocol):
    name: str
    dependencies: list[GenerationDependency]

    async def execute(self, context: PipelineContext) -> SkillResult:
        ...
```

Coordinator 支持反向生成请求：

```text
skill A 发现缺少前置依赖 X
-> 返回 proposed SkillRequest
-> DAG coordinator 检查是否成环
-> 调度能生成 X 的 skill
-> 带着新结果恢复 skill A
```

这让生成流程可以动态按需展开，而不是固定线性流程。

## 16. World Tick Bus

Tick Bus 负责初始化后的持续世界推演。

MVP 职责：

- 注册通用 simulation node。
- 发布经过校验的 event。
- 按计划或因果影响包唤醒节点。
- 从 RAG 检索相关上下文。
- 让 `game/` 层 prompt builder 构造模拟 prompt。
- 通过 Memory Curator 保存模拟摘要。

边界：

Tick Bus 不理解领域机制。它只知道 node、event、payload 和 memory fragment。

### 16.1 Tick Loop v0（首个推演闭环）

MVP 的第一个推演闭环。目标是把静态 `WorldSeed` 变成能逐 tick 前进的世界，
不追求覆盖完整模拟系统。

核心模型：离散事件模拟。世界时间按 tick 逐格推进；主循环是确定性代码；
LLM 只在节点被唤醒时调用一次，输出经 Pydantic 校验后才允许提交。LLM 失败
不影响 tick 推进，本格降级处理。

**`core/tick_bus.py`（确定性调度器，无领域知识）**

```python
class TickBus:
    current_tick: int

    def register_node(self, node: SimulationNode) -> None: ...
    def schedule_event(self, event: TickEvent, fire_at_tick: int) -> None: ...
    def advance(self) -> list[TickEvent]: ...   # tick += 1，返回本格到期事件
    def pending_count(self) -> int: ...
```

TickBus 只认识 node / event / tick，不知道 world law、character、faction。

**Bootstrap：因果包 → 初始节点与事件**

世界初始化产出的 `CausalImpactPacket` 是推演的燃料。对每个 `CausalImpact`：

- 用 `target_hint` 派生一个 `SimulationNode`（`node_type` 取自 `target_type`）。
- 按 `delay_ticks` 把一个 `TickEvent` 登记到 TickBus。

v0 用 metadata（节点 id / tags / world_seed_id）路由检索，不依赖语义向量，
因此可以先不引入真 embedding。

**节点回合（`game/world_sim/`）**

节点被唤醒时，`game/` 层执行：

```text
取 RAG 上下文（metadata 过滤）
-> 构造 node tick 任务
-> AgentRuntime 跑节点 agent
-> 校验得到 NodeTickOutcome
```

`NodeTickOutcome` 是领域层输出 schema：

```python
class NodeTickOutcome(BaseModel):
    node_id: str
    tick: int
    narrative: str
    proposed_changes: list[ProposedChange] = Field(default_factory=list)
    new_impacts: list[CausalImpact] = Field(default_factory=list)
```

**提交**

只有校验通过的 outcome 才提交：

- 把 outcome 摘要转成 `MemoryFragment`（`kind=tick_outcome`）写入 RAG。
- `new_impacts` 里每个新影响派生节点并按 `delay_ticks` 重新登记到 TickBus
  —— 蝴蝶效应由此持续发酵。

**循环与停止**

`WorldTickWorkflow` 驱动：`for _ in range(max_ticks): bus.advance() ...`。
跑满 `max_ticks` 或事件队列清空即停止。每个 tick 的事件、outcome、新影响
都留有结构化记录，可回放、可审计。

**v0 故意推后**：真语义 embedding（先用 metadata 路由）、DAG 生成管线、
常驻 Runtime Entity Agent、语义缓存、熔断。

### 16.2 Tick Loop v1（节点连续性与相关性检索）

v0 跑通后的第一次打磨。两处耦合改动，让世界从"一格一格独立反应"变成
"持续演化"。

**节点跨 tick 连续性**

每次节点回合提交后，`WorldTickWorkflow` 把 outcome 写回节点自身：

- `node.last_tick` 更新为当前 tick。
- `node.metadata["recent_narratives"]`：追加本次叙事，按 `history_window`
  截取最近 N 条（默认 3）。
- `node.metadata["change_log"]`：追加本次 `proposed_changes` 的 summary，
  截取最近 2N 条。

节点再次被唤醒时，自己的近期历史会以 `node.model_dump()` 的形式直接进入 prompt
context —— 不依赖 RAG 检索能不能命中。这是节点级"自我延续"的最简实现，
仍然满足铁律 2（agent 提议、core 提交）。

**相关性检索**

v0 把 `world_seed_id` 下所有 fragment 全量倒给节点。v1 改成两段拼接：

- **Canon 段**（始终带）：`metadata_filter={"kind": "world_law", "world_seed_id": ...}`
  拿到所有世界法则。法则是世界的不变约束，每次推演都要看见。
- **相关性段**（top_k 排序）：用 `node.node_type / node.id / event.event_type /
  payload.target_hint / payload.impact_summary` 拼成 query，按 `retrieval_top_k`
  （默认 6）取相关 fragment。

两段按 fragment id 去重后给到 prompt。即使在词面 embedding 下，非空 query 也能
按词重叠产出合理排序；接入真语义 embedding 后只需替换 repository 实现，workflow
不变。

**仍然推后到下一里程碑**：真语义 embedding、按节点维度的细粒度路由（例如
"只看该节点自身历史"）、节点状态的结构化更新（当前只追加叙事文本）。

## 17. 动态 Runtime Entity Agent

Runtime Entity Agent 不是常驻进程，而是需要时临时组装的 prompt。

Prompt 组装顺序：

```text
system persona
+ RAG retrieves: long-term memory and world knowledge
+ current state or tick context
+ user input or incoming event
```

交互流水线：

```text
user input
-> retrieve relevant memories
-> assemble prompt
-> run agent with response schema
-> return response to player
-> summarize new event
-> curator decides what enters RAG
```

这样可以让实体拥有连续性，同时不需要让每个实体长期运行。

## 18. MVP 开发路线图

### Phase 1：Provider 与校验底座

第一步具体应该先写：

```text
src/core/llm_gateway.py
class LLMGateway
```

原因：

整个 multi-agent 系统依赖稳定的 Schema 约束 LLM 调用。如果这一层不稳定，Debate、Guard、Curator、Causality 都会不可靠。

实现目标：

- OpenAI 兼容 request builder。
- 默认模型 `mimo-v2.5-pro`。
- 支持 per-request `ThinkingPolicy`。
- 开启 thinking 时自动应用最小 token 预算。
- Schema 修复重试时自动使用 `thinking: disabled`。
- API key 从环境变量读取。
- `complete()`。
- `complete_and_parse()`。
- JSON 提取。
- Pydantic 校验失败自动重试。

### Phase 2：Agent Runtime 骨架

文件：

```text
src/core/agents/schemas.py
src/core/agents/runtime.py
```

类：

```text
AgentProfile
AgentTask
AgentRunResult
ProposedChange
AgentRuntime
```

### Phase 3：世界初始化 Schema

文件：

```text
src/game/world_init/schemas.py
```

类：

```text
PlayerWorldAnswer
WorldLaw
WorldSeedCandidate
WorldSeed
CausalImpactPacket
```

### Phase 4：Debate Workflow

文件：

```text
src/game/world_init/workflow.py
```

实现：

```text
player answer
-> expander
-> critic
-> drama designer
-> synthesizer
-> canon guard
```

### Phase 5：RAG 持久化

文件：

```text
src/core/rag_repository.py
```

实现：

```text
UniversalRAGRepository.upsert()
UniversalRAGRepository.hybrid_search()
```

随后将 Memory Curator 接入 Chroma。

### Phase 6：首个端到端脚本

文件：

```text
src/main.py
```

行为：

```text
ask one question
read player answer
run world-init workflow
print accepted world seed
write world seed and causal packet to Chroma
print fragment IDs
```

### Phase 7：Tick Loop v0

文件：

```text
src/core/tick_bus.py
src/game/world_sim/schemas.py
src/game/world_sim/agents.py
src/game/world_sim/prompts.py
src/game/world_sim/memory.py
src/game/world_sim/tick_workflow.py
```

实现：

```text
world-init causal packet
-> bootstrap nodes + scheduled events
-> tick loop: advance -> wake node -> reason -> validate -> commit
-> new impacts rescheduled
-> stop at max_ticks or empty queue
```

详细实现计划见 `docs/superpowers/plans/2026-05-22-tick-loop-v0-plan.md`。

## 19. 测试策略

单元测试：

- Pydantic Schema 校验。
- LLM 输出 JSON 提取。
- 使用 mock provider 测试 LLM Gateway 重试逻辑。
- Agent Runtime message 组装。
- Guard decision 处理。
- 使用临时 Chroma 目录测试 RAG upsert/search。

集成测试：

```text
given a fixed player answer
when the world-init workflow runs with a fake LLM provider
then it returns a valid WorldSeed
and writes at least one world_seed fragment to RAG
and writes one causal impact packet fragment to RAG
```

Live provider smoke test：

- 只手动运行或 opt-in 运行。
- 需要环境变量提供 API key。
- 只发送一次极小 chat completion。
- 不进入普通 CI。
- 默认使用 `thinking: disabled` 控制成本和短输出稳定性。

## 20. MVP 验收标准

MVP 完成条件：

1. 玩家可以回答一个初始化问题。
2. 多个 Agent 产出经过校验的结构化 debate artifact。
3. Synthesizer 生成合法 `WorldSeedCandidate`。
4. Canon Guard 接受或修正为合法 `WorldSeed`。
5. Memory Curator 将被接受事实写入 Chroma。
6. Causality Analyzer 写入一个合法 `CausalImpactPacket`。
7. 全流程可在 2020 MacBook Pro M1 本地运行。
8. 仓库中没有 API key 或供应商密钥。
9. 关键推理任务能显式开启 thinking，普通高频任务能显式关闭 thinking。

## 21. 已定设计决策

1. 使用 supervised multi-agent，不使用自由运行的 Agent 群。
2. Pydantic 是唯一结构化输出契约。
3. MVP 使用 Chroma 持久化 RAG。
4. MVP RAG 使用确定性 `hashed_text_embedding`（词面散列，非学习模型）；
   真语义 embedding（MiniLM 或 provider embedding 接口）与语义缓存推后。
5. LLM 调用使用 OpenAI 兼容 chat completion。
6. 当前 live model ID 使用 `mimo-v2.5-pro`。
7. 第一闭环不实现完整 Runtime Entity Agent，只保留接口方向。
8. Causality 用延迟影响包表达，不直接修改世界状态。
9. Thinking 使用按任务配置的 `ThinkingPolicy`，关键推理开启，高频任务关闭。
