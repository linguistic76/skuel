"""
Regression: per-IP login throttle complements per-account lockout
=================================================================

Closes 2026-05-26 security audit item #5 (per-IP throttle half). The pre-
existing account lockout (`is_account_locked`, keyed by email) catches a
focused brute force on a single account but does nothing for distributed
credential stuffing — one host blasting many emails. The new
`is_ip_rate_limited` + `count_recent_failed_attempts_by_ip` pair adds the
orthogonal axis.

These tests exercise the unit-level semantics. The Neo4j Cypher query is
covered by the integration suite under tests/integration/.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.persistence.neo4j.session_backend import (
    MAX_FAILED_ATTEMPTS_PER_IP,
    SessionBackend,
)
from core.auth.graph_auth import GraphAuthService
from core.utils.result_simplified import Result

# ----------------------------------------------------------------------------
# is_ip_rate_limited / count_recent_failed_attempts_by_ip
# ----------------------------------------------------------------------------


def _make_session_backend_with_count(count: int) -> SessionBackend:
    """Build a SessionBackend whose Cypher query returns the given failed-attempt count."""
    backend = SessionBackend.__new__(SessionBackend)
    backend.driver = MagicMock()
    backend.logger = MagicMock()

    record = {"failed_count": count}

    async def _single():
        return record

    async def _run(query, params):
        result = MagicMock()
        result.single = _single
        return result

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock(run=AsyncMock(side_effect=_run)))
    session_cm.__aexit__ = AsyncMock(return_value=None)
    backend.driver.session = MagicMock(return_value=session_cm)
    return backend


@pytest.mark.asyncio
async def test_ip_below_threshold_not_limited():
    backend = _make_session_backend_with_count(MAX_FAILED_ATTEMPTS_PER_IP - 1)
    result = await backend.is_ip_rate_limited("203.0.113.7")
    assert result.is_ok
    assert result.value is False


@pytest.mark.asyncio
async def test_ip_at_threshold_is_limited():
    backend = _make_session_backend_with_count(MAX_FAILED_ATTEMPTS_PER_IP)
    result = await backend.is_ip_rate_limited("203.0.113.7")
    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_unknown_sentinel_never_rate_limited():
    """CLI / background entry points pass 'unknown' — throttling would block every non-HTTP login."""
    backend = _make_session_backend_with_count(MAX_FAILED_ATTEMPTS_PER_IP * 100)
    result = await backend.is_ip_rate_limited("unknown")
    assert result.is_ok and result.value is False


@pytest.mark.asyncio
async def test_empty_ip_never_rate_limited():
    backend = _make_session_backend_with_count(MAX_FAILED_ATTEMPTS_PER_IP * 100)
    result = await backend.is_ip_rate_limited("")
    assert result.is_ok and result.value is False


# ----------------------------------------------------------------------------
# GraphAuthService.sign_in honors the IP throttle
# ----------------------------------------------------------------------------


def _graph_auth_with_backend_doubles(
    *,
    ip_limited: bool = False,
    account_locked: bool = False,
) -> tuple[GraphAuthService, MagicMock, MagicMock]:
    """Build a GraphAuthService whose session_backend reports the given throttle state.

    Returns the two backend doubles alongside the service: assertions read them
    directly rather than through ``service.<handle>``, which now names a protocol.
    """
    session_backend = MagicMock()
    session_backend.is_ip_rate_limited = AsyncMock(return_value=Result.ok(ip_limited))
    session_backend.is_account_locked = AsyncMock(return_value=Result.ok(account_locked))
    # If we reach further checks, fail closed loudly so the test surfaces it:
    session_backend.log_auth_event = AsyncMock(return_value=Result.ok(MagicMock()))

    user_backend = MagicMock()
    user_backend.find_by = AsyncMock(return_value=Result.ok([]))

    service = GraphAuthService.__new__(GraphAuthService)
    service.session_backend = session_backend
    service.user_backend = user_backend
    service.logger = MagicMock()
    return service, session_backend, user_backend


@pytest.mark.asyncio
async def test_sign_in_blocked_when_ip_throttled():
    """An IP at threshold gets a generic 'network' error BEFORE the email lookup runs.

    Order matters: blocking before find_by keeps the response indistinguishable
    for valid vs invalid emails from a throttled IP (no user-enumeration channel).
    """
    service, session_backend, user_backend = _graph_auth_with_backend_doubles(ip_limited=True)

    result = await service.sign_in(
        email="anyone@example.com",
        password="any_password",
        ip_address="203.0.113.7",
    )

    assert result.is_error
    err = result.expect_error().message.lower()
    assert "too many" in err or "network" in err
    # Account-locked branch must NOT have been reached
    session_backend.is_account_locked.assert_not_called()
    # And we must NOT have queried for the user (enumeration prevention)
    user_backend.find_by.assert_not_called()


@pytest.mark.asyncio
async def test_sign_in_proceeds_to_account_check_when_ip_clean():
    service, session_backend, _user_backend = _graph_auth_with_backend_doubles(ip_limited=False)

    await service.sign_in(
        email="anyone@example.com",
        password="any_password",
        ip_address="203.0.113.7",
    )

    session_backend.is_ip_rate_limited.assert_awaited_once_with("203.0.113.7")
    session_backend.is_account_locked.assert_awaited_once_with("anyone@example.com")


@pytest.mark.asyncio
async def test_sign_in_with_unknown_ip_skips_throttle_check_at_backend_level():
    """The backend, not graph_auth, is responsible for the 'unknown' sentinel.

    graph_auth still calls is_ip_rate_limited("unknown"); the backend returns False
    without a DB hit. Encodes the contract.
    """
    service, session_backend, _user_backend = _graph_auth_with_backend_doubles(ip_limited=False)

    await service.sign_in(
        email="anyone@example.com",
        password="any_password",
        ip_address="unknown",
    )

    session_backend.is_ip_rate_limited.assert_awaited_once_with("unknown")
