import pytest


def _make_curator():
    """构造 Curator + 同款 WorldMemory(测试时一起返回)。"""
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


def test_curator_drops_facts_in_pending_range_mvp():
    """0.5 ≤ confidence < 0.8 在 MVP 简化为丢弃(v2 实现 pending)。"""
    from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind

    curator, wm = _make_curator()
    beat = NarrativeBeat(
        narration="x",
        new_facts=[
            NewFact(kind=TextAdventureMemoryKind.EVENT, statement="中置信", confidence=0.7),
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
    # 预存一条(用已分词形式,这是 Curator 入库时也会做的)
    wm.upsert(MemoryRecord(
        kind="world_law", content="魔法 需 血液",
        source="seed", session_id="s",
    ))
    # 新 fact 与已存语义相似
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
    assert " " in records[0].content  # 入库内容已分词


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
    from core.world_memory import MemoryQuery
    from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind

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

    # 验证已入 WorldMemory(用 token 化的 query,jieba 会拆 "国王" / "被" / "刺")
    results = wm.query(MemoryQuery(query_text="国王 被 刺", session_id="s", top_k=5))
    assert len(results) >= 1


def test_curator_processes_multiple_facts_in_one_beat():
    """beat.new_facts 含多条 fact,Curator 应逐个处理,各自走四道闸。"""
    from game.text_adventure.schemas import NarrativeBeat, NewFact, TextAdventureMemoryKind

    curator, wm = _make_curator()
    beat = NarrativeBeat(
        narration="x",
        new_facts=[
            NewFact(kind=TextAdventureMemoryKind.EVENT, statement="高置信事件 A", confidence=0.9),
            NewFact(kind=TextAdventureMemoryKind.EVENT, statement="低置信事件 B", confidence=0.3),  # 丢
            NewFact(kind=TextAdventureMemoryKind.EVENT, statement="高置信事件 C", confidence=0.85),
        ],
    )
    records = curator.curate(beat=beat, session_id="s", turn_index=0)
    assert len(records) == 2  # 只 A 和 C 通过四道闸
