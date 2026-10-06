"""The task-contributes-to-goal re-type, census and write, against a real Neo4j.

``scripts/migrations/task_contributes_to_goal_2026_10.py`` moves a task's goal link from
``(Task)-[:FULFILLS_GOAL]->(Goal)`` onto ``(Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)``, the
one edge tasks and events contribute through, and takes the rest of the old shape with
it: the ``Task.fulfills_goal_uid`` column, the task template's
``fulfills_goal_template_uid``, the link doors' unread edge properties, and the vault
tracker keys that named the old type.

The seed holds one pair per state a pair can be in:

- ``old``: only the old edge (the task also holds the column, as the live tasks do);
- ``both``: the old edge and a new one carrying nothing;
- ``kept``: the old edge and a new one carrying the task link door's properties;

and beside them:

- a task holding the column alone (a PathStep-spawned task), to a goal its owner owns;
- a task whose column names another user's goal, and one whose column names nothing;
- an event's ``CONTRIBUTES_TO_GOAL`` carrying the event link door's ``contribution_weight``;
- a sub-goal's ``Goal.fulfills_goal_uid`` (its parent) and a goal template's
  ``fulfills_goal_template_uid`` — different fields of the same old name, untouched;
- a task template's ``fulfills_goal_template_uid``, renamed.

The type leaves the code, so an old edge between any other kinds, or an Edge file's
tracker row naming it, stops the run before any write.

The tracker half also runs over rows a real sync wrote, set back to the old shape.

Last, the tally backstop the run ends with: ``GoalsProgressService.reconcile_goal_tallies``
over the bootstrapped app's graph.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from structlog.testing import capture_logs

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums.entity_enums import EntityType
from core.services.ingestion.authored_edges import authored_edge_fingerprint
from core.services.ingestion.config import ENTITY_CONFIGS
from tests.integration._activity_link_rig import (
    create,
    signed_in_client,
    sync_vault,
    write_edge,
    write_vault_file,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts/migrations/task_contributes_to_goal_2026_10.py"
)


def _load() -> ModuleType:
    """Import the script by path (``scripts/`` is not a package).

    Registered in ``sys.modules`` before it runs: ``@dataclass`` resolves the
    module's annotations through it.
    """
    spec = importlib.util.spec_from_file_location("task_contributes_to_goal_2026_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load()

MARK = "zzztctgmig"
USER = f"user_{MARK}"
OTHER = f"user_{MARK}_other"
STATES = ("old", "both", "kept")
TASK = {state: f"task.{MARK}.{state}" for state in STATES}
GOAL = {state: f"goal.{MARK}.{state}" for state in STATES}

COLUMN_TASK = f"task.{MARK}.column"  # the column alone, naming its owner's goal
COLUMN_GOAL = f"goal.{MARK}.column"
FOREIGN_TASK = f"task.{MARK}.foreign"  # the column names another user's goal
FOREIGN_GOAL = f"goal.{MARK}.foreign"
MISSING_TASK = f"task.{MARK}.missing"  # the column names no goal
EVENT = f"event.{MARK}.weighted"
SUBGOAL = f"goal.{MARK}.sub"  # Goal.fulfills_goal_uid: its parent, GOAL["old"]
TASK_TEMPLATE = f"tt.{MARK}.task"
GOAL_TEMPLATE = f"gt.{MARK}.goal"
PARENT_GOAL_TEMPLATE = f"gt.{MARK}.parent"

LINK_DOOR_PROPS = {"contribution_percentage": 50.0, "milestone_uid": "milestone-1"}
EVENT_DOOR_PROPS = {"contribution_weight": 2.0}

# (type, source, target, properties) for every edge in the graph, sorted.
type Props = dict[str, Any]  # boundary: raw neo4j property map
type EdgeRow = tuple[str, str, str, Props]


async def _run(
    driver: AsyncDriver,
    query: str,
    **params: Any,  # boundary: neo4j query parameters
) -> list[Props]:
    async with driver.session() as session:
        return [dict(row) async for row in await session.run(query, **params)]


async def _node(
    driver: AsyncDriver,
    label: str,
    uid: str,
    owner: str | None = USER,
    **properties: Any,  # boundary: raw neo4j property map
) -> None:
    await _run(
        driver,
        f"""
        CREATE (n:Entity:{label} {{uid: $uid, title: $uid, status: 'active'}})
        SET n += $properties
        """,
        uid=uid,
        properties={**({"user_uid": owner} if owner else {}), **properties},
    )


async def _edge(
    driver: AsyncDriver,
    source: str,
    edge_type: str,
    target: str,
    **properties: Any,  # boundary: raw neo4j property map
) -> None:
    written = await _run(
        driver,
        f"""
        MATCH (a {{uid: $source}}), (b {{uid: $target}})
        CREATE (a)-[r:{edge_type}]->(b)
        SET r = $properties
        RETURN count(r) AS written
        """,
        source=source,
        target=target,
        properties=properties,
    )
    assert written == [{"written": 1}], (source, edge_type, target)


async def _edges(driver: AsyncDriver) -> list[EdgeRow]:
    rows = await _run(
        driver,
        """
        MATCH (a)-[r]->(b)
        RETURN type(r) AS type, a.uid AS source, b.uid AS target, properties(r) AS properties
        """,
    )
    return sorted(
        ((row["type"], row["source"], row["target"], dict(row["properties"])) for row in rows),
        key=_ends,
    )


def _ends(edge: EdgeRow) -> tuple[str, str, str]:
    return edge[:3]


def _between(edges: list[EdgeRow], one: str, other: str) -> list[EdgeRow]:
    return [edge for edge in edges if {edge[1], edge[2]} == {one, other}]


async def _props(driver: AsyncDriver, uid: str) -> Props:
    [row] = await _run(driver, "MATCH (n {uid: $uid}) RETURN properties(n) AS p", uid=uid)
    return dict(row["p"])


async def _nodes(driver: AsyncDriver) -> dict[str, Props]:
    """Every node's whole property map, by uid."""
    rows = await _run(driver, "MATCH (n) WHERE n.uid IS NOT NULL RETURN properties(n) AS p")
    return {row["p"]["uid"]: dict(row["p"]) for row in rows}


