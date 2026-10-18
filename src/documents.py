"""Bounded PDF parsing, optional OCR, and page-preserving chunking."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import re
import shutil

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
        raise ValidationError('PDF exceeds the configured upload limit.')
    return safe_filename(name)


def clean_text(text: str) -> str:
    text = text.replace('\x00', '').replace('\r', '\n')
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[^\S\n]+', ' ', text)).strip()


def _extract_pages(data: bytes, name: str, settings: Settings | None = None,
                  ocr: bool = False) -> list[Page]:
    settings = settings or Settings()
    source = validate_pdf(data, name, settings)
    document_id = sha256(source.encode() + b'\0' + data).hexdigest()
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValidationError('Encrypted PDFs are not supported. Upload an unlocked copy.')
        _reject_active_content(reader)
        if not 0 < len(reader.pages) <= settings.max_pdf_pages:
            raise ValidationError(f'PDF page limit: expected 1–{settings.max_pdf_pages} pages.')
        pages = []
        total = 0
        for index, page in enumerate(reader.pages):
            text = clean_text(page.extract_text() or '')
            if not text and ocr:
                text = clean_text(ocr_page(data, index))
            total += len(text)
            if total > settings.max_pdf_text_chars:
                raise ValidationError('PDF extracted text exceeds the configured character limit.')
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
                overlap: int = 150, max_chunks: int = 5000) -> list[Chunk]:
    if not 100 <= chunk_size <= 4000 or not 0 <= overlap < chunk_size:
        raise ValidationError('Use chunk size 100–4000 and overlap smaller than chunk size.')
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    chunks = []
    for page in pages:
        for i, text in enumerate(splitter.split_text(page.text)):
            if len(chunks) >= max_chunks:
                raise ValidationError('Chunk storage limit reached. Delete documents or use smaller PDFs.')
            key = f'{page.document_id}:{page.page}:{i}:{text}'
            chunks.append(Chunk(sha256(key.encode()).hexdigest(), page.document_id,
                                page.source, page.page, text))
    return chunks


def _extract_tables(data: bytes, name: str, settings: Settings | None = None) -> list[dict]:
    import pdfplumber
    settings = settings or Settings()
    source = validate_pdf(data, name, settings)
    _extract_pages(data, name, settings)  # Apply the same structural and text limits.
    tables = []
    total = 0
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            if len(pdf.pages) > settings.max_pdf_pages:
                raise ValidationError('PDF exceeds the configured page limit.')
            for number, page in enumerate(pdf.pages, 1):
                for table in page.extract_tables():
                    total += sum(len(str(cell)) for row in table for cell in row)
                    if total > settings.max_pdf_text_chars:
                        raise ValidationError('Extracted tables exceed the configured character limit.')
                    tables.append({'source': source, 'page': number, 'rows': table})
                    if len(tables) >= 100:
                        return tables
    except ValidationError:
        raise
    except Exception:
        raise ValidationError('Tables could not be extracted from this PDF.') from None
    return tables


def _reject_active_content(reader):
    """Reject embedded payloads/actions without executing or following any links."""
    from pypdf.generic import DictionaryObject, ArrayObject, IndirectObject
    blocked = {'/JS', '/JavaScript', '/OpenAction', '/AA', '/EmbeddedFiles',
               '/Launch', '/RichMedia', '/XFA', '/SubmitForm', '/ImportData', '/GoToR'}
    pending, seen = [reader.trailer], set()
    count = 0
    while pending:
        item = pending.pop()
        if isinstance(item, IndirectObject):
            key = (item.idnum, item.generation)
            if key in seen:
                continue
            seen.add(key)
            item = item.get_object()
        count += 1
        if count > 100_000:
            raise ValidationError('PDF object complexity exceeds the safety limit.')
        if isinstance(item, DictionaryObject):
            if blocked.intersection(item) or str(item.get('/S', '')) in blocked:
                raise ValidationError('PDF contains active content or embedded files; export a flattened copy.')
            pending.extend(item.values())
        elif isinstance(item, ArrayObject):
            pending.extend(item)


def extract_pages(data: bytes, name: str, settings: Settings | None = None,
                  ocr: bool = False) -> list[Page]:
    from src.pdf_process import parse_pdf
    return [Page(**row) for row in parse_pdf(data, name, settings or Settings(), 'pages', ocr)]


def extract_tables(data: bytes, name: str, settings: Settings | None = None) -> list[dict]:
    from src.pdf_process import parse_pdf
    return parse_pdf(data, name, settings or Settings(), 'tables', False)


def validate_upload_batch(sizes, settings):
    """Check selected upload buffers before copying/parsing any file contents."""
    if len(sizes) > settings.max_documents:
        raise ValidationError('Too many selected PDFs. Select fewer documents.')
    if any(size < 1 or size > settings.max_upload_bytes for size in sizes):
        raise ValidationError('A PDF exceeds the configured upload limit or is empty.')
    if sum(sizes) > settings.max_batch_upload_bytes:
        raise ValidationError('Selected PDFs exceed the combined upload budget. Select fewer files.')
