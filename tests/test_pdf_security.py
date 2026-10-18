from dataclasses import replace
from io import BytesIO
import subprocess
from unittest.mock import Mock

import pytest
from pypdf import PdfWriter
from pypdf.actions import JavaScript
from pypdf.generic import DecodedStreamObject, NameObject

from src.config import Settings
from src.documents import Page, chunk_pages, extract_pages, extract_tables
from src.errors import ServiceError, ValidationError
from src.pdf_process import _SLOTS


def pdf_bytes(writer):
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize('payload', ['javascript', 'attachment'])
def test_rejects_active_pdf_content(payload):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    if payload == 'javascript':
        writer.add_open_action(JavaScript('app.alert("untrusted")'))
    else:
        writer.add_attachment('payload.exe', b'not executable')
    with pytest.raises(ValidationError, match='active content'):
        extract_pages(pdf_bytes(writer), 'active.pdf')


def test_pdf_content_not_just_filename_or_magic_header():
    with pytest.raises(ValidationError):
        extract_pages(b'%PDF-1.7\n<html>not a pdf</html>', 'fake.pdf')


def test_custom_page_and_text_limits_apply_to_tables_and_text(sample_pdf):
    for parse in (extract_pages, extract_tables):
        with pytest.raises(ValidationError):
            parse(sample_pdf, 'report.pdf', Settings(max_pdf_pages=0))
        with pytest.raises(ValidationError, match='character limit'):
            parse(sample_pdf, 'report.pdf', Settings(max_pdf_text_chars=10))


def test_chunk_limit_is_enforced_while_building_not_after_allocation():
    pages = [Page('id', 'report.pdf', 1, 'revenue ' * 10_000)]
    with pytest.raises(ValidationError, match='Chunk storage limit'):
        chunk_pages(pages, chunk_size=100, overlap=0, max_chunks=2)


def test_compressed_pdf_stream_bomb_is_rejected():
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject()
    stream.set_data(b' ' * (5 * 1024 * 1024))
    page[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    data = pdf_bytes(writer)
    assert len(data) < 20_000
    with pytest.raises(ValidationError):
        extract_pages(data, 'compressed.pdf')


def test_worker_timeout_is_visible_and_releases_admission_slot(monkeypatch, sample_pdf):
    run = Mock(side_effect=subprocess.TimeoutExpired('worker', 1))
    monkeypatch.setattr('src.pdf_process._run_worker', run)
    with pytest.raises(ValidationError, match='time limit'):
        extract_pages(sample_pdf, 'report.pdf', Settings(pdf_timeout_seconds=1))
    assert run.call_args.kwargs['timeout'] == 1
    assert _SLOTS.acquire(blocking=False)
    assert _SLOTS.acquire(blocking=False)
    assert not _SLOTS.acquire(blocking=False)
    _SLOTS.release()
    _SLOTS.release()


def test_worker_capacity_rejects_instead_of_queuing_uploads(sample_pdf):
    assert _SLOTS.acquire(blocking=False)
    assert _SLOTS.acquire(blocking=False)
    try:
        with pytest.raises(ServiceError, match='busy'):
            extract_pages(sample_pdf, 'report.pdf')
    finally:
        _SLOTS.release()
        _SLOTS.release()


def test_parser_process_does_not_inherit_api_secrets(monkeypatch, sample_pdf):
    from src.pdf_process import _run_worker
    real_run = _run_worker
    def checked(*args, **kwargs):
        assert 'GOOGLE_API_KEY' not in kwargs['env']
        assert 'PRIVATE_TEST_SECRET' not in kwargs['env']
        return real_run(*args, **kwargs)
    monkeypatch.setenv('PRIVATE_TEST_SECRET', 'unit-test-placeholder')
    monkeypatch.setattr('src.pdf_process._run_worker', checked)
    assert extract_pages(sample_pdf, 'report.pdf')


@pytest.mark.parametrize('sizes,options,match', [
    ([1, 1], {'max_documents': 1}, 'Too many'),
    ([11], {'max_upload_bytes': 10}, 'upload limit'),
    ([0], {}, 'empty'),
    ([6, 6], {'max_batch_upload_bytes': 10}, 'combined upload budget'),
])
def test_selected_upload_batch_limits(sizes, options, match):
    from src.documents import validate_upload_batch
    with pytest.raises(ValidationError, match=match):
        validate_upload_batch(sizes, Settings(**options))


def test_real_timed_out_worker_is_killed_and_reaped(tmp_path):
    import os
    import sys
    from src.pdf_process import _run_worker
    pid_file = tmp_path / 'worker.pid'
    code = ('import os,time; from pathlib import Path; '
            'Path("worker.pid").write_text(str(os.getpid())); time.sleep(60)')
    with pytest.raises(subprocess.TimeoutExpired):
        _run_worker([sys.executable, '-c', code], input=b'', timeout=2,
                    env={'PATH': os.environ.get('PATH', ''),
                         **{key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR') if key in os.environ}},
                    cwd=tmp_path)
    assert pid_file.exists()
    # No platform-specific ps/kill probe: waitpid via Popen's context has completed.
    # A Linux-specific check additionally verifies the process is gone, not a zombie.
    if sys.platform == 'linux':
        assert not __import__('pathlib').Path('/proc', pid_file.read_text()).exists()
