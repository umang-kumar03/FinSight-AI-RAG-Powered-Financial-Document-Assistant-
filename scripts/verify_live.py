"""Opt-in live Gemini check. Report statuses only, never secrets/provider payloads."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import Settings
from src.embeddings import GeminiEmbeddings, call_ai
from src.rag import RAGService
from src.errors import ServiceError


def verify(enabled=None):
    settings = Settings.from_env()
    result = {'key_available': bool(settings.api_key), 'connection': 'not_run',
              'pdf_semantic_rag': 'not_run',
              'model_availability': {'chat': 'not_run', 'embeddings': 'not_run'}}
    if not settings.api_key:
        result['blocker'] = 'GOOGLE_API_KEY is unavailable in the application process.'
        return result, 2
    if enabled is None:
        enabled = os.getenv('RUN_LIVE_GEMINI') == '1'
    if not enabled:
        result['blocker'] = 'Live calls are disabled. Explicitly pass --live or set RUN_LIVE_GEMINI=1.'
        return result, 3
    active_model = None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model=settings.chat_model, google_api_key=settings.api_key,
                                     temperature=0, timeout=45, max_retries=0, vertexai=False)
        active_model = 'chat'
        call_ai(lambda: llm.client.models.get(model=settings.chat_model))
        result['model_availability']['chat'] = 'passed'
        active_model = 'embeddings'
        call_ai(lambda: llm.client.models.get(model=settings.embedding_model))
        result['model_availability']['embeddings'] = 'passed'
        active_model = None
        response = call_ai(lambda: llm.invoke('Reply with the single word OK.'))
        if not response.content:
            raise RuntimeError('Empty response')
        result['connection'] = 'passed'
        with tempfile.TemporaryDirectory(prefix='finsight-live-') as path, \
                RAGService(path, GeminiEmbeddings(settings), settings,
                           persistent=sys.platform != 'win32') as service:
            pdf = Path(__file__).resolve().parents[1] / 'data/samples/annual_report.pdf'
            service.ingest(pdf.read_bytes(), pdf.name)
            answer = service.answer('What was revenue in 2025?', mode='gemini', llm=llm)
            if not answer.sources or '1500' not in answer.text.replace(',', ''):
                raise RuntimeError('Answer did not satisfy fixture assertions')
            if not any(s.source == pdf.name and s.page == 1 for s in answer.sources):
                raise RuntimeError('Expected source page not retrieved')
        result['pdf_semantic_rag'] = 'passed'
        return result, 0
    except Exception as exc:
        stage = 'connection' if result['connection'] != 'passed' else 'pdf_semantic_rag'
        if active_model:
            result['model_availability'][active_model] = 'failed'
        else:
            result[stage] = 'failed'
        # ServiceError is our sanitized application boundary; never stringify foreign SDK errors.
        result['blocker'] = str(exc) if isinstance(exc, ServiceError) else (
            'Live operation failed; check model access, quota, and secure configuration.')
        return result, 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', help='Optional JSON status report path')
    parser.add_argument('--live', action='store_true', help='Explicitly enable real Gemini calls')
    args = parser.parse_args()
    result, exit_code = verify(enabled=args.live or os.getenv('RUN_LIVE_GEMINI') == '1')
    output = json.dumps(result, indent=2) + '\n'
    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
    print(output, end='')
    raise SystemExit(exit_code)
