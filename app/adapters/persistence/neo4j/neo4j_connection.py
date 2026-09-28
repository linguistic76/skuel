"""
Neo4j Connection Wrapper
========================

The app-wide Neo4j connection. ``get_connection()`` is the singleton accessor used
at the composition root (``services_bootstrap``) to build the shared ``AsyncDriver``,
and ``Neo4jConnection`` is also instantiated directly by migration / index scripts.

``connect()`` opens the graph in three steps: the driver is built by
``open_async_driver`` (``graph_driver.py`` — refused unless the process clock is
pinned to UTC), the server is probed until it answers (``connect_with_retry`` — a
paused AuraDB Free instance wakes), and the graph's data version is checked
(``require_utc_instants`` — a graph holding data the UTC instants migration has
not been applied to is refused; an empty one is stamped). Only the migration
script opens without the last step (``utc_instants_guard=False``).

Driver-level timeouts and pool sizing come from ``DatabaseConfig`` and are applied
where the driver is built. These bound connection establishment,
pool acquisition, and managed-transaction retry — they do NOT cap a single query's
execution time. The per-query server-side timeout (``neo4j.Query(timeout=)``) is
applied a layer up: ``services_bootstrap/compose.py`` wraps the shared driver with
``TimedDriver`` (see ``timed_driver.py``), which injects the timeout on every
``session.run`` / ``begin_transaction`` / ``execute_query`` it hands out.

``Neo4jConnection`` itself stays raw on purpose: migration and one-off index
scripts that instantiate it directly run DDL (vector / full-text / domain indexes)
that can legitimately exceed the default 120s budget, and a server-side abort
there would be wrong.
"""

__version__ = "1.0"


import asyncio
import os
from typing import Any

from neo4j import AsyncDriver, Record

from adapters.persistence.neo4j.graph_driver import open_async_driver, require_utc_instants
from core.config.settings import get_settings
from core.constants import Neo4jConnectRetry

# Protocols
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

logger = get_logger(__name__)

_connection_instance = None
# One opener at a time: two concurrent first calls would otherwise build two drivers.
_connection_lock = asyncio.Lock()


class Neo4jConnection:
    """Neo4j connection wrapper backing the app-wide ``get_connection()`` singleton.

    Also instantiated directly by scripts. Applies driver-level timeout / pool config
    from ``DatabaseConfig``.
    """

    def __init__(
        self,
        uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        *,
        utc_instants_guard: bool = True,
    ) -> None:
        """
        Initialize Neo4j connection.

        Args:
            uri: Neo4j URI (defaults to env/settings)
            username: Neo4j username (defaults to env/settings)
            password: Neo4j password (defaults to encrypted credential store)
            utc_instants_guard: check the graph's data version on connect —
                False only for the UTC instants migration script, which
                writes the record the check reads
        """
        from core.config.credential_store import get_credential

        settings = get_settings()
        db_config = getattr(settings, "database", settings)

        self.uri: str = str(
            uri
            or getattr(db_config, "neo4j_uri", None)
            or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        )
        self.username: str = str(
            username
            or getattr(db_config, "neo4j_username", None)
            or get_credential("NEO4J_USERNAME", fallback_to_env=True)
            or get_credential("NEO4J_USER", fallback_to_env=True)
            or "neo4j"
        )

        # Use encrypted credential store for password (with env fallback for migration)
        self.password: str | None = (
            password
            or getattr(db_config, "neo4j_password", None)
            or get_credential("NEO4J_PASSWORD", fallback_to_env=True)
        )

        # Driver-level timeouts / pool config from DatabaseConfig (Stage-agnostic,
        # .env-tunable). Bounds connection establishment, pool acquisition, and
        # managed-transaction retry — NOT a single query's execution time.
        self._driver_config: dict[str, Any] = {
            "connection_timeout": float(getattr(db_config, "connection_timeout", 30.0)),
            "connection_acquisition_timeout": float(
                getattr(db_config, "connection_acquisition_timeout", 60.0)
            ),
            "max_transaction_retry_time": float(getattr(db_config, "max_retry_time", 30.0)),
            "max_connection_pool_size": int(getattr(db_config, "max_connection_pool_size", 50)),
            "max_connection_lifetime": int(getattr(db_config, "max_connection_lifetime", 3600)),
        }

        self.driver: AsyncDriver | None = None
        self._utc_instants_guard = utc_instants_guard
        self._opened = False

    def _build_driver(self) -> AsyncDriver:
        """The driver, built on first use — refused unless the process clock is pinned."""
        if self.driver is None:
            self.driver = open_async_driver(
                self.uri, auth=(self.username, self.password), **self._driver_config
            )
        return self.driver

    async def connect(self) -> AsyncDriver:
        """Open the graph and return the live driver.

        Builds the driver, probes the server until it answers (bounded retry — a
        paused AuraDB Free instance takes a few seconds to wake), then checks the
        graph's data version unless this connection is the migration script's.
        A failure closes the driver, so the next call starts over.
        """
        if self._opened and self.driver is not None:
            return self.driver
        driver = self._build_driver()
        try:
            await connect_with_retry(
                self,
                max_attempts=Neo4jConnectRetry.MAX_ATTEMPTS,
                base_delay_seconds=Neo4jConnectRetry.BASE_DELAY_SECONDS,
                max_delay_seconds=Neo4jConnectRetry.MAX_DELAY_SECONDS,
            )
            if self._utc_instants_guard:
                await require_utc_instants(driver)
            self._opened = True
        finally:
            if not self._opened:
                await self.close()
        logger.info(
            "Connected to Neo4j at %s (connection_timeout=%ss, acquisition_timeout=%ss, "
            "max_transaction_retry_time=%ss, pool=%s)",
            self.uri,
            self._driver_config["connection_timeout"],
            self._driver_config["connection_acquisition_timeout"],
            self._driver_config["max_transaction_retry_time"],
            self._driver_config["max_connection_pool_size"],
        )
        return driver

    async def close(self):
        """Close the connection."""
        self._opened = False
        if self.driver:
            await self.driver.close()
            self.driver = None
            logger.info("Closed Neo4j connection")

    async def __aenter__(self) -> Neo4jConnection:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def probe_connectivity(self) -> None:
        """Verify the server is reachable AND queryable — raise if not.

        Runs ``RETURN 1`` (a stronger check than the driver's routing-only
        ``verify_connectivity``: it confirms the database is actually resumed and
        answering, which matters for an AuraDB Free instance waking from pause).
        Propagates ``NEO4J_EXCEPTIONS`` (incl. ``ServiceUnavailable``) so callers
        — notably ``connect_with_retry``, which ``connect`` runs — can back off
        and retry.
        """
        driver = self._build_driver()
        async with driver.session() as session:
            result = await session.run("RETURN 1 as test")
            data = await result.single()
        if data is None or data["test"] != 1:
            raise RuntimeError("Neo4j connectivity probe returned no result")

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[Record] | None:
        """
        Execute a Cypher query.

        Args:
            query: Cypher query string,
            params: Query parameters

        Returns:
            List of Neo4j Record objects, or None if error
        """
        try:
            driver = await self.connect()
            async with driver.session() as session:
                result = await session.run(query, params or {})
                # Collect all records as Record objects
                return [record async for record in result]

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query[:200]}...")
            return None


