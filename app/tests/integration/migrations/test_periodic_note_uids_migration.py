"""The periodic-note uid migration, census and write, against a real Neo4j.

``scripts/migrations/periodic_note_uids_2026_10.py`` renames every periodic note
from ``ue:{kind}:{user}:{period}`` to ``periodic_note_uid`` of its kind, owner and
period, stamps the period into its metadata, and points its tracker row at the
new uid.

The seed is the graph the old writers left: a daily note synced from a vault file
(embedded, a task extracted from it, a tracker row naming it, no ``period_key``)
and a weekly note made in the app (``period_key`` stamped, no tracker row) — plus
a UserEntry that is no periodic note, which the run must leave alone.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest

from core.models.user_entry.user_entry import periodic_note_uid

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.integration,
    pytest.mark.outside_uid_grammar(
        "seeds the old periodic note uid shapes this migration renames"
    ),
]

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/migrations/periodic_note_uids_2026_10.py"


def _load() -> ModuleType:
    """Import the script by path (``scripts/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("periodic_note_uids_2026_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load()

OWNER = "user_zzzpnmig"
DAILY_OLD = f"ue:daily:{OWNER}:2026-06-16"
DAILY_NEW = periodic_note_uid("daily", OWNER, "2026-06-16")
WEEKLY_OLD = f"ue:weekly:{OWNER}:2026-W25"
WEEKLY_NEW = periodic_note_uid("weekly", OWNER, "2026-W25")
PLAIN = "ue_aa11bb22"
TASK = "task_zzzpnmig"
VAULT_FILE = "/vault/periodic_notes/Daily/2026-06-16.md"
VECTOR = [0.5, 0.25, 0.125]


async def _run(
    driver: AsyncDriver, query: str, **params: Any
) -> list[Any]:  # boundary: cypher-params
    async with driver.session() as session:
        result = await session.run(query, params)
        return [record async for record in result]


@pytest.fixture
async def old_graph(neo4j_driver: AsyncDriver, clean_neo4j: None) -> AsyncIterator[None]:
    """The old shapes on an otherwise empty graph — the census reads every UserEntry."""
    await _run(
        neo4j_driver,
        """
        MERGE (u:User {uid: $owner})
        CREATE (u)-[:OWNS]->(daily:Entity:UserEntry {
            uid: $daily, user_uid: $owner, entity_type: 'user_entry',
            pipeline: 'extract_activities', metadata: $daily_md, embedding: $vector})
        CREATE (u)-[:OWNS]->(:Entity:UserEntry {
            uid: $weekly, user_uid: $owner, entity_type: 'user_entry',
            pipeline: 'none', metadata: $weekly_md})
        CREATE (u)-[:OWNS]->(:Entity:UserEntry {
            uid: $plain, user_uid: $owner, entity_type: 'user_entry', metadata: '{}'})
        CREATE (u)-[:OWNS]->(:Entity:Task {uid: $task, user_uid: $owner})
               -[:EXTRACTED_FROM {vault_id: 'sk_abc123'}]->(daily)
        CREATE (:IngestionMetadata {file_path: $vault_file, entity_uid: $daily})
        CREATE (:IngestionMetadata {file_path: '/vault/knowledge/plain.md', entity_uid: $plain})
        """,
        owner=OWNER,
        daily=DAILY_OLD,
        daily_md=json.dumps({"entry_kind": "daily", "vault_file_path": VAULT_FILE}),
        weekly=WEEKLY_OLD,
        weekly_md=json.dumps({"entry_kind": "weekly", "period_key": "2026-W25"}),
        plain=PLAIN,
        task=TASK,
        vault_file=VAULT_FILE,
        vector=VECTOR,
    )
    yield
    await _run(neo4j_driver, "MATCH (u:User {uid: $owner}) DETACH DELETE u", owner=OWNER)


async def _note(driver: AsyncDriver, uid: str) -> Any:
    rows = await _run(
        driver,
        """
        MATCH (n:UserEntry {uid: $uid})
        OPTIONAL MATCH (:User {uid: $owner})-[o:OWNS]->(n)
        OPTIONAL MATCH (:Task {uid: $task})-[x:EXTRACTED_FROM]->(n)
        RETURN n.metadata AS metadata, n.embedding AS embedding,
               count(DISTINCT o) AS owned, count(DISTINCT x) AS extracted
        """,
        uid=uid,
        owner=OWNER,
        task=TASK,
    )
    return rows[0] if rows else None


async def _tracker(driver: AsyncDriver) -> dict[str, str]:
    rows = await _run(
        driver, "MATCH (m:IngestionMetadata) RETURN m.file_path AS path, m.entity_uid AS uid"
    )
    return {str(row["path"]): str(row["uid"]) for row in rows}


@pytest.mark.usefixtures("old_graph")
class TestTheRename:
    async def test_census_plans_both_notes_and_the_vault_note_row(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        plan = await migration.census(neo4j_driver)

        assert plan.stops == [], plan.stops
        assert sorted((r.old, r.new) for r in plan.renames) == sorted(
            [(DAILY_OLD, DAILY_NEW), (WEEKLY_OLD, WEEKLY_NEW)]
        )
        assert plan.repoints == [migration.Repoint(path=VAULT_FILE, old=DAILY_OLD, new=DAILY_NEW)]
        assert (plan.periodic, plan.embedded) == (2, 1)

    async def test_confirm_renames_in_place_and_keeps_every_edge_and_vector(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        plan = await migration.census(neo4j_driver)

        assert await migration.migrate(neo4j_driver, plan) == (2, 1)

        assert await _note(neo4j_driver, DAILY_OLD) is None
        daily = await _note(neo4j_driver, DAILY_NEW)
        assert json.loads(daily["metadata"]) == {
            "entry_kind": "daily",
            "vault_file_path": VAULT_FILE,
            "period_key": "2026-06-16",
        }
        assert list(daily["embedding"]) == VECTOR
        assert (daily["owned"], daily["extracted"]) == (1, 1)
        weekly = await _note(neo4j_driver, WEEKLY_NEW)
        assert json.loads(weekly["metadata"]) == {"entry_kind": "weekly", "period_key": "2026-W25"}
        assert await _tracker(neo4j_driver) == {
            VAULT_FILE: DAILY_NEW,
            "/vault/knowledge/plain.md": PLAIN,
        }
        assert await migration._read_back(neo4j_driver, plan) == []

    async def test_a_re_run_writes_nothing_and_reads_back_clean(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        before = await migration.census(neo4j_driver)
        await migration.migrate(neo4j_driver, before)

        again = await migration.census(neo4j_driver)

        assert again.stops == [] and again.writes == 0
        assert again.at_derived_uid == 2
        assert await migration._read_back(neo4j_driver, again) == []

    async def test_an_app_note_made_before_the_run_stops_it_before_any_write(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Opening the day's note between merge and migration makes a second note."""
        await _run(
            neo4j_driver,
            """
            MATCH (u:User {uid: $owner})
            CREATE (u)-[:OWNS]->(:Entity:UserEntry {
                uid: $new, user_uid: $owner, entity_type: 'user_entry', metadata: $md})
            """,
            owner=OWNER,
            new=DAILY_NEW,
            md=json.dumps({"entry_kind": "daily", "period_key": "2026-06-16"}),
        )

        plan = await migration.census(neo4j_driver)

        assert f"{DAILY_NEW} (for {DAILY_OLD}) is already held by a node" in plan.stops
        with pytest.raises(migration.CountMismatchError):
            await migration.migrate(neo4j_driver, plan)
        assert await _note(neo4j_driver, DAILY_OLD) is not None
        assert (await _tracker(neo4j_driver))[VAULT_FILE] == DAILY_OLD

    async def test_a_property_naming_an_old_uid_stops_the_run(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """A submitted copy records the note it came from by uid; the rename would
        leave that reference naming no node."""
        await _run(
            neo4j_driver,
            """
            MATCH (u:User {uid: $owner})
            CREATE (u)-[:OWNS]->(:Entity:UserEntry {
                uid: 'ue_bb22cc33', user_uid: $owner, entity_type: 'user_entry',
                submitted_from_uid: $daily})
            """,
            owner=OWNER,
            daily=DAILY_OLD,
        )

        plan = await migration.census(neo4j_driver)

        assert plan.stops == ["node ue_bb22cc33.submitted_from_uid names an old periodic uid"]

    async def test_a_note_changed_after_the_census_rolls_the_whole_run_back(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        plan = await migration.census(neo4j_driver)
        await _run(
            neo4j_driver,
            "MATCH (n:UserEntry {uid: $uid}) SET n.metadata = $md",
            uid=WEEKLY_OLD,
            md=json.dumps({"entry_kind": "weekly", "period_key": "2026-W25", "edited": True}),
        )

        with pytest.raises(migration.CountMismatchError):
            await migration.migrate(neo4j_driver, plan)

        assert await _note(neo4j_driver, DAILY_OLD) is not None
        assert await _note(neo4j_driver, DAILY_NEW) is None
        assert (await _tracker(neo4j_driver))[VAULT_FILE] == DAILY_OLD
