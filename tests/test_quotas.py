"""Deterministic admission tests: no network, real locks and simultaneous callers."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
from unittest.mock import patch

import pytest

from src.config import Settings
from src.embeddings import call_ai
from src.errors import ServiceError
from src.quotas import QuotaGovernor, input_units


def test_global_and_session_rate_windows():
    now = [1000.]
    governor = QuotaGovernor(clock=lambda: now[0])
    one = Settings(session_id='one', gemini_session_requests_per_minute=1, gemini_requests_per_minute=2)
    two = replace(one, session_id='two')
    with governor.reserve(one, 100): pass
    with pytest.raises(ServiceError, match='rate limit'):
        with governor.reserve(one, 100): pass
    with governor.reserve(two, 100): pass
    with pytest.raises(ServiceError, match='rate limit'):
        with governor.reserve(replace(two, session_id='third'), 100): pass
    now[0] += 60
    with governor.reserve(one, 100): pass
    assert governor.total.requests == 3


def test_concurrent_global_admission_is_atomic():
    governor = QuotaGovernor()
    barrier = threading.Barrier(9)
    release = threading.Event()
    admitted = []
    lock = threading.Lock()
    def attempt(index):
        settings = Settings(session_id=str(index), gemini_concurrency=2)
        barrier.wait(timeout=10)
        try:
            with governor.reserve(settings, 100):
                with lock: admitted.append(index)
                release.wait(timeout=10)
            return 'accepted'
        except ServiceError as exc:
            assert 'concurrency' in str(exc)
            return 'rejected'
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(attempt, i) for i in range(8)]
        barrier.wait(timeout=10)
        # Rejected calls finish while the admitted requests are still blocked.
        from concurrent.futures import wait, FIRST_COMPLETED
        while len([f for f in futures if f.done()]) < 6:
            done, _ = wait([f for f in futures if not f.done()], timeout=5, return_when=FIRST_COMPLETED)
            assert done
        assert len(admitted) == 2
        release.set()
        results = [f.result(timeout=10) for f in futures]
    assert results.count('accepted') == 2
    assert results.count('rejected') == 6
    assert governor.total.active == 0
    assert governor.total.requests == 2


def test_session_concurrency_and_failed_request_release():
    governor = QuotaGovernor()
    settings = Settings(session_id='one')
    with pytest.raises(RuntimeError):
        with governor.reserve(settings, 100):
            with pytest.raises(ServiceError, match='concurrency'):
                with governor.reserve(settings, 100): pass
            with governor.reserve(replace(settings, session_id='two'), 100): pass
            raise RuntimeError('simulated failure')
    assert governor.total.active == 0
    assert governor.total.requests == 2  # Errors are still charged.
    with governor.reserve(settings, 100): pass


def test_daily_budget_shared_across_sessions_and_utc_reset():
    now = [86400. * 10 + 1]
    governor = QuotaGovernor(clock=lambda: now[0])
    config = Settings(session_id='one', gemini_daily_tokens=200, gemini_daily_requests=2)
    with governor.reserve(config, 120): pass
    with pytest.raises(ServiceError, match='daily budget'):
        with governor.reserve(replace(config, session_id='two'), 81): pass
    with governor.reserve(replace(config, session_id='two'), 80): pass
    with pytest.raises(ServiceError, match='daily budget'):
        with governor.reserve(replace(config, session_id='new-session'), 1): pass
    now[0] += 86400.
    with governor.reserve(config, 120): pass
    assert governor.total.requests == 1 and governor.total.tokens == 120


def test_session_daily_budget_cannot_reset_by_new_workspace():
    governor = QuotaGovernor()
    config = Settings(session_id='stable-browser-id', gemini_session_daily_requests=1)
    with governor.reserve(config, 1): pass
    with pytest.raises(ServiceError, match='daily budget'):
        with governor.reserve(replace(config), 1): pass
    # A distinct browser identity can bypass the session budget, but not global budgets.
    with governor.reserve(replace(config, session_id='new-browser-id'), 1): pass


@pytest.mark.parametrize('options,units,match', [
    ({'gemini_enabled': False}, 1, 'disabled'),
    ({'gemini_concurrency': 0}, 1, 'concurrency'),
    ({'gemini_daily_requests': 0}, 1, 'daily budget'),
    ({'gemini_max_input_tokens': 10, 'gemini_max_output_tokens': 5}, 16, 'token allowance'),
])
def test_disabled_zero_and_token_limits(options, units, match):
    with pytest.raises(ServiceError, match=match):
        with QuotaGovernor().reserve(Settings(**options), units): pass


def test_capacity_rejects_without_evicting_current_day_budgets():
    governor = QuotaGovernor(max_sessions=1)
    with governor.reserve(Settings(session_id='one'), 1): pass
    with pytest.raises(ServiceError, match='capacity'):
        with governor.reserve(Settings(session_id='two'), 1): pass


def test_every_retry_reserves_budget_and_stops_before_next_network_call(isolated_ai_governor):
    calls = []
    class ResourceExhausted(Exception): pass
    def fail():
        calls.append(1)
        raise ResourceExhausted('private provider payload')
    settings = Settings(gemini_daily_requests=2)
    with patch('tenacity.nap.time.sleep'):
        with pytest.raises(ServiceError, match='daily budget'):
            call_ai(fail, settings=settings, tokens=100)
    assert len(calls) == 2
    assert isolated_ai_governor.total.requests == 2
    assert isolated_ai_governor.total.tokens == 200
    assert isolated_ai_governor.total.active == 0


def test_utf8_reservation_is_conservative():
    assert input_units('₹') == 259
