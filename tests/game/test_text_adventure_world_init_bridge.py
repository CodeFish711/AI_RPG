

def test_world_seed_to_memory_records_extracts_laws():
    """WorldSeed.laws → MemoryRecord(kind=world_law) 各一条。"""
    from game.text_adventure.world_init_bridge import world_seed_to_memory_records
    from game.world_init.schemas import WorldLaw, WorldSeed

    seed = WorldSeed(
        premise="魔法世界",
        laws=[
            WorldLaw(name="血液代价", statement="施法必须流血"),
            WorldLaw(name="神的禁忌", statement="不可呼唤死神之名"),
        ],
        tensions=["凡人想破解禁忌"],
    )
    records = world_seed_to_memory_records(seed=seed, session_id="s")

    law_records = [r for r in records if r.kind == "world_law"]
    assert len(law_records) == 2
    assert any("流血" in r.content or "血液" in r.content for r in law_records)


def test_world_seed_to_memory_records_extracts_tensions_as_events():
    """WorldSeed.tensions → MemoryRecord(kind=event)。"""
    from game.text_adventure.world_init_bridge import world_seed_to_memory_records
    from game.world_init.schemas import WorldSeed, WorldLaw

    seed = WorldSeed(
        premise="x",
        laws=[WorldLaw(name="x", statement="y")],
        tensions=["凡人想破解禁忌", "神想夺回控制权"],
    )
    records = world_seed_to_memory_records(seed=seed, session_id="s")

    event_records = [r for r in records if r.kind == "event"]
    assert len(event_records) == 2


def test_world_seed_to_memory_records_uses_correct_source_label():
    """source = 'world_init'。"""
    from game.text_adventure.world_init_bridge import world_seed_to_memory_records
    from game.world_init.schemas import WorldLaw, WorldSeed

    seed = WorldSeed(
        premise="x",
        laws=[WorldLaw(name="x", statement="y")],
        tensions=["t"],
    )
    records = world_seed_to_memory_records(seed=seed, session_id="s")
    assert all(r.source == "world_init" for r in records)


def test_world_seed_to_memory_records_tokenizes_chinese_content():
    """中文 content 应已分词。"""
    from game.text_adventure.world_init_bridge import world_seed_to_memory_records
    from game.world_init.schemas import WorldLaw, WorldSeed

    seed = WorldSeed(
        premise="x",
        laws=[WorldLaw(name="x", statement="施法必须流血代价")],
        tensions=["凡人破解禁忌"],
    )
    records = world_seed_to_memory_records(seed=seed, session_id="s")
    assert " " in records[0].content
