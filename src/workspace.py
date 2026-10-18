"""Session-owned indexes with platform-safe Chroma storage and retryable cleanup."""
import logging
from pathlib import Path
import tempfile
import time
from uuid import uuid4
import weakref
import threading
from weakref import WeakValueDictionary

from src.config import Settings
from src.errors import ServiceError, ValidationError
from src.rag import RAGService

logger = logging.getLogger(__name__)


def _release(services, directory):
    # Keep failed clients registered, so an explicit second close() can retry.
    for key, service in list(services.items()):
        try:
            service.close()
        except Exception:
            logger.warning('An index could not close cleanly; session cleanup must be retried.')
        else:
            del services[key]
    if services:
        return False  # Never delete files while a client has failed to close.

    # Closing native resources/antivirus scans may release handles asynchronously.
    # Retry only OS deletion errors, for a bounded total delay of 0.75 seconds.
    for delay in (0, .05, .1, .2, .4):
        if delay:
            time.sleep(delay)
        try:
            directory.cleanup()
        except OSError:
            continue
        if not Path(directory.name).exists():
            return True
    logger.warning('Some session files remain locked; retry cleanup after closing the app.')
    return False


_REGISTRY = WeakValueDictionary()
_REGISTRY_LOCK = threading.Lock()
_REAPER_STARTED = False


def _reap_once():
    with _REGISTRY_LOCK:
        workspaces = list(_REGISTRY.values())
    for workspace in workspaces:
        if workspace.expired:
            workspace.close()


def _reap_loop():
    while True:
        time.sleep(30)
        _reap_once()


def _register(workspace):
    global _REAPER_STARTED
    with _REGISTRY_LOCK:
        if sum(not item._closed for item in _REGISTRY.values()) >= workspace.settings.max_active_workspaces:
            raise ServiceError('Workspace capacity reached. Retry later.')
        _REGISTRY[workspace.namespace] = workspace
        if not _REAPER_STARTED:
            threading.Thread(target=_reap_loop, name='finsight-cleanup', daemon=True).start()
            _REAPER_STARTED = True


class SessionWorkspace:
    def __init__(self, *, persistent: bool | None = None, settings=None):
        # All browser sessions use disposable, uniquely named memory collections.
        # Explicit persistent RAGService indexes remain available to offline scripts.
        self.persistent = False if persistent is None else persistent
        self.lock = threading.RLock()
        self.settings = settings or Settings()
        self.created = self.touched = time.monotonic()
        self.namespace = uuid4().hex
        self.directory = tempfile.TemporaryDirectory(prefix='finsight-session-')
        self.services = {}
        self._closed = False
        self._finalizer = weakref.finalize(self, _release, self.services, self.directory)
        _register(self)

    @property
    def expired(self):
        now = time.monotonic()
        return (self._closed or now - self.touched >= self.settings.session_idle_seconds
                or now - self.created >= self.settings.session_lifetime_seconds)

    def _capacity(self, document_id, chunks, settings):
        documents = {d['id'] for service in self.services.values() for d in service.documents()}
        if document_id not in documents and len(documents) >= settings.max_documents:
            raise ValidationError('Document library is full across this session. Delete documents first.')
        if sum(service.collection.count() for service in self.services.values()) + chunks > settings.max_chunks:
            raise ValidationError('Chunk storage limit reached across this session. Delete documents first.')

    def service(self, embeddings, settings):
        with self.lock:
            try:
                return self._service(embeddings, settings)
            except Exception:
                if all(item.embeddings is not embeddings for item in self.services.values()):
                    if hasattr(embeddings, 'close'):
                        embeddings.close()
                raise

    def _service(self, embeddings, settings):
        if self.expired:
            raise ServiceError('This session workspace is closed or expired. Start a new session.')
        self.touched = time.monotonic()
        key = embeddings.identity
        if key not in self.services:
            if len(self.services) >= 2:
                raise ValidationError('Session index limit reached. Clear this workspace first.')
            self.services[key] = RAGService(self.directory.name, embeddings, settings,
                                            persistent=self.persistent, namespace=self.namespace)
            self.services[key].lock = self.lock
            owner = weakref.ref(self)
            def capacity_check(document_id, chunks, configured):
                workspace = owner()
                if workspace is None:
                    raise ServiceError('Session workspace is unavailable.')
                workspace._capacity(document_id, chunks, configured)
            self.services[key].capacity_check = capacity_check
        else:
            previous = self.services[key].embeddings
            if previous is not embeddings and hasattr(previous, 'close'):
                previous.close()
            self.services[key].settings = settings
            self.services[key].embeddings = embeddings
        return self.services[key]

    def close(self):
        with self.lock:
            return self._close()

    def _close(self):
        if self._closed:
            return True
        removed = _release(self.services, self.directory)
        if removed:
            self._closed = True
            self._finalizer.detach()
        return removed
