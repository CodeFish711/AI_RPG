from scripts.smoke_mimo_gateway import build_smoke_requests


def test_smoke_script_builds_disabled_and_enabled_thinking_requests():
    disabled_request, enabled_request = build_smoke_requests()

    assert disabled_request.thinking.type == "disabled"
    assert disabled_request.max_tokens == 128
    assert enabled_request.thinking.type == "enabled"
    assert enabled_request.max_tokens == 1024

