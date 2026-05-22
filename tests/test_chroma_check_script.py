import pytest

pytest.importorskip("chromadb")

from scripts.check_chroma_repository import run_check


def test_check_chroma_repository_writes_reopens_and_searches(tmp_path):
    result = run_check(persist_dir=str(tmp_path))

    assert result["count"] == 1
    assert result["result_count"] == 1
    assert result["first_kind"] == "world_law"

