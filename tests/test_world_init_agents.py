from game.world_init.agents import (
    build_causality_analyzer_profile,
    build_canon_guard_profile,
    build_debate_profiles,
    build_synthesizer_profile,
)


def test_debate_profiles_enable_thinking_for_core_world_building():
    profiles = build_debate_profiles()

    assert [profile.id for profile in profiles] == ["expander", "critic", "drama_designer"]
    assert all(profile.thinking.type == "enabled" for profile in profiles)
    assert all(profile.max_tokens == 4096 for profile in profiles)


def test_synthesizer_guard_and_causality_profiles_enable_thinking():
    profiles = [
        build_synthesizer_profile(),
        build_canon_guard_profile(),
        build_causality_analyzer_profile(),
    ]

    assert [profile.id for profile in profiles] == ["synthesizer", "canon_guard", "causality_analyzer"]
    assert all(profile.thinking.type == "enabled" for profile in profiles)
    assert all("JSON" in " ".join(profile.style_rules) for profile in profiles)

