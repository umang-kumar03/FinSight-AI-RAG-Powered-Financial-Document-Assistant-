import pytest

from scripts.make_sample_data import make_samples


@pytest.fixture(scope='session')
def samples(tmp_path_factory):
    return make_samples(tmp_path_factory.mktemp('samples'))


@pytest.fixture
def sample_pdf(samples):
    return (samples / 'annual_report.pdf').read_bytes()
