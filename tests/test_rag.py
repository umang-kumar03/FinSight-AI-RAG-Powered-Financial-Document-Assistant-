from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.config import Settings
from src.embeddings import GeminiEmbeddings, LocalEmbeddings, call_ai
from src.errors import ServiceError, ValidationError
from src.evaluation import evaluate_retrieval
from src.rag import RAGService


@pytest.fixture
def service(tmp_path, samples):
    service = RAGService(tmp_path / 'chroma')
    for name in ['annual_report.pdf', 'risk_note.pdf']:
        service.ingest((samples / name).read_bytes(), name)
    return service


def test_ingest_search_citations_and_idempotence(service, sample_pdf):
    count = service.collection.count()
    service.ingest(sample_pdf, 'annual_report.pdf')
    assert service.collection.count() == count
    answer = service.answer('What was revenue in 2025?')
    assert '1500' in answer.text and '[S1]' in answer.text
    assert answer.sources[0].source == 'annual_report.pdf'
    assert answer.sources[0].page == 1
    assert answer.mode == 'offline'


def test_multi_doc_filter_delete(service):
    docs = service.documents()
    risk = next(d for d in docs if d['name'] == 'risk_note.pdf')
    sources = service.search('liquidity risk', document_id=risk['id'])
    assert sources and all(s.source == 'risk_note.pdf' for s in sources)
    service.delete_document(risk['id'])
    assert len(service.documents()) == 1
    assert not service.search('liquidity risk', document_id=risk['id'])


def test_persistence_and_isolation(tmp_path, sample_pdf):
    first = RAGService(tmp_path / 'one')
    first.ingest(sample_pdf, 'a.pdf')
    assert len(RAGService(tmp_path / 'one').documents()) == 1
    assert not RAGService(tmp_path / 'two').documents()


def test_empty_and_unrelated(service, tmp_path):
    assert not RAGService(tmp_path / 'empty').answer('revenue?').sources
    assert not service.answer('zyxwvuquuxnebula').sources
    with pytest.raises(ValidationError): service.search('')
    with pytest.raises(ValidationError): service.search('x' * 2001)
    with pytest.raises(ValidationError): service.search('x', k=20)


def test_mocked_gemini_receives_context_and_history(service):
    class FakeLLM:
        def invoke(self, messages):
            assert 'untrusted' in messages[0][1]
            assert '1500' in messages[1][1]
            assert 'earlier question' in messages[1][1]
            return SimpleNamespace(content='Revenue was 1500 [S1].')
    answer = service.answer('revenue in 2025', mode='gemini', llm=FakeLLM(),
                             history=[{'role': 'user', 'content': 'earlier question'}])
    assert answer.text == 'Revenue was 1500 [S1].'
    assert answer.sources[0].page == 1


@pytest.mark.parametrize('text', ['', None, 'No citations', 'Revenue [S99]'])
def test_model_citations_validated(service, text):
    class FakeLLM:
        def invoke(self, messages): return SimpleNamespace(content=text)
    with pytest.raises(ServiceError):
        service.answer('revenue', mode='gemini', llm=FakeLLM())


def test_missing_key(service):
    with pytest.raises(ServiceError, match='GOOGLE_API_KEY'):
        service.answer('revenue', mode='gemini')
    with pytest.raises(ServiceError): GeminiEmbeddings(Settings())


def test_api_failure_sanitized(caplog):
    def bad(): raise ValueError('secret-key-private-document')
    with pytest.raises(ServiceError) as error:
        call_ai(bad)
    assert 'secret-key' not in str(error.value) + caplog.text


def test_rate_limit_retries():
    class ResourceExhausted(Exception): pass
    calls = []
    def operation():
        calls.append(1)
        if len(calls) < 3: raise ResourceExhausted('private')
        return 'ok'
    with patch('tenacity.nap.time.sleep'):
        assert call_ai(operation) == 'ok'
    assert len(calls) == 3


def test_retrieval_evaluation(service):
    report = evaluate_retrieval(service, [{'query': 'liquidity risk',
        'relevant': [{'source': 'risk_note.pdf', 'page': 1}]}], k=2)
    assert report['cases'] == 1
    assert report['mean_recall_at_k'] == 1
    assert report['mean_reciprocal_rank'] == 1
    with pytest.raises(ValidationError): evaluate_retrieval(service, [])


