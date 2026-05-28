"""
Timed Driver Proxy
==================

Wraps the shared ``AsyncDriver`` at the composition root to apply a server-side
per-transaction timeout to every Neo4j query — the chokepoint the codebase
otherwise lacks. ~124 ``session.run(...)`` sites across 24 files in
``adapters/persistence/neo4j/`` each open their own ``self.driver.session()``;
wrapping the **one** driver instance at ``services_bootstrap/compose.py`` covers
all of them.

The neo4j 5.x driver has no global "default tx timeout" knob — per-query timeout
is *only* via ``neo4j.Query(text, timeout=...)`` for ``session.run`` and
``session.begin_transaction(timeout=...)`` for explicit transactions. This module
applies one or the other automatically.

How the override works
----------------------

A ``contextvars.ContextVar`` carries an optional override that ``TimedSession``
resolves at each call. Two context managers set it:

- ``neo4j_query_timeout(seconds)`` — bound the enclosed query to ``seconds``
  (used by ``BulkUpsertBackend`` to grant ingestion the full 600s budget).
- ``unbounded_neo4j_query_timeout()`` — disable the timeout entirely (escape
  hatch for one-off long-running maintenance work).

Sentinel ``_UNSET`` distinguishes "no override set" (fall back to default) from
"explicitly unbounded" (``None``).

Inheritance: ``ContextVar`` values propagate across ``await`` and across
``asyncio.gather``; tasks created **inside** a ``with neo4j_query_timeout(...)``
block inherit the value at creation time. ``reset()`` on the token does NOT
reach into a still-running detached task, so callers must keep the awaited work
inside the block — SKUEL's ingestion path does not spawn detached tasks
mid-upsert, so this is not a hazard in practice.

Why ``Neo4jSchemaManager`` stays raw
-------------------------------------

``compose.py`` deliberately constructs ``Neo4jSchemaManager(raw_driver)`` (NOT
the wrapped driver) because startup DDL — vector index creation on the
``:Entity`` label, full-text indexes, domain indexes — can exceed the 120s
default on a large graph. A timed abort there would block bootstrap. Migration
and one-off index scripts that instantiate ``Neo4jConnection`` directly bypass
the wrapper for the same reason.

See:
    - services_bootstrap/compose.py (wrap site + raw_driver carve-out)
    - core/config/unified_config.py::DatabaseConfig.transaction_timeout
    - /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from neo4j import Query

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterator

    from neo4j import AsyncDriver

logger = get_logger("skuel.adapters.timed_driver")


# Sentinel: "no override set" — falls back to the driver's default_timeout.
# A plain ``None`` cannot serve as the sentinel because ``None`` IS a legal
# override value meaning "explicitly unbounded".
_UNSET: Any = object()

_timeout_override: ContextVar[Any] = ContextVar("neo4j_query_timeout_override", default=_UNSET)


@contextmanager
def neo4j_query_timeout(seconds: float | None) -> Iterator[None]:
    """Set a per-query server-side timeout for the enclosed block.

    ``seconds=None`` is treated as unbounded (use ``unbounded_neo4j_query_timeout``
    for readability). The override propagates across ``await`` and into tasks
    created inside the block; awaited work must complete inside the block, or
    its read of the ContextVar is undefined.
    """
    token = _timeout_override.set(seconds)
    try:
        yield
    finally:
        _timeout_override.reset(token)


@contextmanager
def unbounded_neo4j_query_timeout() -> Iterator[None]:
    """Disable the server-side timeout for the enclosed block.

    Escape hatch for one-off long-running maintenance work executed through the
    wrapped driver (e.g. an admin migration that exceeds the default).
    """
    token = _timeout_override.set(None)
    try:
        yield
    finally:
        _timeout_override.reset(token)


def _resolve_timeout(default: float | None) -> float | None:
    """Return the effective timeout: override if set, else the driver default."""
    override = _timeout_override.get()
    if override is _UNSET:
        return default
    # mypy: override is typed Any (sentinel union), narrow to float|None here.
    return override  # type: ignore[no-any-return]


def _as_timed_query(text: str, timeout: float | None) -> Query:
    """Build a ``neo4j.Query`` carrying the resolved timeout.

    ``Query`` wants a ``LiteralString`` for the text argument; the caller here
    passes a dynamic ``str`` (every backend in this layer composes Cypher from
    typed enum fragments — see ``ingestion_write_backend.py:54`` for the same
    pyright friction).
    """
    return Query(text, timeout=timeout)  # pyright: ignore[reportArgumentType]


class TimedSession:
    """Async session proxy that injects the resolved timeout into every query.

    Wraps the real ``AsyncSession``. ``__getattr__`` forwards anything not
    overridden here (``close``, ``last_bookmarks``, ``cancel``, ``execute_read``,
    ``execute_write``, etc.) so the proxy is transparent to callers.

    ``CypherExecutor`` is annotated ``session: AsyncSession`` and receives a
    ``TimedSession`` — this is duck-typed, not subclassed. SKUEL's mypy config
    disables ``arg-type`` globally, so the mismatch is silenced; pyright is
    warning-gate only.
    """

    def __init__(self, raw: Any, default_timeout: float | None) -> None:
        self._raw = raw
        self._default_timeout = default_timeout

    async def run(self, query: Any, parameters: Any = None, **kwargs: Any) -> Any:
        """Forward to ``session.run``, wrapping ``str`` queries with a timed ``Query``.

        A caller-supplied ``Query`` object is forwarded untouched — its own
        ``timeout`` (if any) wins over ours. The other ``run()`` parameter
        spellings (``query`` / parameters / kwargs) match the real driver.
        """
        if isinstance(query, str):
            query = _as_timed_query(query, _resolve_timeout(self._default_timeout))
        return await self._raw.run(query, parameters, **kwargs)

    async def begin_transaction(
        self,
        metadata: dict[str, Any] | None = None,
        timeout: float | None = None,  # noqa: ASYNC109 — mirrors AsyncSession.begin_transaction
        **kwargs: Any,
    ) -> Any:
        """Forward to ``session.begin_transaction``, injecting the default ``timeout`` if absent."""
        if timeout is None:
            timeout = _resolve_timeout(self._default_timeout)
        return await self._raw.begin_transaction(metadata=metadata, timeout=timeout, **kwargs)

    async def __aenter__(self) -> TimedSession:
        await self._raw.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self._raw.__aexit__(exc_type, exc, tb)

    def __getattr__(self, name: str) -> Any:
        # Only called when an attribute isn't found on the proxy itself.
        return getattr(self._raw, name)


class TimedDriver:
    """``AsyncDriver`` proxy that hands out ``TimedSession`` and wraps ``execute_query``.

    Constructed once at the composition root. ``session()`` mirrors the real
    driver's sync factory (returns an async-context-manager). ``execute_query``
    is the one-call path used by ``IngestionWriteBackend`` and is wrapped
    likewise. Anything else (``verify_connectivity``, ``get_server_info``,
    ``close``, ``encrypted``, etc.) forwards via ``__getattr__``.
    """

    def __init__(self, raw_driver: AsyncDriver, default_timeout: float | None) -> None:
        self._raw = raw_driver
        self._default_timeout = default_timeout
        logger.info(
            "✅ Driver wrapped with %ss server-side query timeout",
            default_timeout if default_timeout is not None else "unbounded",
        )

    def session(self, **session_config: Any) -> TimedSession:
        return TimedSession(self._raw.session(**session_config), self._default_timeout)

    async def execute_query(
        self,
        query_: Any,
        parameters_: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Forward to ``driver.execute_query``, wrapping ``str`` queries with a timed ``Query``."""
        if isinstance(query_, str):
            query_ = _as_timed_query(query_, _resolve_timeout(self._default_timeout))
        return await self._raw.execute_query(query_, parameters_, **kwargs)

    async def __aenter__(self) -> TimedDriver:
        await self._raw.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self._raw.__aexit__(exc_type, exc, tb)

    async def close(self) -> None:
        await self._raw.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


__all__ = [
    "TimedDriver",
    "TimedSession",
    "neo4j_query_timeout",
    "unbounded_neo4j_query_timeout",
]