@pytest.fixture
async def old_shapes(neo4j_driver, clean_neo4j) -> AsyncDriver:
    """Every pair state, the column cases, the edge properties and the templates."""
    driver = neo4j_driver
    for state in STATES:
        await _node(driver, "Goal", GOAL[state], entity_type="goal")
    await _node(driver, "Task", TASK["old"], entity_type="task", fulfills_goal_uid=GOAL["old"])
    await _node(driver, "Task", TASK["both"], entity_type="task", fulfills_goal_uid=GOAL["both"])
    await _node(driver, "Task", TASK["kept"], entity_type="task")
    for state in STATES:
        await _edge(driver, TASK[state], "FULFILLS_GOAL", GOAL[state])
    await _edge(driver, TASK["both"], "CONTRIBUTES_TO_GOAL", GOAL["both"])
    await _edge(driver, TASK["kept"], "CONTRIBUTES_TO_GOAL", GOAL["kept"], **LINK_DOOR_PROPS)

    await _node(driver, "Goal", COLUMN_GOAL, entity_type="goal")
    await _node(driver, "Task", COLUMN_TASK, entity_type="task", fulfills_goal_uid=COLUMN_GOAL)
    await _node(driver, "Goal", FOREIGN_GOAL, owner=OTHER, entity_type="goal")
    await _node(driver, "Task", FOREIGN_TASK, entity_type="task", fulfills_goal_uid=FOREIGN_GOAL)
    await _node(
        driver, "Task", MISSING_TASK, entity_type="task", fulfills_goal_uid=f"goal.{MARK}.gone"
    )

    await _node(driver, "Event", EVENT, entity_type="event")
    await _edge(driver, EVENT, "CONTRIBUTES_TO_GOAL", GOAL["old"], **EVENT_DOOR_PROPS)

    await _node(driver, "Goal", SUBGOAL, entity_type="goal", fulfills_goal_uid=GOAL["old"])
    await _node(
        driver,
        "TaskTemplate",
        TASK_TEMPLATE,
        owner=None,
        entity_type="task_template",
        fulfills_goal_template_uid=GOAL_TEMPLATE,
    )
    await _node(driver, "GoalTemplate", GOAL_TEMPLATE, owner=None, entity_type="goal_template")
    await _node(
        driver,
        "GoalTemplate",
        PARENT_GOAL_TEMPLATE,
        owner=None,
        entity_type="goal_template",
        fulfills_goal_template_uid=GOAL_TEMPLATE,
    )
    return driver


