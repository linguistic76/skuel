"""The retired-link leftovers guard, against a real Neo4j.

``scripts/migrations/retired_link_leftovers_2026_10.py`` reads the graph for what the
Activity links arc's PR 5 retired — a ``PRACTICED_AT_EVENT`` edge, an Edge-file tracker
row naming the type, a tracker row whose ``authored_edges`` holds a key of the type, and
a node carrying ``aligned_principle_uids`` — lists each, and exits 2 while any is stored
(0 when none is). It never writes.

Each remnant kind is seeded alone into an otherwise clean graph, so each test shows the
census finds that kind by itself; the clean graph is the control. ``main()`` is run over
the test graph by standing in for its connection (it would otherwise open the graph
``.env`` names).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest

from adapters.persistence.neo4j import neo4j_connection

if TYPE_CHECKING:
    from neo4j import AsyncDriver

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts/migrations/retired_link_leftovers_2026_10.py"
)


def _load() -> ModuleType:
    """Import the script by path (``scripts/`` is not a package).

    Registered in ``sys.modules`` before it runs: ``@dataclass`` resolves the
    module's annotations through it.
    """
    spec = importlib.util.spec_from_file_location("retired_link_leftovers_2026_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()

MARK = "zzzretiredguard"
PRACTICED = "PRACTICED_AT_EVENT"
EVENT = f"event.{MARK}.event"
HABIT = f"habit.{MARK}.habit"
PRINCIPLE = f"principle.{MARK}.principle"
TASK = f"task.{MARK}.task"


# One driver record, keyed by RETURN alias; the values are heterogeneous Neo4j scalars.
type Row = dict[str, Any]  # boundary: raw neo4j records


async def _run(
    driver: AsyncDriver,
    query: str,
    **params: Any,  # boundary: neo4j query parameters
) -> list[Row]:
    async with driver.session() as session:
        return [dict(row) async for row in await session.run(query, **params)]


async def _seed_nodes(driver: AsyncDriver) -> None:
    """An event, a habit, a principle and a task — no edge, no tracker row."""
    for label, uid in (("Event", EVENT), ("Habit", HABIT), ("Principle", PRINCIPLE)):
        await _run(
            driver,
            f"CREATE (:Entity:{label} {{uid: $uid, title: $uid, status: 'active'}})",
            uid=uid,
        )
    await _run(
        driver,
        "CREATE (:Entity:Task {uid: $uid, title: $uid, status: 'active'})",
        uid=TASK,
    )


async def _snapshot(driver: AsyncDriver) -> tuple[list[Row], list[Row]]:
    """Every node's labels and properties, and every edge — what a write would change."""
    nodes = await _run(
        driver,
        "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props ORDER BY n.uid, n.file_path",
    )
    edges = await _run(
        driver,
        """
        MATCH (a)-[r]->(b)
        RETURN type(r) AS type, a.uid AS source, b.uid AS target, properties(r) AS props
        ORDER BY type, source, target
        """,
    )
    return nodes, edges


@pytest.fixture
async def graph(neo4j_driver, clean_neo4j) -> AsyncDriver:
    await _seed_nodes(neo4j_driver)
    return neo4j_driver


async def test_a_clean_graph_is_clean(graph: AsyncDriver) -> None:
    found = await guard.census(graph)

    assert found.clean
    assert (found.edges, found.edge_file_rows, found.tracker_keys, found.property_nodes) == (
        [],
        [],
        [],
        [],
    )


async def test_a_practiced_at_event_edge_from_a_principle_or_a_habit_is_listed(
    graph: AsyncDriver,
) -> None:
    for source in (PRINCIPLE, HABIT):
        await _run(
            graph,
            f"MATCH (a {{uid: $source}}), (e {{uid: $event}}) CREATE (a)-[:{PRACTICED}]->(e)",
            source=source,
            event=EVENT,
        )

    found = await guard.census(graph)

    assert not found.clean
    assert sorted((row["source_uid"], row["target_uid"]) for row in found.edges) == sorted(
        [(PRINCIPLE, EVENT), (HABIT, EVENT)]
    )
    assert (found.edge_file_rows, found.tracker_keys, found.property_nodes) == ([], [], [])


async def test_an_edge_file_tracker_row_naming_the_type_is_listed(graph: AsyncDriver) -> None:
    entity_uid = f"edge:{HABIT}|{PRACTICED}|{EVENT}"
    await _run(
        graph,
        "CREATE (:IngestionMetadata {file_path: $path, entity_uid: $entity_uid})",
        path=f"/vault/{MARK}-edge.yaml",
        entity_uid=entity_uid,
    )

    found = await guard.census(graph)

    assert not found.clean
    assert [row["entity_uid"] for row in found.edge_file_rows] == [entity_uid]
    assert (found.edges, found.tracker_keys, found.property_nodes) == ([], [], [])


async def test_a_tracker_row_holding_a_key_of_the_type_is_listed(graph: AsyncDriver) -> None:
    """The row's other key, of a live type, is not listed."""
    key = f"{PRACTICED}|outgoing|{EVENT}"
    await _run(
        graph,
        """
        CREATE (:IngestionMetadata {file_path: $path, entity_uid: $entity_uid,
                                    authored_edges: [$key, 'REINFORCES_HABIT|outgoing|x']})
        """,
        path=f"/vault/{MARK}-habit.md",
        entity_uid=HABIT,
        key=key,
    )

    found = await guard.census(graph)

    assert not found.clean
    assert [row["keys"] for row in found.tracker_keys] == [[key]]
    assert (found.edges, found.edge_file_rows, found.property_nodes) == ([], [], [])


async def test_a_task_carrying_aligned_principle_uids_is_listed(graph: AsyncDriver) -> None:
    await _run(
        graph,
        "MATCH (t {uid: $uid}) SET t.aligned_principle_uids = [$principle]",
        uid=TASK,
        principle=PRINCIPLE,
    )

    found = await guard.census(graph)

    assert not found.clean
    assert [(row["uid"], row["value"]) for row in found.property_nodes] == [(TASK, [PRINCIPLE])]
    assert (found.edges, found.edge_file_rows, found.tracker_keys) == ([], [], [])


class _Borrowed:
    """The test driver, lent to ``main()``: its ``close()`` leaves the fixture's driver open."""

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    async def execute_query(self, *args: Any, **kwargs: Any) -> Any:  # boundary: driver call
        return await self._driver.execute_query(*args, **kwargs)

    async def close(self) -> None:
        return None


def _lend(monkeypatch: pytest.MonkeyPatch, driver: AsyncDriver) -> None:
    """Make ``main()``'s ``Neo4jConnection().connect()`` return the test driver."""

    class _Connection:
        async def connect(self) -> _Borrowed:
            return _Borrowed(driver)

    monkeypatch.setattr(neo4j_connection, "Neo4jConnection", _Connection)


async def test_main_exits_0_on_a_clean_graph_and_2_on_a_remnant_and_writes_nothing(
    graph: AsyncDriver, monkeypatch: pytest.MonkeyPatch
) -> None:
    _lend(monkeypatch, graph)

    assert await guard.main() == 0

    await _run(
        graph,
        f"MATCH (h {{uid: $habit}}), (e {{uid: $event}}) CREATE (h)-[:{PRACTICED}]->(e)",
        habit=HABIT,
        event=EVENT,
    )
    await _run(
        graph,
        "MATCH (t {uid: $uid}) SET t.aligned_principle_uids = [$principle]",
        uid=TASK,
        principle=PRINCIPLE,
    )
    before = await _snapshot(graph)

    assert await guard.main() == 2
    assert await _snapshot(graph) == before
