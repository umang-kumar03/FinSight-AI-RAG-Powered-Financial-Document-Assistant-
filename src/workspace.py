"""Session-owned indexes with platform-safe Chroma storage and retryable cleanup."""
import logging
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4
import weakref

from src.errors import ServiceError
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


class SessionWorkspace:
    def __init__(self, *, persistent: bool | None = None):
        # Sessions promise no cross-restart durability. On Windows, avoid Chroma 1.5.9's
        # native persistent-file shutdown limitation without changing explicit RAG indexes.
        self.persistent = sys.platform != 'win32' if persistent is None else persistent
        self.namespace = uuid4().hex[:16]
        self.directory = tempfile.TemporaryDirectory(prefix='finsight-session-')
        self.services = {}
        self._closed = False
        self._finalizer = weakref.finalize(self, _release, self.services, self.directory)

    def service(self, embeddings, settings):
        if self._closed:
            raise ServiceError('This session workspace is closed. Start a new session.')
        key = embeddings.identity
        if key not in self.services:
            self.services[key] = RAGService(self.directory.name, embeddings, settings,
                                            persistent=self.persistent, namespace=self.namespace)
        else:
            self.services[key].settings = settings
            self.services[key].embeddings = embeddings
        return self.services[key]

    def close(self):
        if self._closed:
            return True
        removed = _release(self.services, self.directory)
        if removed:
            self._closed = True
            self._finalizer.detach()
        return removed