async def _migrate(driver: AsyncDriver) -> Any:  # boundary: the script's Written
    return await migration.migrate(driver, await migration.census(driver))


class TestCensus:
    async def test_the_census_reads_each_shape_and_the_links_to_keep(self, old_shapes) -> None:
        found = await migration.census(old_shapes)

        assert [(row["task_uid"], row["goal_uid"]) for row in found.old] == sorted(
            (TASK[state], GOAL[state]) for state in STATES
        )
        assert sorted((row["task_uid"], row["goal_uid"]) for row in found.contributes) == [
            (TASK["both"], GOAL["both"]),
            (TASK["kept"], GOAL["kept"]),
        ]
        columns = {row["task_uid"]: (row["linkable"], row["has_edge"]) for row in found.columns}
        assert columns == {
            TASK["old"]: (True, True),
            TASK["both"]: (True, True),
            COLUMN_TASK: (True, False),
            FOREIGN_TASK: (False, False),
            MISSING_TASK: (False, False),
        }
        assert [row["template_uid"] for row in found.templates] == [TASK_TEMPLATE]
        assert sorted(row["source_uid"] for row in found.edge_props) == sorted(
            [EVENT, TASK["kept"]]
        )
        assert found.pairs == {(TASK[state], GOAL[state]) for state in STATES} | {
            (COLUMN_TASK, COLUMN_GOAL)
        }
        assert (found.stranded, found.edge_file_rows, found.tracker_rewrites) == ([], [], {})
        assert not found.blocked
        assert found.pending

    async def test_the_census_writes_nothing(self, old_shapes) -> None:
        edges, nodes = await _edges(old_shapes), await _nodes(old_shapes)

        await migration.census(old_shapes)

        assert (await _edges(old_shapes), await _nodes(old_shapes)) == (edges, nodes)


# (source, target) of an old edge that does not join a task to a goal: each would be
# left behind by the re-type.
STRANDED = {
    "from-a-habit": (f"habit.{MARK}.h", GOAL["old"]),
    "reversed": (GOAL["old"], TASK["old"]),
    "task-to-task": (TASK["old"], COLUMN_TASK),
}


class TestStranded:
    @pytest.mark.parametrize("case", STRANDED, ids=list(STRANDED))
    async def test_the_census_lists_it_and_does_not_count_it_as_a_pair(
        self, old_shapes, case: str
    ) -> None:
        source, target = STRANDED[case]
        await _node(old_shapes, "Habit", f"habit.{MARK}.h", entity_type="habit")
        await _edge(old_shapes, source, "FULFILLS_GOAL", target)

        found = await migration.census(old_shapes)

        assert [(row["source_uid"], row["target_uid"]) for row in found.stranded] == [
            (source, target)
        ]
        assert found.blocked
        assert len(found.old) == len(STATES)

    @pytest.mark.parametrize("case", STRANDED, ids=list(STRANDED))
    async def test_the_write_refuses_and_writes_nothing(self, old_shapes, case: str) -> None:
        source, target = STRANDED[case]
        await _node(old_shapes, "Habit", f"habit.{MARK}.h", entity_type="habit")
        await _edge(old_shapes, source, "FULFILLS_GOAL", target)
        edges, nodes = await _edges(old_shapes), await _nodes(old_shapes)
        found = await migration.census(old_shapes)

        with pytest.raises(migration.StrandedEdgesError):
            await migration.migrate(old_shapes, found)

        assert (await _edges(old_shapes), await _nodes(old_shapes)) == (edges, nodes)


