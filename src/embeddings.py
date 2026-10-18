"""Explicit embedding providers: offline lexical hashing or Gemini semantics."""
from hashlib import sha256
import logging

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import Settings
from src.errors import ServiceError

logger = logging.getLogger(__name__)


class TransientAPIError(Exception):
    pass


def remote_call(operation):
    # Log only the category, never provider messages (which may contain secrets/text).
    try:
        return operation()
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


def call_ai(operation):
    try:
        return retry_remote(operation)
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
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        self.client = GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model, google_api_key=settings.api_key,
            output_dimensionality=768, vertexai=False, client_args={'timeout': 45},
        )
        self.identity = 'gemini-' + sha256(settings.embedding_model.encode()).hexdigest()[:16]

    def embed_documents(self, texts):
        result = call_ai(lambda: self.client.embed_documents(texts))
        return self._normalize(result)

    def embed_query(self, text):
        return self._normalize([call_ai(lambda: self.client.embed_query(text))])[0]

    @staticmethod
    def _normalize(vectors):
        array = np.asarray(vectors, dtype=float)
        norms = np.linalg.norm(array, axis=1, keepdims=True)
        if not np.isfinite(array).all() or (norms == 0).any():
            raise ServiceError('Embedding service returned invalid vectors.')
        return (array / norms).tolist()
