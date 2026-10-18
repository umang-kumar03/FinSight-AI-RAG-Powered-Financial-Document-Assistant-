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
