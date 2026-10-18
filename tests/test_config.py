from src.config import Settings


def test_environment_key_not_in_repr(monkeypatch):
    monkeypatch.setenv('GOOGLE_API_KEY', 'do-not-print')
    config = Settings.from_env()
    assert config.api_key == 'do-not-print'
    assert 'do-not-print' not in repr(config)
