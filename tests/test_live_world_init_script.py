import pytest

from scripts.live_world_init import DEFAULT_LIVE_ANSWER, build_parser, ensure_live_enabled


def test_live_world_init_parser_defaults_to_safe_non_live_mode():
    parser = build_parser()
    args = parser.parse_args([])

    assert args.live is False
    assert args.answer == DEFAULT_LIVE_ANSWER


def test_live_world_init_requires_explicit_live_flag():
    parser = build_parser()
    args = parser.parse_args([])

    with pytest.raises(SystemExit, match="--live"):
        ensure_live_enabled(args)


def test_live_world_init_accepts_explicit_live_flag():
    parser = build_parser()
    args = parser.parse_args(["--live", "--answer", "代价是失去一个名字。"])

    ensure_live_enabled(args)

