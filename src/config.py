"""Environment settings. Never log or serialize API credentials."""
from dataclasses import dataclass, field
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default='', repr=False)
    chat_model: str = 'gemini-2.5-flash'
    embedding_model: str = 'models/gemini-embedding-001'
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pdf_pages: int = 100
    max_documents: int = 20
    max_chunks: int = 5000

    @classmethod
    def from_env(cls):
        load_dotenv(override=False)
        return cls(
            api_key=os.getenv('GOOGLE_API_KEY', ''),
            chat_model=os.getenv('GEMINI_MODEL', 'gemini-2.5-flash'),
            embedding_model=os.getenv('GEMINI_EMBEDDING_MODEL', 'models/gemini-embedding-001'),
        )