def test_document_limit(tmp_path, samples):
    service = RAGService(tmp_path / 'limited', settings=Settings(max_documents=1))
    service.ingest((samples / 'annual_report.pdf').read_bytes(), 'a.pdf')
    with pytest.raises(ValidationError, match='full'):
        service.ingest((samples / 'risk_note.pdf').read_bytes(), 'b.pdf')


def test_embedding_providers():
    provider = LocalEmbeddings()
    vectors = provider.embed_documents(['revenue profit', 'currency risk'])
    assert len(vectors) == 2 and len(vectors[0]) == 768
    assert provider.embed_query('revenue profit') == vectors[0]
    normalized = GeminiEmbeddings._normalize([[3.0, 4.0]])
    assert normalized[0] == pytest.approx([.6, .8])


def test_embedding_adapter_with_mocked_transport(monkeypatch):
    captured = {}
    class FakeEmbeddingClient:
        def __init__(self, **kwargs): captured.update(kwargs)
        def embed_documents(self, texts): return [[3., 4.] for _ in texts]
        def embed_query(self, text): return [3., 4.]
    monkeypatch.setattr('langchain_google_genai.GoogleGenerativeAIEmbeddings', FakeEmbeddingClient)
    provider = GeminiEmbeddings(Settings(api_key='unit-test-key'))
    assert provider.embed_documents(['example'])[0] == pytest.approx([.6, .8])
    assert provider.embed_query('example') == pytest.approx([.6, .8])
    assert captured['vertexai'] is False
    assert captured['output_dimensionality'] == 768
    with pytest.raises(ServiceError): GeminiEmbeddings._normalize([[0., 0.]])


def test_wrapped_rate_limit_and_exhaustion(caplog):
    class APIError(Exception): code = 429
    def operation():
        try: raise APIError('secret')
        except APIError as cause: raise RuntimeError('private provider message') from cause
    with patch('tenacity.nap.time.sleep'):
        with pytest.raises(ServiceError, match='rate limited'):
            call_ai(operation)
    assert 'secret' not in caplog.text and 'private provider' not in caplog.text


def test_partial_index_rolls_back(tmp_path, sample_pdf):
    service = RAGService(tmp_path / 'rollback')
    with patch.object(type(service.collection), 'upsert', side_effect=RuntimeError('db error')):
        with pytest.raises(ServiceError, match='partial index'):
            service.ingest(sample_pdf, 'annual_report.pdf')
    assert service.collection.count() == 0


def test_chunk_limit(tmp_path, sample_pdf):
    service = RAGService(tmp_path / 'chunks', settings=Settings(max_chunks=0))
    with pytest.raises(ValidationError, match='Chunk storage limit'):
        service.ingest(sample_pdf, 'annual_report.pdf')


def test_invalid_mode_and_empty_evaluation_labels(service):
    with pytest.raises(ValidationError): service.answer('revenue', mode='unknown')
    with pytest.raises(ValidationError):
        evaluate_retrieval(service, [{'query': 'revenue', 'relevant': []}])


@pytest.mark.parametrize('code,message', [(404, 'model is unavailable'), (403, 'permission was denied')])
def test_api_model_and_permission_errors_are_actionable(code, message):
    class APIError(Exception):
        status_code = code
    def operation():
        raise APIError('sensitive-provider-payload')
    with pytest.raises(ServiceError, match=message) as error:
        call_ai(operation)
    assert 'sensitive-provider-payload' not in str(error.value)


def test_citation_page_matches_actual_pdf_page(tmp_path):
    from io import BytesIO
    from reportlab.pdfgen import canvas
    data = BytesIO()
    pdf = canvas.Canvas(data)
    pdf.drawString(30, 700, '2024 fictional revenue was 800.')
    pdf.showPage()
    pdf.drawString(30, 700, '2025 fictional revenue was 1500.')
    pdf.save()
    with RAGService(tmp_path / 'pages') as service:
        service.ingest(data.getvalue(), 'two-pages.pdf')
        answer = service.answer('2025 revenue 1500')
        assert answer.sources[0].page == 2
        assert '1500' in answer.sources[0].text
        assert answer.sources[0].source == 'two-pages.pdf'


def test_embedding_collections_do_not_mix_documents(tmp_path, sample_pdf):
    class OtherProvider(LocalEmbeddings):
        identity = 'different-model-identity'
    with RAGService(tmp_path / 'shared', LocalEmbeddings()) as first, \
            RAGService(tmp_path / 'shared', OtherProvider()) as second:
        first.ingest(sample_pdf, 'only-first.pdf')
        assert first.documents()
        assert not second.documents()
        assert not second.search('revenue')
