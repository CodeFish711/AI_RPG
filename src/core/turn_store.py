from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from core._validators import is_valid_session_id, validate_session_id
from core.agents.guard import GuardDecision
from core.schemas import RAGQueryResult, TurnInput
from core.world_memory import MemoryRecord


class Turn(BaseModel):
    """一次完整闭环的快照,可序列化存盘。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    input: TurnInput
    retrieved_memory: list[RAGQueryResult] = Field(default_factory=list)
    narrative_draft: dict[str, Any] | None = None
    guard_decision: GuardDecision | None = None
    curated_records: list[MemoryRecord] = Field(default_factory=list)
    response_text: str | None = None
    status: Literal["ok", "degraded", "failed"] = "ok"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TurnResult(BaseModel):
    """TurnLoop.run_turn 的返回值。turn 是整轮快照,response_text 是给玩家看的文本。"""

    turn: Turn
    response_text: str = Field(min_length=1)
    guard_retries: int = Field(default=0, ge=0)


class TurnStore:
    """把 Turn 序列化为 JSONL,每 session 一个文件:<data_dir>/<session_id>.jsonl。"""

    def __init__(self, *, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save(self, turn: Turn) -> None:
        # turn.input.session_id 已被 Pydantic 校验过 pattern
        path = self._path_for(turn.input.session_id)
        line = turn.model_dump_json()
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load_session(self, *, session_id: str) -> list[Turn]:
        validate_session_id(session_id)
        path = self._path_for(session_id)
        if not path.exists():
            return []
        turns: list[Turn] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            turns.append(Turn.model_validate_json(line))
        return turns

    def load_recent(self, *, session_id: str, n: int) -> list[Turn]:
        validate_session_id(session_id)
        if n <= 0:
            return []
        all_turns = self.load_session(session_id=session_id)
        return all_turns[-n:]

    def list_sessions(self) -> list[str]:
        """返回 data_dir 下所有 jsonl session_id,按 mtime 倒序(最新优先)。
        忽略非 jsonl 文件(.DS_Store / .md / .txt 等)。"""
        jsonl_files = [p for p in self.data_dir.iterdir() if p.is_file() and p.suffix == ".jsonl"]
        jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.stem for p in jsonl_files]

    def _path_for(self, session_id: str) -> Path:
        # 内部不变量:_path_for 是私有的,假定调用方已校验。用 RuntimeError 而非 assert,
        # 保证 python -O 下仍触发(assert 在 -O 时被 strip)。
        if not is_valid_session_id(session_id):
            raise RuntimeError(f"_path_for: invalid session_id {session_id!r}")
        return self.data_dir / f"{session_id}.jsonl"
