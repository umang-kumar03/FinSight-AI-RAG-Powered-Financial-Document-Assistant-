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


@pytest.mark.live
@pytest.mark.skipif(os.getenv('RUN_LIVE_GEMINI') != '1' or not LIVE_SETTINGS.api_key,
                    reason='Real Gemini credentials and RUN_LIVE_GEMINI=1 required')
def test_live_gemini_connection():
    from langchain_google_genai import ChatGoogleGenerativeAI
    from src.embeddings import call_ai
    settings = Settings.from_env()
    llm = ChatGoogleGenerativeAI(model=settings.chat_model, google_api_key=settings.api_key,
                                 temperature=0, timeout=45, max_retries=0, vertexai=False)
    response = call_ai(lambda: llm.invoke('Reply with the single word OK.'))
    assert response.content, 'Live provider returned an empty response.'
