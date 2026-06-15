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
