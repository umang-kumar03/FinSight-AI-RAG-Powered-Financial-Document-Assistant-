"""Environment settings. Never log or serialize API credentials."""
from dataclasses import dataclass, field, fields
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default='', repr=False)
    chat_model: str = 'gemini-2.5-flash'
    embedding_model: str = 'models/gemini-embedding-001'
    max_upload_bytes: int = 20 * 1024 * 1024
    max_batch_upload_bytes: int = 40 * 1024 * 1024
    max_pdf_pages: int = 100
    max_documents: int = 20
    max_chunks: int = 5000

    max_active_workspaces: int = 16
    max_pdf_text_chars: int = 500_000
    pdf_timeout_seconds: int = 20
    pdf_worker_memory_mb: int = 512
    session_idle_seconds: int = 1800
    session_lifetime_seconds: int = 7200
    gemini_enabled: bool = True
    gemini_requests_per_minute: int = 30
    gemini_session_requests_per_minute: int = 6
    gemini_concurrency: int = 2
    gemini_session_concurrency: int = 1
    gemini_daily_requests: int = 500
    gemini_daily_tokens: int = 500_000
    gemini_session_daily_requests: int = 50
    gemini_session_daily_tokens: int = 50_000
    gemini_max_input_tokens: int = 16_000
    gemini_max_output_tokens: int = 1024
    # Random server-generated identifier; never accept a user-supplied session identifier.
    session_id: str = field(default='', repr=False)

    @classmethod
    def from_env(cls):
        load_dotenv(override=False)
        values = {
            'api_key': os.getenv('GOOGLE_API_KEY', ''),
            'chat_model': os.getenv('GEMINI_MODEL', 'gemini-2.5-flash'),
            'embedding_model': os.getenv('GEMINI_EMBEDDING_MODEL', 'models/gemini-embedding-001'),
        }
        for item in fields(cls):
            if item.name in {'api_key', 'chat_model', 'embedding_model', 'session_id'}:
                continue
            raw = os.getenv(item.name.upper())
            if raw is not None:
                if item.name == 'gemini_enabled':
                    if raw.lower() not in {'true', 'false', '1', '0'}:
                        raise ValueError('GEMINI_ENABLED must be true or false.')
                    values[item.name] = raw.lower() in {'true', '1'}
                else:
                    try:
                        value = int(raw)
                    except ValueError:
                        raise ValueError(f'{item.name.upper()} must be an integer.') from None
                    if value < 0:
                        raise ValueError(f'{item.name.upper()} must be nonnegative.')
                    values[item.name] = value
        return cls(**values)