class TestRetype:
    @pytest.mark.parametrize("state", STATES)
    async def test_each_pair_ends_with_one_bare_contributes_edge_and_no_old_edge(
        self, old_shapes, state: str
    ) -> None:
        await _migrate(old_shapes)

        joined = _between(await _edges(old_shapes), TASK[state], GOAL[state])
        assert joined == [("CONTRIBUTES_TO_GOAL", TASK[state], GOAL[state], {})]

    async def test_the_run_reports_what_it_wrote(self, old_shapes) -> None:
        """One column linked — the column-only task's; a column beside its own edge is
        the re-type's to carry. Three re-typed, five columns removed, one template
        renamed, two edges stripped (the kept task's and the event's)."""
        written = await _migrate(old_shapes)

        assert (
            written.columns_linked,
            written.edges_migrated,
            written.columns_removed,
            written.templates_renamed,
            written.edges_stripped,
            written.tracker_rows,
        ) == (1, 3, 5, 1, 2, 0)

    async def test_no_old_edge_remains(self, old_shapes) -> None:
        await _migrate(old_shapes)

        assert not [edge for edge in await _edges(old_shapes) if edge[0] == "FULFILLS_GOAL"]


class TestColumn:
    async def test_a_column_alone_becomes_its_edge(self, old_shapes) -> None:
        assert _between(await _edges(old_shapes), COLUMN_TASK, COLUMN_GOAL) == []

        await _migrate(old_shapes)

        assert _between(await _edges(old_shapes), COLUMN_TASK, COLUMN_GOAL) == [
            ("CONTRIBUTES_TO_GOAL", COLUMN_TASK, COLUMN_GOAL, {})
        ]

    async def test_a_column_naming_another_users_goal_or_nothing_is_dropped_without_an_edge(
        self, old_shapes
    ) -> None:
        await _migrate(old_shapes)

        edges = await _edges(old_shapes)
        assert _between(edges, FOREIGN_TASK, FOREIGN_GOAL) == []
        assert [edge for edge in edges if MISSING_TASK in edge[1:3]] == []

    async def test_no_task_holds_the_column(self, old_shapes) -> None:
        await _migrate(old_shapes)

        rows = await _run(
            old_shapes, "MATCH (t:Task) WHERE t.fulfills_goal_uid IS NOT NULL RETURN t.uid AS uid"
        )
        assert rows == []

    async def test_a_sub_goals_parent_field_of_the_same_name_is_untouched(self, old_shapes) -> None:
        before = await _props(old_shapes, SUBGOAL)
        assert before["fulfills_goal_uid"] == GOAL["old"]

        await _migrate(old_shapes)

        assert await _props(old_shapes, SUBGOAL) == before


class TestTemplate:
    async def test_the_task_templates_field_is_renamed(self, old_shapes) -> None:
        await _migrate(old_shapes)

        props = await _props(old_shapes, TASK_TEMPLATE)
        assert "fulfills_goal_template_uid" not in props
        assert props["contributes_to_goal_template_uid"] == GOAL_TEMPLATE

    async def test_a_goal_templates_field_of_the_old_name_is_untouched(self, old_shapes) -> None:
        before = await _props(old_shapes, PARENT_GOAL_TEMPLATE)

        await _migrate(old_shapes)

        assert await _props(old_shapes, PARENT_GOAL_TEMPLATE) == before
        assert before["fulfills_goal_template_uid"] == GOAL_TEMPLATE


class TestEdgeProps:
    async def test_the_link_doors_properties_leave_every_contributes_edge(self, old_shapes) -> None:
        await _migrate(old_shapes)

        assert _between(await _edges(old_shapes), EVENT, GOAL["old"]) == [
            ("CONTRIBUTES_TO_GOAL", EVENT, GOAL["old"], {})
        ]
        assert [
            edge for edge in await _edges(old_shapes) if edge[0] == "CONTRIBUTES_TO_GOAL"
        ] == sorted(
            [
                ("CONTRIBUTES_TO_GOAL", source, target, {})
                for source, target in [
                    *((TASK[state], GOAL[state]) for state in STATES),
                    (COLUMN_TASK, COLUMN_GOAL),
                    (EVENT, GOAL["old"]),
                ]
            ],
            key=_ends,
        )


