"""Cross-session and same-session races exercise real Chroma indexes."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import gc
from pathlib import Path
import threading
import time
import weakref

import pytest

from src.config import Settings
from src.embeddings import LocalEmbeddings
from src.errors import ServiceError, ValidationError
from src.session_state import clear_private_state, prepare_session
from src.workspace import SessionWorkspace, _reap_once


def test_simultaneous_uploads_cannot_query_or_delete_foreign_documents(samples):
    one, two = SessionWorkspace(), SessionWorkspace()
    try:
        first = one.service(LocalEmbeddings(), Settings())
        second = two.service(LocalEmbeddings(), Settings())
        barrier = threading.Barrier(2)
        def ingest(service, filename):
            barrier.wait(timeout=10)
            return service.ingest((samples / filename).read_bytes(), filename)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(ingest, first, 'annual_report.pdf')
            b = pool.submit(ingest, second, 'risk_note.pdf')
            first_id, second_id = a.result(), b.result()
        assert not first.search('liquidity risk', document_id=second_id)
        assert not second.search('revenue', document_id=first_id)
        first.delete_document(second_id)
        assert second.documents()[0]['id'] == second_id
        assert one.close()
        assert second.search('liquidity risk')
        assert not list(Path(two.directory.name).iterdir())
    finally:
        one.close()
        two.close()


def test_concurrent_same_session_uploads_cannot_exceed_document_limit(samples):
    settings = Settings(max_documents=1)
    workspace = SessionWorkspace(settings=settings)
    service = workspace.service(LocalEmbeddings(), settings)
    try:
        def ingest(filename):
            try:
                service.ingest((samples / filename).read_bytes(), filename)
                return 'ok'
            except ValidationError:
                return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(ingest, ['annual_report.pdf', 'risk_note.pdf']))
        assert sorted(results) == ['ok', 'rejected']
        assert len(service.documents()) == 1
    finally:
        workspace.close()


def test_limits_cannot_be_bypassed_by_switching_embedding_collection(sample_pdf, samples):
    class OtherEmbeddings(LocalEmbeddings): identity = 'other-model'
    settings = Settings(max_documents=1)
    workspace = SessionWorkspace(settings=settings)
    try:
        first = workspace.service(LocalEmbeddings(), settings)
        first.ingest(sample_pdf, 'first.pdf')
        second = workspace.service(OtherEmbeddings(), settings)
        with pytest.raises(ValidationError, match='across this session'):
            second.ingest((samples / 'risk_note.pdf').read_bytes(), 'second.pdf')
        assert not second.documents()
        # The same PDF can be reindexed under the other model, but chunks count twice.
        tight = replace(settings, max_chunks=first.collection.count())
        second.settings = tight
        with pytest.raises(ValidationError, match='Chunk storage limit'):
            second.ingest(sample_pdf, 'first.pdf')
    finally:
        workspace.close()


def test_background_expiry_releases_only_idle_session(sample_pdf):
    one, two = SessionWorkspace(), SessionWorkspace()
    first = one.service(LocalEmbeddings(), Settings())
    second = two.service(LocalEmbeddings(), Settings())
    try:
        first.ingest(sample_pdf, 'expired.pdf')
        second.ingest(sample_pdf, 'live.pdf')
        one.touched = time.monotonic() - one.settings.session_idle_seconds - 1
        _reap_once()
        assert one._closed
        with pytest.raises(ServiceError, match='closed'): first.documents()
        assert second.documents()[0]['name'] == 'live.pdf'
    finally:
        one.close()
        two.close()


def test_finalizer_has_no_service_to_workspace_reference_cycle(sample_pdf):
    workspace = SessionWorkspace()
    service = workspace.service(LocalEmbeddings(), Settings())
    service.ingest(sample_pdf, 'private.pdf')
    path = Path(workspace.directory.name)
    reference = weakref.ref(workspace)
    del workspace
    gc.collect()
    assert reference() is None
    assert not path.exists()
    assert service._closed


def test_clear_all_private_state_preserves_quota_identity_and_other_session():
    first = {'_quota_session': 'stable', 'messages': ['private'], 'financials': object(),
             'prices': object(), 'portfolio_result': object(), 'frontier': object(),
             'portfolio_parameters': object(), 'rag_identity': object(), 'chat_scope': 'private'}
    second = {'messages': ['other'], 'financials': object(), 'portfolio_result': object()}
    before = dict(second)
    clear_private_state(first)
    assert first == {'_quota_session': 'stable', '_upload_generation': 1}
    assert second == before


def test_expired_session_resets_results_before_next_ui_interaction():
    workspace = SessionWorkspace(settings=Settings(session_lifetime_seconds=0))
    state = {'workspace': workspace, 'messages': ['secret'], 'financials': object(),
             'prices': object(), 'portfolio_result': object(), '_quota_session': 'retained'}
    prepare_session(state)
    assert workspace._closed
    assert state == {'_quota_session': 'retained', '_upload_generation': 1}


def test_closed_service_refuses_read_write_and_provider_refresh(sample_pdf):
    workspace = SessionWorkspace()
    service = workspace.service(LocalEmbeddings(), Settings())
    assert workspace.close()
    for operation in (service.documents, lambda: service.ingest(sample_pdf, 'private.pdf'),
                      lambda: service.search('private'), lambda: service.delete_document('id')):
        with pytest.raises(ServiceError, match='closed'):
            operation()


def test_zero_workspace_capacity_refuses_admission():
    with pytest.raises(ServiceError, match='capacity'):
        SessionWorkspace(settings=Settings(max_active_workspaces=0))
