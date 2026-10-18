"""The opt-in live check must report missing access without leaking diagnostics."""
from scripts.verify_live import verify
from src.config import Settings


def test_missing_key_prevents_live_calls(monkeypatch):
    monkeypatch.setattr('scripts.verify_live.Settings.from_env', lambda: Settings())
    result, status = verify()
    assert status == 2
    assert result['connection'] == 'not_run'
    assert result['pdf_semantic_rag'] == 'not_run'
    assert result['key_available'] is False


def test_provider_failure_never_exposes_credentials(monkeypatch):
    secret = 'fixture-secret-that-must-not-appear'
    monkeypatch.setattr('scripts.verify_live.Settings.from_env', lambda: Settings(api_key=secret))
    def failing_client(**kwargs):
        raise ValueError(secret)
    monkeypatch.setattr('langchain_google_genai.ChatGoogleGenerativeAI', failing_client)
    result, status = verify()
    assert status == 1 and result['connection'] == 'failed'
    assert secret not in str(result)