class TestRerun:
    async def test_a_second_run_finds_nothing_to_do_and_changes_nothing(self, old_shapes) -> None:
        await _migrate(old_shapes)
        edges, nodes = await _edges(old_shapes), await _nodes(old_shapes)

        again = await migration.census(old_shapes)
        written = await migration.migrate(old_shapes, again)

        assert (again.old, again.columns, again.templates, again.edge_props) == ([], [], [], [])
        assert again.tracker_rewrites == {}
        assert not again.pending
        assert again.pairs == set()
        assert len(again.contributes) == len(STATES) + 1
        assert (
            written.columns_linked,
            written.edges_migrated,
            written.columns_removed,
            written.templates_renamed,
            written.edges_stripped,
            written.tracker_rows,
        ) == (0, 0, 0, 0, 0, 0)
        assert (await _edges(old_shapes), await _nodes(old_shapes)) == (edges, nodes)


# ---------------------------------------------------------------------------
# Tracker rows
# ---------------------------------------------------------------------------

ROW_TASK = f"/vault/{MARK}/task.md"
ROW_BOTH = f"/vault/{MARK}/both.md"
ROW_EVENT = f"/vault/{MARK}/event.md"
KU = f"ku.{MARK}.applied"


async def _tracker_row(
    driver: AsyncDriver, file_path: str, entity_uid: str, keys: list[str]
) -> None:
    await _run(
        driver,
        """
        CREATE (row:IngestionMetadata {file_path: $file_path, entity_uid: $entity_uid,
                                       authored_edges: $keys, content_hash: 'seeded',
                                       status: 'success'})
        """,
        file_path=file_path,
        entity_uid=entity_uid,
        keys=keys,
    )


async def _rows(driver: AsyncDriver) -> dict[str, Props]:
    """Every tracker row's whole property map, by file path."""
    rows = await _run(driver, "MATCH (row:IngestionMetadata) RETURN properties(row) AS properties")
    return {row["properties"]["file_path"]: dict(row["properties"]) for row in rows}


@pytest.fixture
async def old_rows(old_shapes) -> AsyncDriver:
    """A task file's row with the old key, one holding the old and the new key for one
    goal, and an event file's row naming only the new type."""
    await _tracker_row(
        old_shapes,
        ROW_TASK,
        TASK["old"],
        [f"APPLIES_KNOWLEDGE|outgoing|{KU}", f"FULFILLS_GOAL|outgoing|{GOAL['old']}"],
    )
    await _tracker_row(
        old_shapes,
        ROW_BOTH,
        TASK["both"],
        [
            f"CONTRIBUTES_TO_GOAL|outgoing|{GOAL['both']}",
            f"FULFILLS_GOAL|outgoing|{GOAL['both']}",
        ],
    )
    await _tracker_row(
        old_shapes, ROW_EVENT, EVENT, [f"CONTRIBUTES_TO_GOAL|outgoing|{GOAL['old']}"]
    )
    return old_shapes


class TestTrackerRows:
    async def test_the_census_lists_the_rows_naming_the_old_type_and_not_the_events(
        self, old_rows
    ) -> None:
        found = await migration.census(old_rows)

        assert set(found.tracker_rewrites) == {ROW_TASK, ROW_BOTH}

    async def test_the_task_files_row_is_the_fingerprint_its_new_field_computes(
        self, old_rows
    ) -> None:
        """A re-ingest of the edited task file diffs to nothing: prior == current."""
        await _migrate(old_rows)

        declared = {
            "connections.contributes_to_goal": [GOAL["old"]],
            "connections.applies_knowledge": [KU],
        }
        fingerprint = authored_edge_fingerprint(
            declared, ENTITY_CONFIGS[EntityType.TASK].relationship_config
        )
        assert fingerprint == sorted(
            [f"APPLIES_KNOWLEDGE|outgoing|{KU}", f"CONTRIBUTES_TO_GOAL|outgoing|{GOAL['old']}"]
        )
        assert (await _rows(old_rows))[ROW_TASK]["authored_edges"] == fingerprint

    async def test_an_old_and_a_new_key_for_one_goal_become_one_key(self, old_rows) -> None:
        await _migrate(old_rows)

        assert (await _rows(old_rows))[ROW_BOTH]["authored_edges"] == [
            f"CONTRIBUTES_TO_GOAL|outgoing|{GOAL['both']}"
        ]

    async def test_the_run_reports_two_rows_and_touches_nothing_else(self, old_rows) -> None:
        before = await _rows(old_rows)

        written = await _migrate(old_rows)

        after = await _rows(old_rows)
        assert written.tracker_rows == 2
        assert after[ROW_EVENT] == before[ROW_EVENT]
        assert {
            path: {key: value for key, value in row.items() if key != "authored_edges"}
            for path, row in after.items()
        } == {
            path: {key: value for key, value in row.items() if key != "authored_edges"}
            for path, row in before.items()
        }

    async def test_a_second_run_leaves_every_row_identical(self, old_rows) -> None:
        await _migrate(old_rows)
        after_first = await _rows(old_rows)

        again = await migration.census(old_rows)
        await migration.migrate(old_rows, again)

        assert again.tracker_rewrites == {}
        assert await _rows(old_rows) == after_first


