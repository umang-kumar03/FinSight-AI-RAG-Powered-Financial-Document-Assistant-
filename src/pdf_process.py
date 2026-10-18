"""Disposable, bounded PDF workers; uploads are piped, never saved to shared paths."""
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import threading

from src.documents import validate_pdf
from src.errors import ServiceError, ValidationError

# Admission is shared across sessions, and rejects instead of queuing upload bytes.
_SLOTS = threading.BoundedSemaphore(2)


def parse_pdf(data, name, settings, operation, ocr):
    name = validate_pdf(data, name, settings)
    if not _SLOTS.acquire(blocking=False):
        raise ServiceError('PDF processing is busy. Retry when another upload finishes.')
    try:
        limits = {key: getattr(settings, key) for key in (
            'max_upload_bytes', 'max_pdf_pages', 'max_pdf_text_chars',
            'pdf_timeout_seconds', 'pdf_worker_memory_mb')}
        header = json.dumps({'name': name, 'operation': operation, 'ocr': ocr, 'limits': limits}).encode()
        # The parsing child does not need provider credentials or Streamlit secrets.
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG')
               if key in os.environ}
        env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', PYTHONNOUSERSITE='1')
        try:
            result = _run_worker(
                [sys.executable, '-m', 'src.pdf_worker'], input=header + b'\n' + data,
                timeout=max(1, settings.pdf_timeout_seconds), env=env,
                cwd=Path(__file__).resolve().parents[1])
        except subprocess.TimeoutExpired:
            raise ValidationError('PDF processing exceeded the time limit.') from None
        if result.returncode or len(result.stdout) > settings.max_pdf_text_chars * 12 + 1_000_000:
            raise ValidationError('PDF processing exceeded a safety limit or could not finish.')
        try:
            payload = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            raise ValidationError('PDF processing could not finish safely.') from None
        if 'error' in payload:
            error = ServiceError if payload.get('service') else ValidationError
            raise error(payload['error'])
        return payload['result']
    finally:
        _SLOTS.release()


def _run_worker(command, *, input, timeout, env, cwd):
    # A separate process group lets Linux reap an OCR descendant too, rather than
    # killing just the Python parent and leaving a Tesseract process running.
    options = {'start_new_session': True} if os.name == 'posix' else {
        'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=env, cwd=cwd, **options) as process:
        try:
            output, _ = process.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                # Windows taskkill /T includes any opt-in OCR descendant.
                try:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=5, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                if process.poll() is None:
                    process.kill()
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout=output)
