"""Own session indexes and close Chroma before cleaning temporary directories."""
import logging
from pathlib import Path
import tempfile
import weakref

from src.rag import RAGService

logger = logging.getLogger(__name__)


def _release(services, directory):
    for service in services.values():
        try:
            service.close()
        except Exception:
            logger.warning('An index could not close cleanly; cleanup may require an app restart.')
    services.clear()
    # Windows can still hold external antivirus/file handles; never raise at interpreter exit.
    directory.cleanup()
    removed = not Path(directory.name).exists()
    if not removed:
        logger.warning('Some session files remain locked; retry cleanup after closing the app.')
    return removed


class SessionWorkspace:
    def __init__(self):
        self.directory = tempfile.TemporaryDirectory(prefix='finsight-session-',
                                                      ignore_cleanup_errors=True)
        self.services = {}
        # The callback owns resources, not self, so it can run on session collection or exit.
        self._finalizer = weakref.finalize(self, _release, self.services, self.directory)

    def service(self, embeddings, settings):
        key = embeddings.identity
        if key not in self.services:
            self.services[key] = RAGService(self.directory.name, embeddings, settings)
        else:
            self.services[key].settings = settings
            self.services[key].embeddings = embeddings
        return self.services[key]

    def close(self):
        if self._finalizer.alive:
            return self._finalizer()
        return not Path(self.directory.name).exists()
