"""Spec §7.A 一致性失败分类集成测试。

每个测试模拟一类一致性失败:WorldMemory 中预存"事实",NarrativeAgent 生成
违反该事实的提案,Guard 收到完整 references(含事实 + recent turns)→ reject
→ TurnLoop 降级。验证 references 装配正确 + 降级路径正确。

不验 Guard 真实推理能力(用 FakeStructuredGateway 编排 reject)— 那留 Phase D
live smoke。

## 中文 fixture 加空格的说明(workaround)

stored memory 与 query 中的长中文短语刻意加了空格(如 "魔法 需 血液 代价"
而非 "魔法需血液代价")。原因:`InMemoryRAGRepository._terms()` 用
`re.findall(r"[\\w]+", text.lower())` tokenize,连续中文被识别为单个
token,空格分词的 query 与无空格的 stored content 无 token overlap,
cosine score = 0 → references 为空 → 测试假阴性 FAIL。

⚠ Phase D 切到 ChromaRAGRepository **不会自动解决**这个问题 —
ChromaRAG 的 hashed_text_embedding() 内部也调 _terms(),同一 tokenize
缺陷会随到 Phase D。Phase D contract 文档(extending-the-engine.md)
会加显式警告。彻底解法是引入 jieba 或真实 embedding model,
Phase D / E 处理。

## 断言信号设计

每个测试的断言 substring 都刻意选**只在 stored memory 出现、不在
narration / proposal 出现的词**,确保测试真正验证 "references 注入"
路径,而不是被 proposal payload 中相同词汇假阳性满足。例如 test 3
narration 用 "崭新的钥匙",断言用 "黄铜" / "持有"(只在 stored memory
出现)。
"""

from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from core.agents.guard import ConsistencyGuard, GuardDecision, GuardFinding
from core.agents.narrative import NarrativeAgent
from core.agents.runtime import AgentRuntime
from core.agents.schemas import AgentProfile
from core.rag_repository import InMemoryRAGRepository
from core.turn_loop import TurnLoop, TurnLoopConfig
from core.turn_store import TurnStore
from core.world_memory import MemoryRecord, WorldMemory
from tests._fakes import FakeStructuredGateway


class _Beat(BaseModel):
    narration: str = Field(min_length=1)
    new_facts: list[str] = Field(default_factory=list)


def _build_loop(
    *,
    gateway: FakeStructuredGateway,
    tmp_path: Path,
    retrieval_kinds: list[str],
) -> tuple[TurnLoop, WorldMemory]:
    """构造完整 TurnLoop + WorldMemory,统一配 priority_kinds = retrieval_kinds。"""
    runtime = AgentRuntime(gateway=gateway)
    narrative = NarrativeAgent(
        runtime=runtime,
        profile=AgentProfile(id="n", name="N", role="narrator", objective="o"),
    )
    guard = ConsistencyGuard(
        runtime=runtime,
        profile=AgentProfile(id="g", name="G", role="guard", objective="o"),
    )
    wm = WorldMemory(repository=InMemoryRAGRepository())
    store = TurnStore(data_dir=tmp_path)
    loop = TurnLoop(
        narrative_agent=narrative,
        guard=guard,
        world_memory=wm,
        turn_store=store,
        config=TurnLoopConfig(
            narrative_output_schema=_Beat,
            response_text_field="narration",
            retrieval_kinds=retrieval_kinds,
            references_priority_kinds=retrieval_kinds,
            guard_rules=[],
        ),
    )
    return loop, wm


@pytest.mark.asyncio
async def test_consistency_failure_world_law_violation(tmp_path: Path):
    """spec §7.A 法则违反:world_law 中 '魔法 需 血液 代价',narrative 让 NPC 免费施法。

    注:存储内容刻意用空格分隔(玩家面前是检索/匹配体系实现细节),让
    InMemoryRAGRepository 的 cosine-on-terms 评分能命中 query 共享词。
    """
    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="NPC Alice 凭空施放火球术,毫无代价。"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(
                severity="error",
                message="violates world_law: 魔法需血液代价",
            )],
        ),
    )

    loop, wm = _build_loop(gateway=gateway, tmp_path=tmp_path, retrieval_kinds=["world_law"])
    wm.upsert(MemoryRecord(
        kind="world_law", content="魔法 需 血液 代价,无血 则 无法 施法",
        source="seed", session_id="sess_law",
    ))

    result = await loop.run_turn(session_id="sess_law", raw_text="让 Alice 施展 魔法 火球")

    assert result.turn.status == "degraded"
    guard_msg = gateway.invocations[1].messages[1]
    assert "血液" in guard_msg.content and "代价" in guard_msg.content
    assert "world_law" in str(result.turn.metadata.get("guard_rejection", {}))


