"""The graph's data-version guard, on a real Neo4j (a testcontainer of its own).

``Neo4jConnection.connect`` refuses a graph that holds data unless each record
it requires (``:MigrationRecord`` — the UTC instants migration's and the uid
grammar's, ``DATA_MIGRATIONS``) is in state ``applied``, and stamps a graph it
finds empty with every one it lacks (``adapters/persistence/neo4j/graph_driver.py``).
The cases need a graph that is empty, then holds data with no record, then holds a
reverted record — which the shared container, full of the session's users, never
is — so this module runs on a container of its own (``scratch_neo4j_container``).

The last test is the other half of the contract: the shared container's
``clean_neo4j`` keeps the records, so a driver opened onto the graph after it
cleared still opens.

See: /docs/roadmap/utc-instants-arc.md § Migration contract (PR 4), step 7
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.graph_driver import (
    DATA_MIGRATIONS,
    STAMPED_EMPTY,
    UID_GRAMMAR_MIGRATION,
    UTC_INSTANTS,
    UTC_INSTANTS_MIGRATION,
    DataMigration,
    GraphNotMigratedError,
    open_async_driver,
)
from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.models.enums.migration_enums import MigrationState

if TYPE_CHECKING:
    from neo4j import AsyncDriver
    from testcontainers.community.neo4j import Neo4jContainer  # type: ignore[import-untyped]

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.integration,
    pytest.mark.usefixtures("connection_settings"),
]


@pytest.fixture(scope="module")
def guard_container(scratch_neo4j_container: Neo4jContainer) -> Neo4jContainer:
    return scratch_neo4j_container


@pytest_asyncio.fixture(loop_scope="session")
async def raw(guard_container: Neo4jContainer) -> AsyncIterator[AsyncDriver]:
    """An unguarded driver onto the guard container, emptied before each test."""
    driver = open_async_driver(guard_container.get_connection_url(), auth=("neo4j", "unused"))
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    yield driver
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    await driver.close()


async def _open(
    guard_container: Neo4jContainer, *, requires: tuple[DataMigration, ...] = DATA_MIGRATIONS
) -> Neo4jConnection:
    connection = Neo4jConnection(
        uri=guard_container.get_connection_url(),
        username="neo4j",
        password="unused",
        requires=requires,
    )
    await connection.connect()
    return connection


async def _records(raw: AsyncDriver) -> list[dict[str, object]]:
    result = await raw.execute_query(
        "MATCH (r:MigrationRecord) RETURN r.name AS name, r.state AS state, r.stamped AS stamped "
        "ORDER BY name"
    )
    return [dict(record) for record in result.records]


def _stamped(*names: str) -> list[dict[str, object]]:
    return [
        {"name": name, "state": MigrationState.APPLIED, "stamped": STAMPED_EMPTY}
        for name in sorted(names)
    ]


async def _applied(raw: AsyncDriver, *names: str) -> None:
    await raw.execute_query(
        "UNWIND $names AS name CREATE (:MigrationRecord {name: name, state: $state})",
        names=list(names),
        state=MigrationState.APPLIED,
    )


async def test_an_empty_graph_is_stamped_and_opens_again_after_a_restart(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    first = await _open(guard_container)
    await first.close()
    assert await _records(raw) == _stamped(UTC_INSTANTS_MIGRATION, UID_GRAMMAR_MIGRATION)

    # The app writes, stops, and starts again: the graph holds data now, and
    # the records the empty graph was stamped with let it open.
    await raw.execute_query("CREATE (:Entity:Task {uid: 'task.guard-probe', created_at: 'x'})")
    second = await _open(guard_container)
    await second.close()
    assert len(await _records(raw)) == 2


async def test_an_empty_graph_a_uid_script_opened_is_stamped_with_the_rest_by_the_app(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    """A script that requires only the UTC record stamps only it; the app's open stamps the uid
    grammar's, the graph still holding nothing."""
    script = await _open(guard_container, requires=(UTC_INSTANTS,))
    await script.close()
    assert await _records(raw) == _stamped(UTC_INSTANTS_MIGRATION)
    app = await _open(guard_container)
    await app.close()
    assert await _records(raw) == _stamped(UTC_INSTANTS_MIGRATION, UID_GRAMMAR_MIGRATION)


