"""
The Graph Driver — one construction site, two refusals
======================================================

Every Neo4j driver in the tree is built by ``open_async_driver``: the app's
connection (``Neo4jConnection``), every script, every test fixture. A test
(``tests/unit/test_graph_driver_construction_sites.py``) holds it that way — no
other file constructs ``AsyncGraphDatabase.driver`` or ``GraphDatabase.driver``.
Two checks live on this one path:

- **The process clock** (ADR-089). ``open_async_driver`` refuses a process whose
  clock is not pinned to UTC (``core/utils/process_clock.py``): a naive writer in
  an unpinned process stamps the host's wall clock, which a UTC corpus cannot
  tell from its own stamps.
- **The data version.** ``require_migration_records`` refuses a graph that holds
  data unless each whole-corpus migration the code reads it through has its
  record (``:MigrationRecord``) in state ``applied``. ``DATA_MIGRATIONS`` names
  them: the UTC instants migration (``UTC_INSTANTS``) — an un-migrated graph holds
  laptop-clock stamps the pinned code would read as UTC; and the uid grammar
  (``UID_GRAMMAR``) — an un-migrated graph holds uids in retired shapes, which
  the code reads as other nodes or as none (a default group no longer read as
  default, a periodic note minted twice). A graph that holds nothing (a fresh
  install, a test database) never held the old values, so it is stamped with
  every record it lacks at once and opens. ``Neo4jConnection.connect`` runs the
  check on every connection it opens; a script that brings a graph forward opens
  requiring only the records of the migrations before its own.

See: /docs/roadmap/utc-instants-arc.md § Migration contract (PR 4)
See: /docs/decisions/ADR-013-ku-uid-flat-identity.md § Amendment (2026-10-18)
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

#: The name the uid grammar's record carries.
UID_GRAMMAR_MIGRATION = "uid_grammar_2026_10"

#: Why an empty graph carries a record: it was stamped when first opened.
STAMPED_EMPTY = "empty graph"

_RECORD = NeoLabel.MIGRATION_RECORD.value


@dataclass(frozen=True)
class DataMigration:
    """A whole-corpus migration a graph must carry the applied record of to open.

    ``remedy`` tells an operator what the un-migrated graph holds and how to
    bring it forward.
    """

    name: str
    remedy: str


UTC_INSTANTS = DataMigration(
    name=UTC_INSTANTS_MIGRATION,
    remedy=(
        "The graph holds instants on the laptop's old clock, which this code reads as UTC. "
        "Migrate it in the deploy sitting (scripts/migrations/utc_instants_2026_10.py; "
        "docs/roadmap/utc-instants-arc.md § Migration contract), or run the code that "
        "predates the cutover against it."
    ),
)

UID_GRAMMAR = DataMigration(
    name=UID_GRAMMAR_MIGRATION,
    remedy=(
        "The graph may hold uids in shapes this code no longer mints or reads. Read it with "
        "./dev uid-census, move what it names with the uid migrations in order "
        "(scripts/migrations/chunk_and_content_uids_2026_10.py, periodic_note_uids_2026_10.py, "
        "generated_uids_2026_10.py, user_uids_2026_10.py), then stamp it: "
        "uv run scripts/migrations/uid_grammar_2026_10.py --confirm."
    ),
)

#: Every record a graph must carry to open, in the order the migrations ran.
DATA_MIGRATIONS: tuple[DataMigration, ...] = (UTC_INSTANTS, UID_GRAMMAR)

# One entry per record, a missing state kept as null: collect(r.state) would drop
# it, and a record with no state beside one that is applied would read as one.
_READ_RECORDS = f"""
OPTIONAL MATCH (r:{_RECORD}) WHERE r.name IN $names
WITH collect(r) AS records
RETURN [r IN records | {{name: r.name, state: r.state}}] AS records,
       EXISTS {{ MATCH (n) WHERE NOT n:{_RECORD} }} AS holds_data
