"""Bounded PDF parsing, optional OCR, and page-preserving chunking."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import re
import shutil

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from src.config import Settings
from src.errors import ServiceError, ValidationError


@dataclass(frozen=True)
class Page:
    document_id: str
    source: str
    page: int
    text: str


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    source: str
    page: int
    text: str


def safe_filename(name: str) -> str:
    # Filenames are display metadata only; uploads are never written to user paths.
    name = re.split(r'[/\\]', name)[-1]
    return re.sub(r'[^\w .-]', '_', name)[:120] or 'document.pdf'


def validate_pdf(data: bytes, name: str, settings: Settings) -> str:
    if not name.lower().endswith('.pdf') or not data.startswith(b'%PDF-'):
        raise ValidationError('Upload a valid PDF file.')
    if len(data) > settings.max_upload_bytes:
        raise ValidationError('PDF exceeds the 20 MB upload limit.')
    return safe_filename(name)


def clean_text(text: str) -> str:
    text = text.replace('\x00', '').replace('\r', '\n')
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[^\S\n]+', ' ', text)).strip()


def extract_pages(data: bytes, name: str, settings: Settings | None = None,
                  ocr: bool = False) -> list[Page]:
    settings = settings or Settings()
    source = validate_pdf(data, name, settings)
    document_id = sha256(source.encode() + b'\0' + data).hexdigest()
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValidationError('Encrypted PDFs are not supported. Upload an unlocked copy.')
        if not 0 < len(reader.pages) <= settings.max_pdf_pages:
            raise ValidationError('PDF must contain between 1 and 100 pages.')
        pages = []
        total = 0
        for index, page in enumerate(reader.pages):
            text = clean_text(page.extract_text() or '')
            if not text and ocr:
                text = clean_text(ocr_page(data, index))
            total += len(text)
            if total > 2_000_000:
                raise ValidationError('PDF extracted text exceeds the 2 million character limit.')
            if text:
                pages.append(Page(document_id, source, index + 1, text))
        if not pages:
            raise ValidationError('No readable text found. Enable optional OCR for scanned PDFs.')
        return pages
    except (ValidationError, ServiceError):
        raise
    except Exception:
        raise ValidationError('PDF could not be parsed. Use a valid, unlocked PDF.') from None


def ocr_page(data: bytes, index: int) -> str:
    """OCR is opt-in and needs the optional packages plus Tesseract executable."""
    if not shutil.which('tesseract'):
        raise ServiceError('OCR needs Tesseract installed on the host; see deployment docs.')
    try:
        import pypdfium2
        import pytesseract
    except ImportError:
        raise ServiceError('Install requirements-ocr.txt to enable OCR.') from None
    try:
        pdf = pypdfium2.PdfDocument(data)
        try:
            page = pdf[index]
            try:
                width, height = page.get_size()
                if width * height * 4 > 20_000_000:
                    raise ValidationError('Scanned page dimensions exceed the OCR pixel limit.')
                bitmap = page.render(scale=2)
                try:
                    return pytesseract.image_to_string(bitmap.to_pil(), timeout=20)
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            pdf.close()
    except ValidationError:
        raise
    except Exception:
        raise ServiceError('OCR failed or exceeded its processing timeout.') from None


def chunk_pages(pages: list[Page], chunk_size: int = 1000,
                overlap: int = 150) -> list[Chunk]:
    if not 100 <= chunk_size <= 4000 or not 0 <= overlap < chunk_size:
        raise ValidationError('Use chunk size 100–4000 and overlap smaller than chunk size.')
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    chunks = []
    for page in pages:
        for i, text in enumerate(splitter.split_text(page.text)):
            key = f'{page.document_id}:{page.page}:{i}:{text}'
            chunks.append(Chunk(sha256(key.encode()).hexdigest(), page.document_id,
                                page.source, page.page, text))
    return chunks


def extract_tables(data: bytes, name: str, settings: Settings | None = None) -> list[dict]:
    import pdfplumber
    settings = settings or Settings()
    source = validate_pdf(data, name, settings)
    tables = []
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            if len(pdf.pages) > settings.max_pdf_pages:
                raise ValidationError('PDF exceeds the 100 page limit.')
            for number, page in enumerate(pdf.pages, 1):
                for table in page.extract_tables():
                    tables.append({'source': source, 'page': number, 'rows': table})
                    if len(tables) >= 100:
                        return tables
    except ValidationError:
        raise
    except Exception:
        raise ValidationError('Tables could not be extracted from this PDF.') from None
    return tables