async def test_two_openers_of_one_empty_graph_write_one_record(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    """Separate processes open a fresh graph at once: the record's name is unique, so one
    record is written and both open."""
    await raw.execute_query("DROP CONSTRAINT MigrationRecord_name_unique IF EXISTS")
    first, second = await asyncio.gather(_open(guard_container), _open(guard_container))
    await first.close()
    await second.close()
    assert await _records(raw) == _stamped(UTC_INSTANTS_MIGRATION, UID_GRAMMAR_MIGRATION)
    constraints = await raw.execute_query(
        "SHOW CONSTRAINTS YIELD labelsOrTypes, properties, type "
        "WHERE 'MigrationRecord' IN labelsOrTypes RETURN properties, type"
    )
    assert [(r["properties"], r["type"]) for r in constraints.records] == [
        (["name"], "NODE_PROPERTY_UNIQUENESS")
    ]


async def test_a_graph_holding_data_with_no_record_is_refused(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    await raw.execute_query("CREATE (:Entity:Task {uid: 'task.unmigrated'})")
    with pytest.raises(GraphNotMigratedError) as refused:
        await _open(guard_container)
    for name in (UTC_INSTANTS_MIGRATION, UID_GRAMMAR_MIGRATION):
        assert f"no MigrationRecord named {name!r}" in str(refused.value)
    assert await _records(raw) == [], "a refused graph is not stamped"


async def test_a_graph_holding_data_without_the_uid_record_is_refused_with_its_remedy(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    """A graph from before the uid grammar's close — the UTC record applied, no uid record."""
    await raw.execute_query("CREATE (:Entity:Group {uid: 'group_default_user_admin'})")
    await _applied(raw, UTC_INSTANTS_MIGRATION)
    with pytest.raises(GraphNotMigratedError) as refused:
        await _open(guard_container)
    message = str(refused.value)
    assert f"no MigrationRecord named {UID_GRAMMAR_MIGRATION!r}" in message
    assert UTC_INSTANTS_MIGRATION not in message
    assert "uid_grammar_2026_10.py --confirm" in message


async def test_a_uid_script_opens_a_graph_without_the_uid_record(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    """The census, the stamp and the uid migrations open before the record exists."""
    await raw.execute_query("CREATE (:Entity:Group {uid: 'group_default_user_admin'})")
    await _applied(raw, UTC_INSTANTS_MIGRATION)
    connection = await _open(guard_container, requires=(UTC_INSTANTS,))
    await connection.close()
    assert [record["name"] for record in await _records(raw)] == [UTC_INSTANTS_MIGRATION]


async def test_a_reverted_graph_is_refused(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    await raw.execute_query(
        "CREATE (:Entity:Task {uid: 'task.reverted'}) "
        "CREATE (:MigrationRecord {name: $name, state: $state})",
        name=UTC_INSTANTS_MIGRATION,
        state=MigrationState.REVERTED,
    )
    with pytest.raises(GraphNotMigratedError, match="'reverted'"):
        await _open(guard_container)


async def test_a_graph_recorded_twice_is_refused(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    # Two records can only predate the uniqueness constraint; drop it to build that graph.
    await raw.execute_query("DROP CONSTRAINT MigrationRecord_name_unique IF EXISTS")
    await raw.execute_query(
        "CREATE (:MigrationRecord {name: $name, state: $state}) "
        "CREATE (:MigrationRecord {name: $name, state: $state})",
        name=UTC_INSTANTS_MIGRATION,
        state=MigrationState.APPLIED,
    )
    with pytest.raises(GraphNotMigratedError, match="2 MigrationRecord"):
        await _open(guard_container)


async def test_a_stateless_record_beside_an_applied_one_is_refused(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    """A record with no state still counts: two records, not one applied."""
    await raw.execute_query("DROP CONSTRAINT MigrationRecord_name_unique IF EXISTS")
    await raw.execute_query(
        "CREATE (:Entity:Task {uid: 'task.stateless'}) "
        "CREATE (:MigrationRecord {name: $name, state: $state}) "
        "CREATE (:MigrationRecord {name: $name})",
        name=UTC_INSTANTS_MIGRATION,
        state=MigrationState.APPLIED,
    )
    with pytest.raises(GraphNotMigratedError, match="2 MigrationRecord"):
        await _open(guard_container)


async def test_applied_records_open_a_graph_that_holds_data(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    await raw.execute_query("CREATE (:Entity:Task {uid: 'task.migrated'})")
    await _applied(raw, UTC_INSTANTS_MIGRATION, UID_GRAMMAR_MIGRATION)
    connection = await _open(guard_container)
    await connection.close()


async def test_the_utc_migration_script_opens_an_unmigrated_graph(
    raw: AsyncDriver, guard_container: Neo4jContainer
) -> None:
    """The opener that requires no record: the UTC migration, the first of them, must reach
    the graph before any record exists."""
    await raw.execute_query("CREATE (:Entity:Task {uid: 'task.before-cutover'})")
    connection = await _open(guard_container, requires=())
    await connection.close()
    assert await _records(raw) == [], "an opener requiring nothing neither checks nor stamps"


async def test_clean_neo4j_keeps_the_records(clean_neo4j: None, neo4j_driver: AsyncDriver) -> None:
    """The shared graph is cleared between tests; a driver opened after it still opens."""
    result = await neo4j_driver.execute_query(
        "MATCH (r:MigrationRecord) RETURN r.name AS name, r.state AS state ORDER BY name"
    )
    assert [(record["name"], record["state"]) for record in result.records] == [
        (name, MigrationState.APPLIED)
        for name in sorted((UTC_INSTANTS_MIGRATION, UID_GRAMMAR_MIGRATION))
    ]
