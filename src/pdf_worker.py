"""Internal child entry point. No network calls, user paths, or provider credentials."""
import json
import sys


def main():
    header = json.loads(sys.stdin.buffer.readline(8192))
    limits = header['limits']
    if sys.platform == 'linux':
        import resource
        memory = max(64, limits['pdf_worker_memory_mb']) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        cpu = max(1, limits['pdf_timeout_seconds'])
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    from dataclasses import asdict
    from src.config import Settings
    from src.documents import _extract_pages, _extract_tables
    from src.errors import ServiceError, ValidationError
    import pypdf.filters
    # Bound decompression in pypdf before parsing streams. Timeout/memory limits
    # remain necessary for other filters and the separate pdfplumber parser.
    pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH = 4 * 1024 * 1024
    data = sys.stdin.buffer.read(limits['max_upload_bytes'] + 1)
    try:
        settings = Settings(**limits)
        if header['operation'] == 'pages':
            result = [asdict(page) for page in _extract_pages(data, header['name'], settings, header['ocr'])]
        else:
            result = _extract_tables(data, header['name'], settings)
        print(json.dumps({'result': result}))
    except (ValidationError, ServiceError) as exc:
        print(json.dumps({'error': str(exc), 'service': isinstance(exc, ServiceError)}))
    except Exception:
        print(json.dumps({'error': 'PDF could not be processed safely.'}))


if __name__ == '__main__':
    main()
