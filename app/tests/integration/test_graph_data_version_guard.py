"""The graph's data-version guard, on a real Neo4j (a testcontainer of its own).

``Neo4jConnection.connect`` refuses a graph that holds data unless the UTC
instants migration's record (``:MigrationRecord``) is in state ``applied``, and
stamps a graph it finds empty (``adapters/persistence/neo4j/graph_driver.py``).
The cases need a graph that is empty, then holds data with no record, then holds a
reverted record — which the shared container, full of the session's users, never
is — so this module runs on a container of its own (``scratch_neo4j_container``).

The last test is the other half of the contract: the shared container's
``clean_neo4j`` keeps the record, so a driver opened onto the graph after it
cleared still opens.

See: /docs/roadmap/utc-instants-arc.md § Migration contract (PR 4), step 7
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.graph_driver import (
    STAMPED_EMPTY,
    STATE_APPLIED,
    STATE_REVERTED,
    UTC_INSTANTS_MIGRATION,
    GraphNotMigratedError,
    open_async_driver,
)
from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.integration,
    pytest.mark.usefixtures("connection_settings"),
]


@pytest.fixture(scope="module")
def guard_container(scratch_neo4j_container: Any) -> Any:
    return scratch_neo4j_container


@pytest_asyncio.fixture(loop_scope="session")
async def raw(guard_container: Any) -> AsyncIterator[Any]:
    """An unguarded driver onto the guard container, emptied before each test."""
    driver = open_async_driver(guard_container.get_connection_url(), auth=("neo4j", "unused"))
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    yield driver
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    await driver.close()


async def _open(guard_container: Any, *, guard: bool = True) -> Neo4jConnection:
    connection = Neo4jConnection(
        uri=guard_container.get_connection_url(),
        username="neo4j",
        password="unused",
        utc_instants_guard=guard,
    )
    await connection.connect()
    return connection


async def _records(raw: Any) -> list[dict[str, Any]]:
    result = await raw.execute_query(
        "MATCH (r:MigrationRecord) RETURN r.name AS name, r.state AS state, r.stamped AS stamped"
    )
    return [dict(record) for record in result.records]


async def test_an_empty_graph_is_stamped_and_opens_again_after_a_restart(
    raw: Any, guard_container: Any
) -> None:
    first = await _open(guard_container)
    await first.close()
    assert await _records(raw) == [
        {"name": UTC_INSTANTS_MIGRATION, "state": STATE_APPLIED, "stamped": STAMPED_EMPTY}
    ]

    # The app writes, stops, and starts again: the graph holds data now, and
    # the record the empty graph was stamped with lets it open.
    await raw.execute_query("CREATE (:Entity:Task {uid: 'task.guard-probe', created_at: 'x'})")
    second = await _open(guard_container)
    await second.close()
    assert len(await _records(raw)) == 1


async def test_two_openers_of_one_empty_graph_write_one_record(
    raw: Any, guard_container: Any
) -> None:
    """Separate processes open a fresh graph at once: the record's name is unique, so one
    record is written and both open."""
    await raw.execute_query("DROP CONSTRAINT MigrationRecord_name_unique IF EXISTS")
    first, second = await asyncio.gather(_open(guard_container), _open(guard_container))
    await first.close()
    await second.close()
    assert len(await _records(raw)) == 1
    constraints = await raw.execute_query(
        "SHOW CONSTRAINTS YIELD labelsOrTypes, properties, type "
        "WHERE 'MigrationRecord' IN labelsOrTypes RETURN properties, type"
    )
    assert [(r["properties"], r["type"]) for r in constraints.records] == [
        (["name"], "NODE_PROPERTY_UNIQUENESS")
    ]


async def test_a_graph_holding_data_with_no_record_is_refused(
    raw: Any, guard_container: Any
) -> None:
    await raw.execute_query("CREATE (:Entity:Task {uid: 'task.unmigrated'})")
    with pytest.raises(GraphNotMigratedError, match="no MigrationRecord"):
        await _open(guard_container)
    assert await _records(raw) == [], "a refused graph is not stamped"


async def test_a_reverted_graph_is_refused(raw: Any, guard_container: Any) -> None:
    await raw.execute_query(
        "CREATE (:Entity:Task {uid: 'task.reverted'}) "
        "CREATE (:MigrationRecord {name: $name, state: $state})",
        name=UTC_INSTANTS_MIGRATION,
        state=STATE_REVERTED,
    )
    with pytest.raises(GraphNotMigratedError, match="'reverted'"):
        await _open(guard_container)


async def test_a_graph_recorded_twice_is_refused(raw: Any, guard_container: Any) -> None:
    # Two records can only predate the uniqueness constraint; drop it to build that graph.
    await raw.execute_query("DROP CONSTRAINT MigrationRecord_name_unique IF EXISTS")
    await raw.execute_query(
        "CREATE (:MigrationRecord {name: $name, state: $state}) "
        "CREATE (:MigrationRecord {name: $name, state: $state})",
        name=UTC_INSTANTS_MIGRATION,
        state=STATE_APPLIED,
    )
    with pytest.raises(GraphNotMigratedError, match="2 MigrationRecord"):
        await _open(guard_container)


async def test_an_applied_record_opens_a_graph_that_holds_data(
    raw: Any, guard_container: Any
) -> None:
    await raw.execute_query(
        "CREATE (:Entity:Task {uid: 'task.migrated'}) "
        "CREATE (:MigrationRecord {name: $name, state: $state})",
        name=UTC_INSTANTS_MIGRATION,
        state=STATE_APPLIED,
    )
    connection = await _open(guard_container)
    await connection.close()


async def test_the_migration_script_opens_an_unmigrated_graph(
    raw: Any, guard_container: Any
) -> None:
    """The one exempt opener: the script that writes the record must reach the graph first."""
    await raw.execute_query("CREATE (:Entity:Task {uid: 'task.before-cutover'})")
    connection = await _open(guard_container, guard=False)
    await connection.close()
    assert await _records(raw) == [], "the exempt opener neither checks nor stamps"


async def test_clean_neo4j_keeps_the_record(clean_neo4j: None, neo4j_driver: Any) -> None:
    """The shared graph is cleared between tests; a driver opened after it still opens."""
    result = await neo4j_driver.execute_query(
        "MATCH (r:MigrationRecord {name: $name}) RETURN r.state AS state",
        name=UTC_INSTANTS_MIGRATION,
    )
    assert [record["state"] for record in result.records] == [STATE_APPLIED]
