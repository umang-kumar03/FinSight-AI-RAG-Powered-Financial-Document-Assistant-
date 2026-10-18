import pytest

from scripts.make_sample_data import make_samples


@pytest.fixture(scope='session')
def samples(tmp_path_factory):
    return make_samples(tmp_path_factory.mktemp('samples'))


@pytest.fixture
def sample_pdf(samples):
    return (samples / 'annual_report.pdf').read_bytes()


@pytest.fixture(autouse=True)
def close_test_indexes(monkeypatch, request):
    # Test-created persistent clients must also release Windows file locks before tmp cleanup.
    from src.rag import RAGService
    original = RAGService.__init__
    def tracked_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        request.addfinalizer(self.close)
    monkeypatch.setattr(RAGService, '__init__', tracked_init)


@pytest.fixture(autouse=True)
def isolated_ai_governor(monkeypatch):
    # Each test gets a fresh production governor; assertions still exercise real admission.
    from src.quotas import QuotaGovernor
    governor = QuotaGovernor()
    monkeypatch.setattr('src.embeddings.GOVERNOR', governor)
    return governor
