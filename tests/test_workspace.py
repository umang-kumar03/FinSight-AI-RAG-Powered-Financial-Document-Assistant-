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


def test_windows_default_uses_memory_without_persistent_files(monkeypatch, sample_pdf):
    workspace = SessionWorkspace()
    try:
        assert workspace.persistent is False
        service = workspace.service(LocalEmbeddings(), Settings())
        service.ingest(sample_pdf, 'report.pdf')
        assert not list(Path(workspace.directory.name).iterdir())
        assert service.answer('revenue 2025').sources
        assert workspace.close()
    finally:
        workspace.close()


def test_memory_sessions_remain_isolated_with_live_other_client(sample_pdf):
    one, two = SessionWorkspace(persistent=False), SessionWorkspace(persistent=False)
    first = one.service(LocalEmbeddings(), Settings())
    other = two.service(LocalEmbeddings(), Settings())
    try:
        first.ingest(sample_pdf, 'one.pdf')
        other.ingest(sample_pdf, 'two.pdf')
        first_collection = first.collection_name
        assert first_collection != other.collection_name
        assert one.close()
        assert not Path(one.directory.name).exists()
        assert other.documents()[0]['name'] == 'two.pdf'
        assert other.answer('revenue').sources
        assert first_collection not in [c.name for c in other.client.list_collections()]
    finally:
        assert one.close()
        assert two.close()


def test_cleanup_retries_temporary_windows_lock(monkeypatch):
    workspace = SessionWorkspace(persistent=False)
    original = workspace.directory.cleanup
    calls = []
    def locked_then_released():
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError('simulated Windows file lock')
        original()
    monkeypatch.setattr(workspace.directory, 'cleanup', locked_then_released)
    monkeypatch.setattr('src.workspace.time.sleep', lambda _: None)
    assert workspace.close()
    assert len(calls) == 3
    assert not Path(workspace.directory.name).exists()


def test_persistent_cleanup_failure_is_visible_and_can_be_retried(monkeypatch, caplog):
    workspace = SessionWorkspace(persistent=False)
    original = workspace.directory.cleanup
    monkeypatch.setattr('src.workspace.time.sleep', lambda _: None)
    monkeypatch.setattr(workspace.directory, 'cleanup', Mock(side_effect=PermissionError('locked')))
    assert workspace.close() is False
    assert workspace._finalizer.alive
    assert 'remain locked' in caplog.text
    assert Path(workspace.directory.name).exists()
    monkeypatch.setattr(workspace.directory, 'cleanup', original)
    assert workspace.close()


def test_client_close_failure_never_deletes_directory(monkeypatch):
    workspace = SessionWorkspace(persistent=False)
    service = workspace.service(LocalEmbeddings(), Settings())
    original = service.close
    monkeypatch.setattr(service, 'close', Mock(side_effect=RuntimeError('cannot close')))
    cleanup = Mock(wraps=workspace.directory.cleanup)
    monkeypatch.setattr(workspace.directory, 'cleanup', cleanup)
    assert workspace.close() is False
    cleanup.assert_not_called()
    assert workspace.services
    monkeypatch.setattr(service, 'close', original)
    assert workspace.close()


def test_closed_workspace_cannot_reopen_storage():
    import pytest
    from src.errors import ServiceError
    workspace = SessionWorkspace(persistent=False)
    assert workspace.close()
    with pytest.raises(ServiceError, match='closed'):
        workspace.service(LocalEmbeddings(), Settings())


def test_memory_close_can_retry_after_collection_was_already_deleted(monkeypatch, tmp_path):
    import pytest
    service = RAGService(tmp_path, persistent=False)
    client = service.client
    original = client.close
    calls = []
    def flaky_close():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('temporary close failure')
        original()
    monkeypatch.setattr(client, 'close', flaky_close)
    delete = Mock(wraps=client.delete_collection)
    monkeypatch.setattr(client, 'delete_collection', delete)
    with pytest.raises(RuntimeError):
        service.close()
    service.close()
    delete.assert_called_once()
    assert len(calls) == 2
