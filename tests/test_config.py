from src.config import Settings


def test_environment_key_not_in_repr(monkeypatch):
    monkeypatch.setenv('GOOGLE_API_KEY', 'do-not-print')
    config = Settings.from_env()
    assert config.api_key == 'do-not-print'
    assert 'do-not-print' not in repr(config)


def test_requested_gemini_model_is_environment_configurable(monkeypatch):
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.8-flash')
    monkeypatch.setenv('GEMINI_EMBEDDING_MODEL', 'models/custom-embedding')
    config = Settings.from_env()
    assert config.chat_model == 'gemini-3.8-flash'
    assert config.embedding_model == 'models/custom-embedding'


def test_budget_configuration_from_environment(monkeypatch):
    monkeypatch.setenv('GEMINI_ENABLED', 'false')
    monkeypatch.setenv('GEMINI_DAILY_TOKENS', '1000')
    monkeypatch.setenv('GEMINI_CONCURRENCY', '1')
    config = Settings.from_env()
    assert config.gemini_enabled is False
    assert config.gemini_daily_tokens == 1000
    assert config.gemini_concurrency == 1


def test_invalid_budget_configuration_fails_closed(monkeypatch):
    import pytest
    monkeypatch.setenv('GEMINI_DAILY_TOKENS', '-1')
    with pytest.raises(ValueError, match='nonnegative'):
        Settings.from_env()
