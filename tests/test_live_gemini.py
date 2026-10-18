"""Explicit opt-in real-provider integration; never counted as passed when skipped."""
import os

import pytest

from src.config import Settings
from src.embeddings import GeminiEmbeddings
from src.rag import RAGService


LIVE_SETTINGS = Settings.from_env()


@pytest.mark.live
@pytest.mark.skipif(os.getenv('RUN_LIVE_GEMINI') != '1' or not LIVE_SETTINGS.api_key,
                    reason='Real Gemini credentials and RUN_LIVE_GEMINI=1 required')
def test_live_semantic_rag(tmp_path, sample_pdf):
    settings = Settings.from_env()
    service = RAGService(tmp_path, GeminiEmbeddings(settings), settings)
    service.ingest(sample_pdf, 'annual_report.pdf')
    answer = service.answer('What was revenue in 2025?', mode='gemini')
    assert answer.sources
    assert '1500' in answer.text.replace(',', '') or '1,500' in answer.text
    assert '[S' in answer.text
