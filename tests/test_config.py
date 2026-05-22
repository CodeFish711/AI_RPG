from core.config import AppSettings


def test_settings_load_mimo_provider_from_environment(monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "secret")
    monkeypatch.setenv("MIMO_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MIMO_MODEL", "mimo-test")

    settings = AppSettings()

    assert settings.mimo_api_key == "secret"
    assert settings.mimo_base_url == "https://example.test/v1"
    assert settings.mimo_model == "mimo-test"

