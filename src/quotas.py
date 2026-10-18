"""Atomic, process-local admission control. Reservations include failed attempts.

No document text, credentials, IP addresses, or model output are stored here.
These counters are a safety brake, not a billing ledger or anonymous-user identity.
"""
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
import threading
import time

from src.errors import ServiceError


@dataclass
class Usage:
    minute: deque = field(default_factory=deque)
    requests: int = 0
    tokens: int = 0
    active: int = 0
    touched: float = 0


class QuotaGovernor:
    def __init__(self, clock=time.time, max_sessions=1000):
        self.clock = clock
        self.max_sessions = max_sessions
        self.lock = threading.Lock()
        self.day = None
        self.total = Usage()
        self.sessions = {}

    @contextmanager
    def reserve(self, settings, tokens):
        if not settings.gemini_enabled:
            raise ServiceError('Gemini is disabled by the operator. Use offline mode.')
        if not isinstance(tokens, int) or tokens < 0 or tokens > settings.gemini_max_input_tokens + settings.gemini_max_output_tokens:
            raise ServiceError('AI request exceeds the configured token allowance.')
        with self.lock:
            now = self.clock()
            day = int(now // 86400)  # UTC calendar day, not the host local timezone.
            if self.day != day:
                self.day = day
                self.total.requests = self.total.tokens = 0
                for usage in self.sessions.values():
                    usage.requests = usage.tokens = 0
            # Never evict current-day usage: clearing a workspace must not reset quotas.
            self.sessions = {key: usage for key, usage in self.sessions.items()
                             if usage.active or now - usage.touched < 86400}
            session = settings.session_id or 'non-ui'
            if session not in self.sessions:
                if len(self.sessions) >= self.max_sessions:
                    raise ServiceError('AI session capacity reached. Use offline mode or retry later.')
                self.sessions[session] = Usage(touched=now)
            own = self.sessions[session]
            for usage in (self.total, own):
                while usage.minute and usage.minute[0] <= now - 60:
                    usage.minute.popleft()
            limits = [
                (self.total, settings.gemini_requests_per_minute, settings.gemini_concurrency,
                 settings.gemini_daily_requests, settings.gemini_daily_tokens),
                (own, settings.gemini_session_requests_per_minute, settings.gemini_session_concurrency,
                 settings.gemini_session_daily_requests, settings.gemini_session_daily_tokens),
            ]
            for usage, rpm, concurrency, requests, budget in limits:
                if usage.active >= concurrency:
                    raise ServiceError('AI concurrency limit reached. Retry after the current request finishes.')
                if len(usage.minute) >= rpm:
                    raise ServiceError('AI request rate limit reached. Retry in a minute.')
                if usage.requests >= requests or usage.tokens + tokens > budget:
                    raise ServiceError('AI daily budget reached. Use offline mode or retry after UTC midnight.')
            for usage in (self.total, own):
                usage.minute.append(now)
                usage.requests += 1
                usage.tokens += tokens
                usage.active += 1
                usage.touched = now
        try:
            yield
        finally:
            with self.lock:
                self.total.active -= 1
                own.active -= 1


# A module singleton survives Streamlit reruns without caching any user data.
GOVERNOR = QuotaGovernor()


def input_units(text):
    """Conservative text-token reservation: one unit per UTF-8 byte, plus framing.

    This is deliberately larger than typical text token counts; it is not a
    currency estimate and cannot bound provider-specific hidden billing charges.
    """
    return len(text.encode('utf-8')) + 256
