"""Exercise the public Chroma lifecycle and cross-session ownership boundary."""
from pathlib import Path
from unittest.mock import Mock

from src.config import Settings
from src.embeddings import LocalEmbeddings
from src.rag import RAGService
from src.workspace import SessionWorkspace


def test_workspace_close_releases_clients_before_directory_removal(sample_pdf):
    workspace = SessionWorkspace()
    service = workspace.service(LocalEmbeddings(), Settings())
    service.ingest(sample_pdf, 'report.pdf')
    path = Path(workspace.directory.name)
    assert path.exists()
    assert workspace.close()
    assert not path.exists()
    assert workspace.close()  # Closing twice is safe.


def test_workspace_clear_never_removes_other_session(sample_pdf):
    one, two = SessionWorkspace(), SessionWorkspace()
    try:
        one.service(LocalEmbeddings(), Settings()).ingest(sample_pdf, 'one.pdf')
        other = two.service(LocalEmbeddings(), Settings())
        other.ingest(sample_pdf, 'two.pdf')
        assert one.close()
        assert other.documents()[0]['name'] == 'two.pdf'
    finally:
        one.close()
        two.close()


def test_service_context_closes_client(tmp_path):
    service = RAGService(tmp_path / 'index')
    close = Mock(wraps=service.client.close)
    service.client.close = close
    with service:
        assert not service.documents()
    close.assert_called_once()


def test_refreshed_provider_replaces_cached_credentials_without_reindexing(sample_pdf):
    workspace = SessionWorkspace()
    try:
        original = LocalEmbeddings()
        service = workspace.service(original, Settings())
        service.ingest(sample_pdf, 'report.pdf')
        refreshed = LocalEmbeddings()
        assert workspace.service(refreshed, Settings()) is service
        assert service.embeddings is refreshed
        assert service.documents()
    finally:
        workspace.close()
