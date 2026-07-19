"""Session-run chokepoint shared by every Neo4j backend class.

``_run_single`` / ``_run_records`` replace hand-rolled
``async with self.driver.session()`` blocks for the two dominant shapes
(one statement → one record; one statement → record dicts), so session
lifecycle lives in exactly one place. Blocks that genuinely need the
session (multi-statement transactions, ``result.consume()`` counters,
cursor streaming) stay inline at their call sites. The closed-driver
teardown guard stays an explicit per-call-site opt-in
(``_is_driver_closed()``) — an implicit guard would make a closed driver
read as "no data".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, Record


class Neo4jSessionRunner:
    """Single-statement session helpers over ``self.driver``.

    Subclasses (the universal backend shell and the standalone backends)
    provide ``self.driver``; this class owns how a session is opened, run,
    and drained.
    """

    driver: AsyncDriver

    def _is_driver_closed(self) -> bool:
        """Check if the Neo4j driver has been closed.

        Used during test teardown to prevent "driver already closed" warnings.
        The ``_closed`` attribute is private to the Neo4j driver but is the
        recommended way to check driver state for graceful degradation.
        See: https://github.com/neo4j/neo4j-python-driver/issues/949
        """
        return getattr(self.driver, "_closed", False)

    async def _run_single(self, query: str, params: dict[str, Any] | None = None) -> Record | None:
        """Run one statement and return its single record (None when no row).

        No implicit closed-driver guard: a silently-empty read on a closed
        driver is indistinguishable from real data absence. The few teardown
        paths that want graceful degradation call ``_is_driver_closed()``
        explicitly before running.
        """
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return await result.single()

    async def _run_records(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Run one statement and return its records as dicts ([] when none).

        No implicit closed-driver guard — see ``_run_single``.
        """
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            records: list[dict[str, Any]] = await result.data()
            return records


__all__ = ["Neo4jSessionRunner"]
