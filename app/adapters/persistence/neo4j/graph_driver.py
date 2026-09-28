"""
The Graph Driver — one construction site, two refusals
======================================================

Every Neo4j driver in the tree is built by ``open_async_driver``: the app's
connection (``Neo4jConnection``), every script, every test fixture. A test
(``tests/unit/test_graph_driver_construction_sites.py``) holds it that way — no
other file constructs ``AsyncGraphDatabase.driver`` or ``GraphDatabase.driver``.
Two checks live on this one path (ADR-089; the UTC Instants arc's cutover):

- **The process clock.** ``open_async_driver`` refuses a process whose clock is
  not pinned to UTC (``core/utils/process_clock.py``): a naive writer in an
  unpinned process stamps the host's wall clock, which a UTC corpus cannot tell
  from its own stamps.
- **The data version.** ``require_utc_instants`` refuses a graph that holds data
  unless the UTC instants migration's record (``:MigrationRecord``, named
  ``UTC_INSTANTS_MIGRATION``) is in state ``applied``: a graph never migrated —
  a restored snapshot, a reverted migration — holds laptop-clock stamps that the
  pinned code would read as UTC and mix with its own. A graph that holds nothing
  (a fresh install, a test database) never held the old clock, so it is stamped
  with the record at once and opens. ``Neo4jConnection.connect`` runs the check
  on every connection it opens; the migration script is the one opener exempt
  from it, since it is what writes the record.

See: /docs/roadmap/utc-instants-arc.md § Migration contract (PR 4)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from neo4j import AsyncGraphDatabase

from core.models.enums.migration_enums import MigrationState
from core.models.enums.neo_labels import NeoLabel
from core.utils.process_clock import process_clock_is_pinned

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction

#: The name the UTC instants migration's record carries.
UTC_INSTANTS_MIGRATION = "utc_instants_2026_10"

#: Why an empty graph carries the record: it was stamped when first opened.
STAMPED_EMPTY = "empty graph"

_RECORD = NeoLabel.MIGRATION_RECORD.value

_READ_RECORD = f"""
OPTIONAL MATCH (r:{_RECORD} {{name: $name}})
WITH collect(r.state) AS states
RETURN states, EXISTS {{ MATCH (n) WHERE NOT n:{_RECORD} }} AS holds_data
"""

# The record's name is unique, so a MERGE on it writes one node however many
# processes race it — an empty graph opened by two at once included.
_RECORD_NAME_UNIQUE = f"""
CREATE CONSTRAINT {_RECORD}_name_unique IF NOT EXISTS
FOR (r:{_RECORD}) REQUIRE r.name IS UNIQUE
"""

_STAMP_EMPTY = f"""
MERGE (r:{_RECORD} {{name: $name}})
ON CREATE SET r.state = $applied, r.stamped = $stamped, r.applied_at = datetime()
RETURN r.state AS state
"""


class ProcessClockNotPinnedError(RuntimeError):
    """A driver was asked for in a process whose clock is not pinned to UTC."""


class GraphNotMigratedError(RuntimeError):
    """The graph holds data and the UTC instants migration is not applied to it."""


def open_async_driver(
    uri: str,
    *,
    auth: tuple[str, str | None] | None,
    **config: Any,  # boundary: neo4j driver keyword config (timeouts, pool size) — heterogeneous
) -> AsyncDriver:
    """Construct a Neo4j driver — refused unless the process clock is pinned to UTC.

    ``config`` passes through to ``AsyncGraphDatabase.driver`` (timeouts, pool
    size). The driver opens no connection here; the data-version check is
    ``require_utc_instants``, which needs the server.
    """
    if not process_clock_is_pinned():
        raise ProcessClockNotPinnedError(
            "Refusing to open a Neo4j driver: the process clock is not pinned to UTC. "
            "Every entry point calls pin_process_clock_to_utc() "
            "(core/utils/process_clock.py) before it reads a clock — this one did not, "
            "and its naive stamps would carry the host's wall clock into a UTC graph."
        )
    return AsyncGraphDatabase.driver(uri, auth=auth, **config)


async def _create_record_name_constraint(tx: AsyncManagedTransaction) -> None:
    result = await tx.run(_RECORD_NAME_UNIQUE)
    await result.consume()


async def ensure_record_name_is_unique(driver: AsyncDriver) -> None:
    """Create the uniqueness constraint on the record's name, when it is missing.

    Run before any write that MERGEs the record — a schema change cannot share a
    transaction with data writes. A managed transaction, so the deadlock two
    concurrent creators can hit is retried rather than raised.
    """
    async with driver.session() as session:
        await session.execute_write(_create_record_name_constraint)


@dataclass(frozen=True)
class _RecordRead:
    states: list[str]
    holds_data: bool
    stamped: bool


async def _read(tx: AsyncManagedTransaction) -> _RecordRead:
    result = await tx.run(_READ_RECORD, name=UTC_INSTANTS_MIGRATION)
    record = await result.single()
    states = [str(state) for state in (record["states"] if record else [])]
    holds_data = bool(record["holds_data"]) if record else False
    return _RecordRead(states, holds_data, stamped=False)


async def _read_or_stamp(tx: AsyncManagedTransaction) -> _RecordRead:
    read = await _read(tx)
    if read.states or read.holds_data:
        return read
    stamp = await tx.run(
        _STAMP_EMPTY,
        name=UTC_INSTANTS_MIGRATION,
        applied=MigrationState.APPLIED.value,
        stamped=STAMPED_EMPTY,
    )
    stamped = await stamp.single()
    return _RecordRead([str(stamped["state"])] if stamped else [], False, stamped=True)


async def require_utc_instants(driver: AsyncDriver) -> None:
    """Refuse a graph that holds data unless the UTC instants migration is applied to it.

    An empty graph is stamped with the record (state ``applied``) in the same
    transaction that found it empty, and opens; the record's name is made unique
    first, so two processes opening one empty graph at once write one record.

    Raises:
        GraphNotMigratedError: the graph holds data and the record is missing,
            reverted, in another state, or recorded more than once.
    """
    async with driver.session() as session:
        read = await session.execute_read(_read)
    if not read.states and not read.holds_data:
        await ensure_record_name_is_unique(driver)
        async with driver.session() as session:
            read = await session.execute_write(_read_or_stamp)
    states = [MigrationState.from_stored(state) for state in read.states]
    if states == [MigrationState.APPLIED]:
        return
    remedy = (
        "The graph holds instants on the laptop's old clock, which this code reads as UTC. "
        "Migrate it in the deploy sitting (scripts/migrations/utc_instants_2026_10.py; "
        "docs/roadmap/utc-instants-arc.md § Migration contract), or run the code that "
        "predates the cutover against it."
    )
    if not read.states:
        raise GraphNotMigratedError(
            f"Refusing a graph with no {_RECORD} named {UTC_INSTANTS_MIGRATION!r}. {remedy}"
        )
    if len(read.states) > 1:
        raise GraphNotMigratedError(
            f"Refusing a graph with {len(read.states)} {_RECORD} nodes named "
            f"{UTC_INSTANTS_MIGRATION!r} (states {read.states}); there must be one."
        )
    raise GraphNotMigratedError(
        f"Refusing a graph whose {_RECORD} {UTC_INSTANTS_MIGRATION!r} is in state "
        f"{read.states[0]!r}, not {MigrationState.APPLIED.value!r}. {remedy}"
    )
