from io import BytesIO
from unittest.mock import patch

import pytest
from pypdf import PdfWriter

from src.config import Settings
from src.documents import (Page, chunk_pages, clean_text, extract_pages,
                           extract_tables, ocr_page, safe_filename)
from src.errors import ServiceError, ValidationError


def test_extract_cites_original_page(sample_pdf):
    pages = extract_pages(sample_pdf, '../../annual_report.pdf')
    assert pages[0].source == 'annual_report.pdf'
    assert pages[0].page == 1
    assert '1500' in pages[0].text
    assert len(pages[0].document_id) == 64


def test_chunks_preserve_metadata():
    chunks = chunk_pages([Page('doc', 'report.pdf', 3, 'revenue 100 ' * 200)], 200, 30)
    assert len(chunks) > 1
    assert all(c.page == 3 and c.source == 'report.pdf' and len(c.text) <= 200 for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


@pytest.mark.parametrize('data,name', [(b'hello', 'x.pdf'), (b'%PDF-1.7', 'x.exe'), (b'', 'x.pdf')])
def test_invalid_upload(data, name):
    with pytest.raises(ValidationError):
        extract_pages(data, name)


def test_oversized_pdf(sample_pdf):
    with pytest.raises(ValidationError, match='upload limit'):
        extract_pages(sample_pdf, 'x.pdf', Settings(max_upload_bytes=10))


def test_encrypted_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt('secret')
    buffer = BytesIO()
    writer.write(buffer)
    with pytest.raises(ValidationError, match='Encrypted'):
        extract_pages(buffer.getvalue(), 'x.pdf')


def test_blank_and_page_limit():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = BytesIO()
    writer.write(buffer)
    with pytest.raises(ValidationError, match='No readable text'):
        extract_pages(buffer.getvalue(), 'blank.pdf')
    with pytest.raises(ValidationError, match='100 pages'):
        extract_pages(buffer.getvalue(), 'blank.pdf', Settings(max_pdf_pages=0))
    with patch('src.documents.ocr_page', return_value='Scanned revenue is 50'):
        pages = extract_pages(buffer.getvalue(), 'blank.pdf', ocr=True)
        assert pages[0].text == 'Scanned revenue is 50'


def test_table_extraction(sample_pdf):
    tables = extract_tables(sample_pdf, 'annual_report.pdf')
    assert tables and tables[0]['page'] == 1
    assert ['2025', '1500', '1000', '500'] in tables[0]['rows']


def test_ocr_missing_host_is_explicit():
    with patch('src.documents.shutil.which', return_value=None):
        with pytest.raises(ServiceError, match='Tesseract'):
            ocr_page(b'', 0)


def test_chunk_validation_and_cleaning():
    with pytest.raises(ValidationError):
        chunk_pages([], 100, 100)
    assert clean_text('a\x00  b\n\n\n c') == 'a b\n\n c'
    assert safe_filename('C:\\folder\\my.pdf') == 'my.pdf'


def test_real_scanned_pdf_ocr():
    import shutil
    pytest.importorskip('pytesseract')
    if not shutil.which('tesseract'):
        pytest.skip('Optional host Tesseract executable not installed')
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    image = Image.new('RGB', (1100, 220), 'white')
    draw = ImageDraw.Draw(image)
    # Pillow's built-in font avoids requiring a platform font file.
    font = ImageFont.load_default(size=48)
    draw.text((40, 60), 'Scanned revenue is 1500.', font=font, fill='black')
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawImage(ImageReader(image), 25, 500, width=550, height=110)
    pdf.save()
    pages = extract_pages(buffer.getvalue(), 'scan.pdf', ocr=True)
    assert '1500' in pages[0].text
    assert pages[0].page == 1
