"""Explicit embedding providers: offline lexical hashing or Gemini semantics."""
from hashlib import sha256
import logging

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import Settings
from src.errors import ServiceError
from src.quotas import GOVERNOR, input_units

logger = logging.getLogger(__name__)


class TransientAPIError(Exception):
    pass


def remote_call(operation):
    # Log only the category, never provider messages (which may contain secrets/text).
    try:
        return operation()
    except ServiceError:
        raise
    except Exception as exc:
        transient = False
        codes = set()
        cause = exc
        # LangChain may wrap a Google SDK error; inspect codes, never its message.
        for _ in range(5):
            if cause is None:
                break
            name = type(cause).__name__
            code = getattr(cause, 'status_code', getattr(cause, 'code', None))
            if isinstance(code, int):
                codes.add(code)
            if name in {'ResourceExhausted', 'ServiceUnavailable', 'DeadlineExceeded',
                        'TooManyRequests', 'TimeoutError', 'ReadTimeout', 'ConnectTimeout'} \
                    or code in {429, 500, 502, 503, 504}:
                transient = True
            cause = cause.__cause__
        if transient:
            logger.warning('Remote service temporarily unavailable')
            raise TransientAPIError() from None
        if 404 in codes:
            raise ServiceError('Configured Gemini model is unavailable or inaccessible. Check the model name and API access.') from None
        if codes & {401, 403}:
            raise ServiceError('Gemini authentication or permission was denied. Check the secure API key and project access.') from None
        raise ServiceError('AI request failed. Check API access, model settings, and quota.') from None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=4),
       retry=retry_if_exception_type(TransientAPIError), reraise=True)
def retry_remote(operation):
    return remote_call(operation)


def call_ai(operation, *, settings=None, tokens=0):
    def admitted():
        if settings is None:  # Pure transport utility; real adapters always pass settings.
            return operation()
        with GOVERNOR.reserve(settings, tokens):
            return operation()
    try:
        return retry_remote(admitted)
    except TransientAPIError:
        raise ServiceError('AI service is busy or rate limited. Please retry later.') from None


class LocalEmbeddings:
    """No downloads or keys. Lexical similarity, not learned semantic embeddings."""
    identity = 'local-hashing-word-bigram-768-v1'

    def __init__(self):
        self.vectorizer = HashingVectorizer(n_features=768, alternate_sign=False,
                                            ngram_range=(1, 2), norm='l2')

    def embed_documents(self, texts):
        return self.vectorizer.transform(texts).toarray().astype(float).tolist()

    def embed_query(self, text):
        return self.embed_documents([text])[0]


class GeminiEmbeddings:
    def __init__(self, settings: Settings):
        if not settings.api_key:
            raise ServiceError('GOOGLE_API_KEY is required for Gemini embeddings.')
        from google import genai
        from google.genai import types
        self.settings = settings
        # Explicit single-attempt SDK calls: every retry is admitted/accounted above.
        self.client = genai.Client(api_key=settings.api_key, vertexai=False,
            http_options=types.HttpOptions(timeout=45000,
                retry_options=types.HttpRetryOptions(attempts=1)))
        self.identity = 'gemini-' + sha256(settings.embedding_model.encode()).hexdigest()[:16]

    def close(self):
        self.client.close()

    def _embed(self, texts, task):
        from google.genai import types
        units = sum(input_units(text) for text in texts)
        if units > self.settings.gemini_max_input_tokens:
            raise ServiceError('Embedding input exceeds the configured token allowance.')
        # Explicit small batches keep one admitted attempt per provider HTTP request.
        result = call_ai(lambda: self.client.models.embed_content(
            model=self.settings.embedding_model,
            contents=[{"parts": [{"text": text}]} for text in texts],
            config=types.EmbedContentConfig(task_type=task, output_dimensionality=768)),
            settings=self.settings, tokens=units)
        if len(result.embeddings or []) != len(texts):
            raise ServiceError('Embedding service returned an invalid batch.')
        return [list(item.values) for item in result.embeddings]

    def embed_documents(self, texts):
        batches, batch, units = [], [], 0
        for text in texts:
            size = input_units(text)
            if batch and (len(batch) >= 8 or units + size > self.settings.gemini_max_input_tokens):
                batches.append(batch)
                batch, units = [], 0
            batch.append(text)
            units += size
        if batch:
            batches.append(batch)
        vectors = []
        for batch in batches:
            vectors.extend(self._embed(batch, 'RETRIEVAL_DOCUMENT'))
        return self._normalize(vectors)

    def embed_query(self, text):
        return self._normalize(self._embed([text], 'RETRIEVAL_QUERY'))[0]

    @staticmethod
    def _normalize(vectors):
        array = np.asarray(vectors, dtype=float)
        norms = np.linalg.norm(array, axis=1, keepdims=True)
        if not np.isfinite(array).all() or (norms == 0).any():
            raise ServiceError('Embedding service returned invalid vectors.')
        return (array / norms).tolist()
