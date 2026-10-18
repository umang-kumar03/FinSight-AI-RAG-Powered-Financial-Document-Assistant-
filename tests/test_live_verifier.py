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
    result, status = verify(enabled=True)
    assert status == 1 and result['connection'] == 'failed'
    assert secret not in str(result)


def test_key_alone_never_enables_live_calls(monkeypatch):
    monkeypatch.setattr('scripts.verify_live.Settings.from_env', lambda: Settings(api_key='fixture-key'))
    result, status = verify(enabled=False)
    assert status == 3
    assert result['connection'] == 'not_run'
    assert result['model_availability'] == {'chat': 'not_run', 'embeddings': 'not_run'}


def test_opt_in_checks_configured_model_availability_before_answering(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    config = Settings(api_key='fixture-key', chat_model='gemini-3.8-flash')
    monkeypatch.setattr('scripts.verify_live.Settings.from_env', lambda: config)
    metadata = Mock()
    llm = SimpleNamespace(client=SimpleNamespace(models=SimpleNamespace(get=metadata)),
                          invoke=lambda _: SimpleNamespace(content='OK'))
    monkeypatch.setattr('langchain_google_genai.ChatGoogleGenerativeAI', lambda **_: llm)
    class FakeService:
        def __init__(self, *args): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ingest(self, *args): pass
        def answer(self, *args, **kwargs):
            return SimpleNamespace(text='Revenue 1500 [S1]', sources=[
                SimpleNamespace(source='annual_report.pdf', page=1)])
    monkeypatch.setattr('scripts.verify_live.GeminiEmbeddings', lambda _: object())
    monkeypatch.setattr('scripts.verify_live.RAGService', FakeService)
    result, status = verify(enabled=True)
    assert status == 0
    assert result['model_availability'] == {'chat': 'passed', 'embeddings': 'passed'}
    assert result['connection'] == 'passed' and result['pdf_semantic_rag'] == 'passed'
    assert metadata.call_args_list[0].kwargs['model'] == 'gemini-3.8-flash'
    assert metadata.call_args_list[1].kwargs['model'] == config.embedding_model


def test_unavailable_model_reports_failed_metadata_without_provider_payload(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr('scripts.verify_live.Settings.from_env', lambda: Settings(api_key='fixture-key'))
    class APIError(Exception):
        status_code = 404
    def unavailable(**kwargs):
        raise APIError('sensitive-provider-payload')
    llm = SimpleNamespace(client=SimpleNamespace(models=SimpleNamespace(get=unavailable)))
    monkeypatch.setattr('langchain_google_genai.ChatGoogleGenerativeAI', lambda **_: llm)
    result, status = verify(enabled=True)
    assert status == 1
    assert result['model_availability']['chat'] == 'failed'
    assert result['model_availability']['embeddings'] == 'not_run'
    assert result['connection'] == 'not_run'
    assert 'model is unavailable' in result['blocker']
    assert 'sensitive-provider-payload' not in str(result)