"""

# The record's name is unique, so a MERGE on it writes one node however many
# processes race it — an empty graph opened by two at once included.
_RECORD_NAME_UNIQUE = f"""
CREATE CONSTRAINT {_RECORD}_name_unique IF NOT EXISTS
FOR (r:{_RECORD}) REQUIRE r.name IS UNIQUE
"""

# A record already there is left as it is: an empty graph with a reverted record
# stays refused.
_STAMP_EMPTY = f"""
UNWIND $names AS name
MERGE (r:{_RECORD} {{name: name}})
ON CREATE SET r.state = $applied, r.stamped = $stamped, r.applied_at = datetime()
"""


class ProcessClockNotPinnedError(RuntimeError):
    """A driver was asked for in a process whose clock is not pinned to UTC."""


class GraphNotMigratedError(RuntimeError):
    """The graph holds data and a migration the code requires is not applied to it."""


def open_async_driver(
    uri: str,
    *,
    auth: tuple[str, str | None] | None,
    **config: Any,  # boundary: neo4j driver keyword config (timeouts, pool size) — heterogeneous
) -> AsyncDriver:
    """Construct a Neo4j driver — refused unless the process clock is pinned to UTC.

    ``config`` passes through to ``AsyncGraphDatabase.driver`` (timeouts, pool
    size). The driver opens no connection here; the data-version check is
    ``require_migration_records``, which needs the server.
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
    # record name -> the state of each record carrying it; None where one has no state
    states: dict[str, list[str | None]]
    holds_data: bool


async def _read(tx: AsyncManagedTransaction, names: list[str]) -> _RecordRead:
    result = await tx.run(_READ_RECORDS, names=names)
    record = await result.single()
    states: dict[str, list[str | None]] = {}
    for entry in record["records"] if record else []:
        state = entry["state"]
        states.setdefault(str(entry["name"]), []).append(None if state is None else str(state))
    holds_data = bool(record["holds_data"]) if record else False
    return _RecordRead(states, holds_data)


async def _read_or_stamp(tx: AsyncManagedTransaction, names: list[str]) -> _RecordRead:
    read = await _read(tx, names)
    if read.holds_data:
        return read
    stamp = await tx.run(
        _STAMP_EMPTY,
        names=names,
        applied=MigrationState.APPLIED.value,
        stamped=STAMPED_EMPTY,
    )
    await stamp.consume()
    return await _read(tx, names)


def _refusal(migration: DataMigration, states: list[str | None]) -> str | None:
    """Why the graph's record of ``migration`` refuses it, or None when it is applied once."""
    if [MigrationState.from_stored(state) for state in states] == [MigrationState.APPLIED]:
        return None
    if not states:
        return f"Refusing a graph with no {_RECORD} named {migration.name!r}. {migration.remedy}"
    if len(states) > 1:
        return (
            f"Refusing a graph with {len(states)} {_RECORD} nodes named "
            f"{migration.name!r} (states {states}); there must be one."
        )
    return (
        f"Refusing a graph whose {_RECORD} {migration.name!r} is in state "
        f"{states[0]!r}, not {MigrationState.APPLIED.value!r}. {migration.remedy}"
    )


async def require_migration_records(
    driver: AsyncDriver, migrations: tuple[DataMigration, ...]
) -> None:
    """Refuse a graph that holds data unless each of ``migrations`` is applied to it.

    An empty graph is stamped with every record of ``migrations`` it lacks (state
    ``applied``) in the same transaction that found it empty, and opens; the
    records' name is made unique first, so two processes opening one empty graph
    at once write one record of each. An empty graph whose records already
    refuse it (a reverted one, one recorded twice) is refused unstamped. No
    migrations, no check.

    Raises:
        GraphNotMigratedError: the graph holds data and a record is missing,
            reverted, in another state, or recorded more than once — every such
            record named in the one message.
    """
    if not migrations:
        return
    names = [migration.name for migration in migrations]
    async with driver.session() as session:
        read = await session.execute_read(_read, names)
    if (
        not read.holds_data
        and any(name not in read.states for name in names)
        and not _refusals(migrations, read, recorded_only=True)
    ):
        await ensure_record_name_is_unique(driver)
        async with driver.session() as session:
            read = await session.execute_write(_read_or_stamp, names)
    refusals = _refusals(migrations, read, recorded_only=False)
    if refusals:
        raise GraphNotMigratedError("\n".join(refusals))


def _refusals(
    migrations: tuple[DataMigration, ...], read: _RecordRead, *, recorded_only: bool
) -> list[str]:
    """Each refusal ``read`` gives, in ``migrations`` order — of the recorded ones only, if asked."""
    return [
        refusal
        for migration in migrations
        if not (recorded_only and migration.name not in read.states)
        if (refusal := _refusal(migration, read.states.get(migration.name, [])))
    ]