# An Edge file's tracker row: its entity_uid names the edge, ``edge:<from>|<TYPE>|<to>``.
OLD_EDGE_FILE_ROW = f"edge:{TASK['old']}|FULFILLS_GOAL|{GOAL['old']}"
NEW_EDGE_FILE_ROW = f"edge:{TASK['old']}|CONTRIBUTES_TO_GOAL|{GOAL['old']}"


class TestEdgeFileRows:
    async def test_an_edge_files_row_naming_the_old_type_blocks_the_run(self, old_rows) -> None:
        await _tracker_row(old_rows, f"/vault/{MARK}/edge.yaml", OLD_EDGE_FILE_ROW, [])
        edges, nodes, rows = await _edges(old_rows), await _nodes(old_rows), await _rows(old_rows)

        found = await migration.census(old_rows)
        assert [row["entity_uid"] for row in found.edge_file_rows] == [OLD_EDGE_FILE_ROW]
        assert found.blocked
        with pytest.raises(migration.StrandedEdgesError):
            await migration.migrate(old_rows, found)

        assert (await _edges(old_rows), await _nodes(old_rows), await _rows(old_rows)) == (
            edges,
            nodes,
            rows,
        )

    async def test_an_edge_files_row_of_the_new_type_does_not_block(self, old_rows) -> None:
        await _tracker_row(old_rows, f"/vault/{MARK}/new.yaml", NEW_EDGE_FILE_ROW, [])

        found = await migration.census(old_rows)

        assert found.edge_file_rows == []
        assert not found.blocked


# ---------------------------------------------------------------------------
# Rows a real sync wrote
# ---------------------------------------------------------------------------

VAULT_TASK = f"task.{MARK}.vault"
VAULT_GOAL = f"goal.{MARK}.vault"


def _write_vault(vault: Path) -> None:
    write_vault_file(vault, "vault-goal", entity_type="goal", uid=VAULT_GOAL, owner=USER)
    write_vault_file(
        vault,
        "vault-task",
        entity_type="task",
        uid=VAULT_TASK,
        owner=USER,
        connections={"contributes_to_goal": [VAULT_GOAL]},
    )


async def _authored(driver: AsyncDriver) -> list[str]:
    [row] = await _run(
        driver,
        "MATCH (row:IngestionMetadata {entity_uid: $uid}) RETURN row.authored_edges AS keys",
        uid=VAULT_TASK,
    )
    return list(row["keys"])


@pytest.fixture
async def synced_then_set_back(
    neo4j_driver, clean_neo4j, tmp_path: Path
) -> AsyncIterator[tuple[AsyncDriver, Path, list[str]]]:
    """A task file synced by the real door, then the graph set back to the old shape.

    Yields ``(driver, vault, the keys the sync stored)``. The edge becomes the old edge,
    the task takes the column, and the row's key the old key, as the graph held them
    before the re-type.
    """
    await _run(neo4j_driver, "MERGE (u:User {uid: $uid})", uid=USER)
    _write_vault(tmp_path)
    await sync_vault(neo4j_driver, tmp_path)
    stored = await _authored(neo4j_driver)
    assert stored == [f"CONTRIBUTES_TO_GOAL|outgoing|{VAULT_GOAL}"]

    await _run(
        neo4j_driver,
        """
        MATCH (t {uid: $task})-[new:CONTRIBUTES_TO_GOAL]->(g {uid: $goal})
        DELETE new
        CREATE (t)-[:FULFILLS_GOAL]->(g)
        SET t.fulfills_goal_uid = g.uid
        WITH t, g
        MATCH (row:IngestionMetadata {entity_uid: t.uid})
        SET row.authored_edges = ['FULFILLS_GOAL|outgoing|' + g.uid]
        """,
        task=VAULT_TASK,
        goal=VAULT_GOAL,
    )
    assert [edge[0] for edge in _between(await _edges(neo4j_driver), VAULT_TASK, VAULT_GOAL)] == [
        "FULFILLS_GOAL"
    ]
    yield neo4j_driver, tmp_path, stored
    await _run(neo4j_driver, "MATCH (u:User {uid: $uid}) DETACH DELETE u", uid=USER)


