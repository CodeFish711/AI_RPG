import pytest

from scripts.live_world_sim import build_parser, ensure_live_enabled
from scripts.live_world_init import DEFAULT_LIVE_ANSWER


def test_live_world_sim_parser_defaults_to_safe_non_live_mode():
    args = build_parser().parse_args([])

    assert args.live is False
    assert args.answer == DEFAULT_LIVE_ANSWER
    assert args.ticks == 4


def test_live_world_sim_requires_explicit_live_flag():
    args = build_parser().parse_args([])

    with pytest.raises(SystemExit, match="--live"):
        ensure_live_enabled(args)


def test_live_world_sim_accepts_explicit_live_flag_and_tick_override():
    args = build_parser().parse_args(["--live", "--ticks", "10"])

    assert args.ticks == 10
    ensure_live_enabled(args)