async def get_connection() -> Neo4jConnection:
    """
    Get or create the singleton Neo4j connection, opened.

    Returns:
        Neo4jConnection instance
    """
    global _connection_instance

    async with _connection_lock:
        if _connection_instance is None:
            connection = Neo4jConnection()
            await connection.connect()
            _connection_instance = connection

    return _connection_instance


async def connect_with_retry(
    connection: Neo4jConnection,
    *,
    max_attempts: int,
    base_delay_seconds: float,
    max_delay_seconds: float,
) -> None:
    """Probe Neo4j with bounded exponential backoff; raise a clear error if it stays down.

    ADR-080 Horizon 0: AuraDB Free auto-pauses on inactivity and takes a few
    seconds to resume on the next connection. Without retry, bootstrap would die
    on a bare ``ServiceUnavailable`` the instant it hit a paused instance. This
    retries ``connection.probe_connectivity()`` (a ``RETURN 1`` check) so a waking
    instance is tolerated, logging each attempt; after ``max_attempts`` it raises
    one actionable ``RuntimeError``.

    Run by ``Neo4jConnection.connect`` — every opener inherits it. Startup-only:
    deep live-request reconnect / circuit-breaker across query sites is
    deliberately deferred (ADR-080 "When to Revisit").

    Delay before attempt *n* (1-indexed) is
    ``min(base_delay_seconds * 2**(n-1), max_delay_seconds)``.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            await connection.probe_connectivity()
            if attempt > 1:
                logger.info("Neo4j reachable on attempt %d/%d — proceeding.", attempt, max_attempts)
            return
        except NEO4J_EXCEPTIONS as e:
            last_error = e
            if attempt >= max_attempts:
                break
            delay = min(base_delay_seconds * (2 ** (attempt - 1)), max_delay_seconds)
            logger.warning(
                "Neo4j not ready (attempt %d/%d): %s. Retrying in %.1fs "
                "(an AuraDB Free instance may be waking from pause)...",
                attempt,
                max_attempts,
                e,
                delay,
            )
            await asyncio.sleep(delay)

    raise RuntimeError(
        f"Neo4j unreachable after {max_attempts} attempts: {last_error}. "
        "If this is AuraDB Free, the instance may be paused — resume it in the "
        "Aura console; otherwise verify NEO4J_URI, credentials, and network reachability."
    ) from last_error