@pytest.mark.asyncio
async def test_consistency_failure_event_contradicts_past(tmp_path: Path):
    """spec §7.A 事实矛盾:event 中 '国王 Aldric 已 暗杀',narrative 让他出场。"""
    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="国王 Aldric 走进大殿,向你示意。"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(severity="error", message="contradicts event: 国王 Aldric 已死")],
        ),
    )

    loop, wm = _build_loop(gateway=gateway, tmp_path=tmp_path, retrieval_kinds=["event"])
    wm.upsert(MemoryRecord(
        kind="event", content="国王 Aldric 在 turn 3 被 暗杀 身亡",
        source="turn:3", session_id="sess_event",
    ))

    result = await loop.run_turn(session_id="sess_event", raw_text="进入王宫 寻找 Aldric")

    assert result.turn.status == "degraded"
    guard_msg = gateway.invocations[1].messages[1]
    assert "Aldric" in guard_msg.content
    assert "暗杀" in guard_msg.content or "身亡" in guard_msg.content


@pytest.mark.asyncio
async def test_consistency_failure_player_state_forgotten(tmp_path: Path):
    """spec §7.A 状态遗忘:player_state 中 '玩家 持有 黄铜 钥匙',narrative 让玩家再找。"""
    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="你在地上发现了一把崭新的钥匙,捡起。"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(severity="error", message="player_state forgotten: 玩家已持有黄铜钥匙")],
        ),
    )

    loop, wm = _build_loop(gateway=gateway, tmp_path=tmp_path, retrieval_kinds=["player_state"])
    wm.upsert(MemoryRecord(
        kind="player_state", content="玩家 持有 黄铜 钥匙 turn 2 获得",
        source="turn:2", session_id="sess_state",
    ))

    result = await loop.run_turn(session_id="sess_state", raw_text="在房间 搜索 钥匙")

    assert result.turn.status == "degraded"
    guard_msg = gateway.invocations[1].messages[1]
    # 必须由 references 引入(而非 narration),所以验证特征性词组
    assert "黄铜" in guard_msg.content
    assert "持有" in guard_msg.content


@pytest.mark.asyncio
async def test_consistency_failure_location_jump(tmp_path: Path):
    """spec §7.A 时空错乱:上轮在森林,本轮 narrative 让玩家瞬间在酒馆。
    通过 recent_turns 引入位置信息(简化:rely on recent_turn 摘要)。"""
    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="你站在森林深处,四周是高大的橡树。"))
    gateway.queue_response(GuardDecision, GuardDecision(decision="accept", findings=[]))
    gateway.queue_response(_Beat, _Beat(narration="你坐在酒馆吧台前,要了一杯麦酒。"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(
                severity="error",
                message="location jump: 上轮森林,本轮酒馆,无移动叙事",
            )],
        ),
    )

    loop, wm = _build_loop(gateway=gateway, tmp_path=tmp_path, retrieval_kinds=[])

    r0 = await loop.run_turn(session_id="sess_loc", raw_text="环顾四周")
    assert r0.turn.status == "ok"

    r1 = await loop.run_turn(session_id="sess_loc", raw_text="说点什么")
    assert r1.turn.status == "degraded"
    second_guard_msg = gateway.invocations[3].messages[1]
    assert "森林" in second_guard_msg.content


@pytest.mark.asyncio
async def test_consistency_failure_choice_without_consequence(tmp_path: Path):
    """spec §7.A 选择无后果:event 中 '玩家 击杀 NPC Bob',本轮 narrative 让 Bob 出场。"""
    gateway = FakeStructuredGateway()
    gateway.queue_response(_Beat, _Beat(narration="NPC Bob 笑着走过来跟你打招呼。"))
    gateway.queue_response(
        GuardDecision,
        GuardDecision(
            decision="reject",
            findings=[GuardFinding(severity="error", message="choice consequence ignored: Bob 已死")],
        ),
    )

    loop, wm = _build_loop(gateway=gateway, tmp_path=tmp_path, retrieval_kinds=["event"])
    wm.upsert(MemoryRecord(
        kind="event", content="玩家 在 turn 5 击杀 了 NPC Bob",
        source="turn:5", session_id="sess_choice",
    ))

    result = await loop.run_turn(session_id="sess_choice", raw_text="走进酒馆 找 Bob 喝酒")

    assert result.turn.status == "degraded"
    guard_msg = gateway.invocations[1].messages[1]
    assert "Bob" in guard_msg.content
    assert "击杀" in guard_msg.content
