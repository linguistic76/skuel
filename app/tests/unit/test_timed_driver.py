"""Unit tests for the TimedDriver / TimedSession proxy."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from neo4j import Query

from adapters.persistence.neo4j.timed_driver import (
    TimedDriver,
    TimedSession,
    neo4j_query_timeout,
    unbounded_neo4j_query_timeout,
)
from core.config.unified_config import DatabaseConfig

# ---------------------------------------------------------------------------
# TimedSession.run — str wrapping + override semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_wraps_str_with_default_timeout() -> None:
    """A str query is wrapped into a Query carrying the default timeout."""
    raw = MagicMock()
    raw.run = AsyncMock(return_value="result-sentinel")
    session = TimedSession(raw, default_timeout=10.0)

    result = await session.run("MATCH (n) RETURN n")

    assert result == "result-sentinel"
    raw.run.assert_awaited_once()
    sent_query = raw.run.await_args.args[0]
    assert isinstance(sent_query, Query)
    assert sent_query.timeout == 10.0


@pytest.mark.asyncio
async def test_run_respects_override() -> None:
    """`neo4j_query_timeout(5.0)` overrides the session default."""
    raw = MagicMock()
    raw.run = AsyncMock()
    session = TimedSession(raw, default_timeout=120.0)

    with neo4j_query_timeout(5.0):
        await session.run("MATCH (n) RETURN n")

    sent_query = raw.run.await_args.args[0]
    assert isinstance(sent_query, Query)
    assert sent_query.timeout == 5.0


@pytest.mark.asyncio
async def test_run_respects_unbounded() -> None:
    """`unbounded_neo4j_query_timeout()` sets the query timeout to None."""
    raw = MagicMock()
    raw.run = AsyncMock()
    session = TimedSession(raw, default_timeout=120.0)

    with unbounded_neo4j_query_timeout():
        await session.run("MATCH (n) RETURN n")

    sent_query = raw.run.await_args.args[0]
    assert isinstance(sent_query, Query)
    assert sent_query.timeout is None


@pytest.mark.asyncio
async def test_run_does_not_clobber_caller_query() -> None:
    """A caller-supplied Query is forwarded untouched (its timeout wins)."""
    raw = MagicMock()
    raw.run = AsyncMock()
    session = TimedSession(raw, default_timeout=10.0)

    original = Query("RETURN 1", timeout=7.0)  # type: ignore[arg-type]
    await session.run(original)

    sent_query = raw.run.await_args.args[0]
    assert sent_query is original
    assert sent_query.timeout == 7.0


# ---------------------------------------------------------------------------
# TimedSession.begin_transaction — default injection + caller override
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_begin_transaction_injects_default() -> None:
    """`begin_transaction()` with no explicit timeout receives the default."""
    raw = MagicMock()
    raw.begin_transaction = AsyncMock()
    session = TimedSession(raw, default_timeout=42.0)

    await session.begin_transaction()

    raw.begin_transaction.assert_awaited_once()
    assert raw.begin_transaction.await_args.kwargs["timeout"] == 42.0


@pytest.mark.asyncio
async def test_begin_transaction_honors_explicit_caller_value() -> None:
    """An explicit `timeout=` survives the wrapper."""
    raw = MagicMock()
    raw.begin_transaction = AsyncMock()
    session = TimedSession(raw, default_timeout=42.0)

    await session.begin_transaction(timeout=99.0)

    assert raw.begin_transaction.await_args.kwargs["timeout"] == 99.0


@pytest.mark.asyncio
async def test_begin_transaction_respects_override() -> None:
    """`neo4j_query_timeout(...)` flows through to `begin_transaction` too."""
    raw = MagicMock()
    raw.begin_transaction = AsyncMock()
    session = TimedSession(raw, default_timeout=42.0)

    with neo4j_query_timeout(300.0):
        await session.begin_transaction()

    assert raw.begin_transaction.await_args.kwargs["timeout"] == 300.0


# ---------------------------------------------------------------------------
# TimedDriver — session factory + execute_query wrapping
# ---------------------------------------------------------------------------


def test_driver_session_returns_timed_session() -> None:
    """`driver.session()` returns a TimedSession proxying the raw session."""
    raw_driver = MagicMock()
    raw_driver.session = MagicMock(return_value="raw-session-sentinel")
    driver = TimedDriver(raw_driver, default_timeout=120.0)

    sess = driver.session(database="neo4j")

    assert isinstance(sess, TimedSession)
    raw_driver.session.assert_called_once_with(database="neo4j")
    assert sess._raw == "raw-session-sentinel"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_execute_query_wraps_str_with_default_timeout() -> None:
    """`driver.execute_query(str, ...)` wraps the string into a timed Query."""
    raw_driver = MagicMock()
    raw_driver.execute_query = AsyncMock(return_value=("records", "summary", "keys"))
    driver = TimedDriver(raw_driver, default_timeout=120.0)

    await driver.execute_query("MATCH (n) RETURN n", {"k": "v"})

    sent_query = raw_driver.execute_query.await_args.args[0]
    assert isinstance(sent_query, Query)
    assert sent_query.timeout == 120.0


@pytest.mark.asyncio
async def test_execute_query_respects_override() -> None:
    """`neo4j_query_timeout(...)` applies to `driver.execute_query` too."""
    raw_driver = MagicMock()
    raw_driver.execute_query = AsyncMock()
    driver = TimedDriver(raw_driver, default_timeout=120.0)

    with neo4j_query_timeout(15.0):
        await driver.execute_query("MATCH (n) RETURN n")

    sent_query = raw_driver.execute_query.await_args.args[0]
    assert isinstance(sent_query, Query)
    assert sent_query.timeout == 15.0


# ---------------------------------------------------------------------------
# Config — env loading
# ---------------------------------------------------------------------------


def test_transaction_timeout_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`NEO4J_TRANSACTION_TIMEOUT=45` lands in DatabaseConfig.transaction_timeout."""
    monkeypatch.setenv("NEO4J_TRANSACTION_TIMEOUT", "45")
    cfg = DatabaseConfig.from_env()
    assert cfg.transaction_timeout == 45.0


def test_transaction_timeout_default_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default is 120.0s when NEO4J_TRANSACTION_TIMEOUT is unset."""
    monkeypatch.delenv("NEO4J_TRANSACTION_TIMEOUT", raising=False)
    cfg = DatabaseConfig.from_env()
    assert cfg.transaction_timeout == 120.0
