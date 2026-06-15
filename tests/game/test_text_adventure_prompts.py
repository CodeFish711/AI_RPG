def test_narrative_instruction_mentions_narrative_beat_schema():
    from game.text_adventure.prompts import NARRATIVE_INSTRUCTION

    assert "NarrativeBeat" in NARRATIVE_INSTRUCTION
    assert "narration" in NARRATIVE_INSTRUCTION


def test_narrative_instruction_specifies_style_rules():
    from game.text_adventure.prompts import NARRATIVE_INSTRUCTION

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

    has_dead_rule = any("死" in r or "dead" in r.lower() for r in TEXT_ADVENTURE_GUARD_RULES)
    assert has_dead_rule
