"""The uid grammar's close, on a real Neo4j (a testcontainer of its own).

Two readers of one verdict: the census script's, read in Python by ``classify``
(``scripts/uid_census.py``), which gates the stamp
(``scripts/migrations/uid_grammar_2026_10.py``); and the graph-health poller's,
filtered on the server by ``UID_PATTERN`` (``UidCensusBackend.read_breaches``).
The first test holds the two to one reading of every sample the grammar's unit
tests classify — Cypher's ``=~`` is Java's regex, not Python's. The rest run the
stamp's sitting: refused while a uid is outside the grammar, a census that writes
nothing, ``--confirm``, a re-run that leaves the record, the app's open after it.

The census reads the WHOLE graph, so the module runs on a container of its own.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.graph_driver import (
    UID_GRAMMAR_MIGRATION,
    UTC_INSTANTS_MIGRATION,
    DataMigration,
    open_async_driver,
)
from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.models.enums.migration_enums import MigrationState
from tests.helpers.production_backends import build_production_backends
from tests.unit.utils.test_uid_grammar import FITTING, OUTSIDE, SHAPE_ONLY

if TYPE_CHECKING:
    from neo4j import AsyncDriver
    from testcontainers.community.neo4j import Neo4jContainer  # type: ignore[import-untyped]

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.integration,
    pytest.mark.usefixtures("connection_settings"),
]

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/migrations/uid_grammar_2026_10.py"


def _load() -> ModuleType:
    """Import the script by path (``scripts/migrations/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("uid_grammar_2026_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


stamp = _load()


@pytest_asyncio.fixture(loop_scope="session")
async def graph(scratch_neo4j_container: Neo4jContainer) -> AsyncIterator[AsyncDriver]:
    """A driver onto the scratch container, emptied but for an applied UTC record."""
    driver = open_async_driver(
        scratch_neo4j_container.get_connection_url(), auth=("neo4j", "unused")
    )
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    await driver.execute_query(
        "CREATE (:MigrationRecord {name: $name, state: $state})",
        name=UTC_INSTANTS_MIGRATION,
        state=MigrationState.APPLIED,
    )
    yield driver
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    await driver.close()


@pytest.fixture
def to_the_scratch_graph(
    scratch_neo4j_container: Neo4jContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``main()``'s ``Neo4jConnection`` opens the scratch container."""
    import adapters.persistence.neo4j.neo4j_connection as connection

    uri = scratch_neo4j_container.get_connection_url()

    def opener(*, requires: tuple[DataMigration, ...]) -> Neo4jConnection:
        return Neo4jConnection(uri=uri, username="neo4j", password="unused", requires=requires)

    monkeypatch.setattr(connection, "Neo4jConnection", opener)


async def _uid_record(graph: AsyncDriver) -> list[dict[str, object]]:
    result = await graph.execute_query(
        "MATCH (r:MigrationRecord {name: $name}) "
        "RETURN r.state AS state, r.stamped AS stamped, r.uids AS uids",
        name=UID_GRAMMAR_MIGRATION,
    )
    return [dict(record) for record in result.records]


async def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    code = await stamp.main(list(args))
    return code, capsys.readouterr().out


async def test_the_server_filter_reads_every_sample_as_classify_does(graph: AsyncDriver) -> None:
    misfits = [*OUTSIDE, *SHAPE_ONLY]
    await graph.execute_query(
        "UNWIND $uids AS uid CREATE (:Probe {uid: uid})", uids=[*FITTING, *misfits]
    )
    # A uid that is not a string, and one two nodes hold.
    await graph.execute_query(
        "CREATE (:Probe {uid: 7}) CREATE (:Entity:Task {uid: 'task.shared'}) "
        "CREATE (:Group {uid: 'task.shared'})"
    )
    backend = build_production_backends(graph)["uid_census_backend"]
    breaches = (await backend.read_breaches(sample=100)).value
    assert breaches.outside == len(misfits) + 1
    assert sorted(breaches.outside_sample) == sorted(
        [f"Probe {uid}" for uid in misfits] + ["Probe 7"]
    )
    assert (breaches.shared, breaches.shared_sample) == (1, ("task.shared",))


async def test_a_graph_that_fits_reads_no_breach(graph: AsyncDriver) -> None:
    await graph.execute_query("UNWIND $uids AS uid CREATE (:Probe {uid: uid})", uids=FITTING)
    backend = build_production_backends(graph)["uid_census_backend"]
    breaches = (await backend.read_breaches(sample=5)).value
    assert (breaches.outside, breaches.shared) == (0, 0)


@pytest.mark.usefixtures("to_the_scratch_graph")
@pytest.mark.outside_uid_grammar(
    "seeds a group uid outside the grammar on a scratch container", static_only=True
)
async def test_the_stamp_waits_on_a_census_that_passes(
    graph: AsyncDriver, capsys: pytest.CaptureFixture[str]
) -> None:
    await graph.execute_query(
        "CREATE (:Entity:Task {uid: 'task_3f9a0c41d2e87b65'}) "
        "CREATE (:Entity:Group {uid: 'group_default_user_admin'})"
    )
    code, out = await _run(capsys, "--confirm")
    assert code == 2 and "STOP: the census fails" in out, out
    assert await _uid_record(graph) == [], "a failing census writes nothing"

    await graph.execute_query("MATCH (g:Group) DETACH DELETE g")
    code, out = await _run(capsys)
    assert code == 0 and "CENSUS ONLY" in out, out
    assert await _uid_record(graph) == [], "the census alone writes nothing"

    code, out = await _run(capsys, "--confirm")
    assert code == 0 and "Stamped" in out, out
    assert await _uid_record(graph) == [
        {"state": MigrationState.APPLIED, "stamped": stamp.STAMPED_BY_CENSUS, "uids": 1}
    ]

    code, out = await _run(capsys, "--confirm")
    assert code == 0 and "already applied" in out, out
    assert len(await _uid_record(graph)) == 1


@pytest.mark.usefixtures("to_the_scratch_graph")
async def test_the_app_opens_the_graph_once_it_is_stamped(
    graph: AsyncDriver, scratch_neo4j_container: Neo4jContainer, capsys: pytest.CaptureFixture[str]
) -> None:
    await graph.execute_query("CREATE (:Entity:Task {uid: 'task_3f9a0c41d2e87b65'})")
    assert (await _run(capsys, "--confirm"))[0] == 0
    app = Neo4jConnection(
        uri=scratch_neo4j_container.get_connection_url(), username="neo4j", password="unused"
    )
    await app.connect()
    await app.close()


@pytest.mark.usefixtures("to_the_scratch_graph")
async def test_a_record_in_another_state_stops_the_stamp(
    graph: AsyncDriver, capsys: pytest.CaptureFixture[str]
) -> None:
    await graph.execute_query(
        "CREATE (:Entity:Task {uid: 'task_3f9a0c41d2e87b65'}) "
        "CREATE (:MigrationRecord {name: $name, state: $state})",
        name=UID_GRAMMAR_MIGRATION,
        state=MigrationState.REVERTED,
    )
    code, out = await _run(capsys, "--confirm")
    assert code == 2 and "'reverted'" in out, out
    assert [record["state"] for record in await _uid_record(graph)] == [MigrationState.REVERTED]
