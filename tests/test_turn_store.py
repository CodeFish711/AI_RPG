import json
from pathlib import Path

import pytest


def test_turn_minimal_payload_validates():
    from core.schemas import TurnInput
    from core.turn_store import Turn

    t = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="s1"))
    assert t.status == "ok"
    assert t.response_text is None
    assert t.id  # auto-generated


def test_turn_round_trip_json_with_guard_and_records():
    from core.agents.guard import GuardDecision
    from core.schemas import TurnInput
    from core.turn_store import Turn
    from core.world_memory import MemoryRecord

    original = Turn(
        input=TurnInput(raw_text="say hi", turn_index=2, session_id="s1"),
        narrative_draft={"narration": "hello"},
        guard_decision=GuardDecision(decision="accept", findings=[]),
        curated_records=[
            MemoryRecord(kind="event", content="player said hi", source="turn:2", session_id="s1")
        ],
        response_text="hello back",
        status="ok",
    )

    dumped = original.model_dump_json()
    restored = Turn.model_validate_json(dumped)

    assert restored.input.raw_text == "say hi"
    assert restored.input.turn_index == 2
    assert restored.guard_decision is not None
    assert restored.guard_decision.decision == "accept"
    assert len(restored.curated_records) == 1
    assert restored.curated_records[0].kind == "event"
    assert restored.response_text == "hello back"


def test_turn_store_save_appends_jsonl_line(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    turn = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="s1"))
    store.save(turn)

    session_file = tmp_path / "s1.jsonl"
    assert session_file.exists()
    lines = session_file.read_text().splitlines()
    assert len(lines) == 1
    decoded = json.loads(lines[0])
    assert decoded["input"]["raw_text"] == "x"


def test_turn_store_save_multiple_turns_appends_lines(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    for i in range(3):
        store.save(Turn(input=TurnInput(raw_text=f"x{i}", turn_index=i, session_id="s2")))

    session_file = tmp_path / "s2.jsonl"
    lines = session_file.read_text().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["input"]["turn_index"] == 0
    assert json.loads(lines[2])["input"]["turn_index"] == 2


def test_turn_store_load_recent_returns_last_n(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    for i in range(5):
        store.save(Turn(input=TurnInput(raw_text=f"x{i}", turn_index=i, session_id="s3")))

    recent = store.load_recent(session_id="s3", n=2)
    assert len(recent) == 2
    assert recent[0].input.turn_index == 3
    assert recent[1].input.turn_index == 4


def test_turn_store_load_recent_handles_missing_session(tmp_path: Path):
    from core.turn_store import TurnStore

    store = TurnStore(data_dir=tmp_path)
    assert store.load_recent(session_id="never", n=5) == []


def test_turn_store_load_session_returns_all_turns_in_order(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    for i in range(3):
        store.save(Turn(input=TurnInput(raw_text=f"x{i}", turn_index=i, session_id="s4")))

    all_turns = store.load_session(session_id="s4")
    assert len(all_turns) == 3
    assert [t.input.turn_index for t in all_turns] == [0, 1, 2]


def test_turn_result_holds_turn_reference():
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnResult

    turn = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="s1"))
    result = TurnResult(turn=turn, response_text="hello", guard_retries=0)
    assert result.turn.id == turn.id
    assert result.response_text == "hello"
    assert result.guard_retries == 0


def test_turn_result_defaults_guard_retries_to_zero():
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnResult

    turn = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="s1"))
    result = TurnResult(turn=turn, response_text="hi")
    assert result.guard_retries == 0


def test_turn_result_response_text_required_non_empty():
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnResult
    from pydantic import ValidationError

    turn = Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="s1"))
    with pytest.raises(ValidationError):
        TurnResult(turn=turn, response_text="")


def test_turn_store_save_rejects_invalid_session_id(tmp_path: Path):
    from core.turn_store import TurnStore

    store = TurnStore(data_dir=tmp_path)
    with pytest.raises(ValueError, match="invalid session_id"):
        store.load_session(session_id="../etc/passwd")
    with pytest.raises(ValueError, match="invalid session_id"):
        store.load_recent(session_id="a/b", n=5)


def test_turn_store_save_accepts_valid_session_id(tmp_path: Path):
    from core.schemas import TurnInput
    from core.turn_store import Turn, TurnStore

    store = TurnStore(data_dir=tmp_path)
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=0, session_id="abc_123")))
    store.save(Turn(input=TurnInput(raw_text="x", turn_index=1, session_id="abc-123")))
    assert (tmp_path / "abc_123.jsonl").exists()
    assert (tmp_path / "abc-123.jsonl").exists()