class TestRowsARealSyncWrote:
    async def test_the_rewritten_row_equals_what_the_sync_stored(
        self, synced_then_set_back
    ) -> None:
        driver, _vault, stored = synced_then_set_back

        await _migrate(driver)

        assert await _authored(driver) == stored

    async def test_a_forced_re_sync_of_the_same_file_retracts_nothing(
        self, synced_then_set_back
    ) -> None:
        driver, vault, stored = synced_then_set_back
        await _migrate(driver)
        migrated = _between(await _edges(driver), VAULT_TASK, VAULT_GOAL)
        assert migrated == [("CONTRIBUTES_TO_GOAL", VAULT_TASK, VAULT_GOAL, {})]

        with capture_logs() as logs:
            await sync_vault(driver, vault, force=True)

        assert _between(await _edges(driver), VAULT_TASK, VAULT_GOAL) == migrated
        assert await _authored(driver) == stored
        assert [log for log in logs if "not retracted" in str(log.get("event"))] == []

    async def test_dropping_the_field_then_retracts_the_migrated_edge(
        self, synced_then_set_back
    ) -> None:
        """The rewritten key addresses the migrated edge: a later drop removes it."""
        driver, vault, _stored = synced_then_set_back
        await _migrate(driver)

        write_vault_file(vault, "vault-task", entity_type="task", uid=VAULT_TASK, owner=USER)
        await sync_vault(driver, vault)

        assert _between(await _edges(driver), VAULT_TASK, VAULT_GOAL) == []
        assert await _authored(driver) == []


# ---------------------------------------------------------------------------
# The tally backstop
# ---------------------------------------------------------------------------

RECONCILE_MARK = "zzztctgrec"


@pytest_asyncio.fixture(loop_scope="session")
async def app_client(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[httpx.AsyncClient]:
    if IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"):
        pytest.skip("FULL tier cannot bootstrap without OPENAI_API_KEY")
    async with signed_in_client(skuel_app, f"user_{RECONCILE_MARK}", RECONCILE_MARK) as client:
        yield client


class TestReconcile:
    async def test_the_reconciler_finds_a_stale_goal_closes_it_and_then_finds_nothing(
        self, skuel_app, app_client
    ) -> None:
        """A contribution written with no announcement (the migration's own re-type) leaves
        the stored tally behind; the reconciler lists the goal, writes it, and is idle."""
        services = skuel_app.state.services
        goal = await create(app_client, "goals", "stale goal", measurement_type="task_based")
        task = await create(app_client, "tasks", "silent contributor")
        await write_edge(services.neo4j_driver, task, "CONTRIBUTES_TO_GOAL", goal)
        before = (await services.goals.backend.get(goal)).value
        assert before.target_value != 1

        listed = await services.goals.progress.reconcile_goal_tallies(dry_run=True)

        assert listed.is_ok, listed
        [gap] = [gap for gap in listed.value if gap.goal_uid == goal]
        assert gap.live == "0/1 contributions"
        assert (await services.goals.backend.get(goal)).value.target_value == before.target_value

        closed = await services.goals.progress.reconcile_goal_tallies(dry_run=False)

        assert closed.is_ok, closed
        assert goal in {gap.goal_uid for gap in closed.value}
        after = (await services.goals.backend.get(goal)).value
        assert (after.current_value, after.target_value) == (0, 1)

        again = await services.goals.progress.reconcile_goal_tallies(dry_run=True)

        assert again.is_ok, again
        assert again.value == []
