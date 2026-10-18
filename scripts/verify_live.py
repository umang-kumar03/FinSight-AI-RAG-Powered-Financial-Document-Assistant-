"""Opt-in live Gemini check. Report statuses only, never secrets/provider payloads."""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import Settings
from src.embeddings import GeminiEmbeddings, call_ai
from src.rag import RAGService


def verify():
    settings = Settings.from_env()
    result = {'key_available': bool(settings.api_key), 'connection': 'not_run',
              'pdf_semantic_rag': 'not_run'}
    if not settings.api_key:
        result['blocker'] = 'GOOGLE_API_KEY is unavailable in the application process.'
        return result, 2
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model=settings.chat_model, google_api_key=settings.api_key,
                                     temperature=0, timeout=45, max_retries=0, vertexai=False)
        response = call_ai(lambda: llm.invoke('Reply with the single word OK.'))
        if not response.content:
            raise RuntimeError('Empty response')
        result['connection'] = 'passed'
        with tempfile.TemporaryDirectory(prefix='finsight-live-') as path:
            service = RAGService(path, GeminiEmbeddings(settings), settings)
            pdf = Path(__file__).resolve().parents[1] / 'data/samples/annual_report.pdf'
            service.ingest(pdf.read_bytes(), pdf.name)
            answer = service.answer('What was revenue in 2025?', mode='gemini', llm=llm)
            if not answer.sources or '1500' not in answer.text.replace(',', ''):
                raise RuntimeError('Answer did not satisfy fixture assertions')
            if not any(s.source == pdf.name and s.page == 1 for s in answer.sources):
                raise RuntimeError('Expected source page not retrieved')
        result['pdf_semantic_rag'] = 'passed'
        return result, 0
    except Exception:
        stage = 'connection' if result['connection'] != 'passed' else 'pdf_semantic_rag'
        result[stage] = 'failed'
        result['blocker'] = 'Live operation failed; check model access, quota, and secure configuration.'
        return result, 1


if __name__ == '__main__':
    result, exit_code = verify()
    output = json.dumps(result, indent=2) + '\n'
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(output)
    print(output, end='')
    raise SystemExit(exit_code)
