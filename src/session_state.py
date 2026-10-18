"""Private browser-session state lifecycle. No shared data cache or user identifiers."""
from uuid import uuid4

DATA_KEYS = ('rag_identity', 'rag_service', 'messages', 'chat_scope', 'financials',
             'prices', 'portfolio_result', 'frontier', 'portfolio_parameters')


def clear_private_state(state):
    """Call only after workspace.close() succeeds. Rotate upload widget identities."""
    for key in DATA_KEYS:
        state.pop(key, None)
    state.pop('workspace', None)
    state['_upload_generation'] = state.get('_upload_generation', 0) + 1
    # Keep this separate from workspace IDs so clearing cannot reset API quotas.
    state.setdefault('_quota_session', uuid4().hex)


def prepare_session(state):
    state.setdefault('_quota_session', uuid4().hex)
    state.setdefault('_upload_generation', 0)
    workspace = state.get('workspace')
    if workspace is not None and workspace.expired:
        if not workspace.close():
            from src.errors import ServiceError
            raise ServiceError('Expired workspace cleanup is pending. Retry shortly.')
        clear_private_state(state)
