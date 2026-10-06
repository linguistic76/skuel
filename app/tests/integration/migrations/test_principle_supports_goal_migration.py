"""The principle-supports-goal re-type, census and write, against a real Neo4j.

``scripts/migrations/principle_supports_goal_2026_10.py`` moves the two stored shapes
of one fact — ``(Principle)-[:GUIDES_GOAL]->(Goal)`` and
``(Goal)-[:GUIDED_BY_PRINCIPLE]->(Principle)`` — onto
``(Principle)-[:SUPPORTS_GOAL {weight, essentiality}]->(Goal)``, and rewrites the
vault tracker rows that recorded the old shapes.

The seed holds one pair per state a pair can be in:

- ``guides``: only the principle-side edge;
- ``guided``: only the goal-side edge, carrying ``alignment_strength``;
- ``both``: both old edges;
- ``kept``: both old edges and a ``SUPPORTS_GOAL`` that already has its values;
- ``partial``: the principle-side edge and a ``SUPPORTS_GOAL`` with a weight only;

and the edges the re-type must leave alone: a PathStep's ``GUIDED_BY_PRINCIPLE`` and
a habit's ``SUPPORTS_GOAL``. Nodes carry the labels and ``entity_type`` the app writes.

The tracker half runs over rows a real sync wrote: the files are ingested, the graph
is set back to the old shapes by Cypher (the old field names no longer ingest), and
after the re-type the rows must equal what the sync stored.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest
from structlog.testing import capture_logs

from core.models.enums.entity_enums import EntityType
from core.services.ingestion.authored_edges import authored_edge_fingerprint
from core.services.ingestion.config import ENTITY_CONFIGS
from tests.integration._activity_link_rig import sync_vault, write_vault_file

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts/migrations/principle_supports_goal_2026_10.py"
)


def _load() -> ModuleType:
    """Import the script by path (``scripts/`` is not a package).

    Registered in ``sys.modules`` before it runs: ``@dataclass`` resolves the
    module's annotations through it.
    """
    spec = importlib.util.spec_from_file_location("principle_supports_goal_2026_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load()

MARK = "zzzpsgmig"
USER = f"user_{MARK}"
STATES = ("guides", "guided", "both", "kept", "partial")
PRINCIPLE = {state: f"principle.{MARK}.{state}" for state in STATES}
GOAL = {state: f"goal.{MARK}.{state}" for state in STATES}
HABIT = f"habit.{MARK}.supporter"
STEP = f"ps.{MARK}.guided"

DEFAULTS = {"weight": 1.0, "essentiality": "supporting"}
KEPT = {"weight": 0.5, "essentiality": "essential"}
HABIT_EDGE = {"weight": 2.0, "essentiality": "critical"}

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


async def _node(driver: AsyncDriver, label: str, entity_type: str, uid: str) -> None:
    await _run(
        driver,
        f"""
        CREATE (n:Entity:{label} {{uid: $uid, entity_type: $entity_type, title: $uid,
                                 status: 'active', user_uid: $user}})
        """,
        uid=uid,
        entity_type=entity_type,
        user=USER,
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


@pytest.fixture
async def old_shapes(neo4j_driver, clean_neo4j) -> AsyncDriver:
    """Every pair state, plus the PathStep and habit edges the re-type leaves alone."""
    for state in STATES:
        await _node(neo4j_driver, "Principle", "principle", PRINCIPLE[state])
        await _node(neo4j_driver, "Goal", "goal", GOAL[state])
    await _node(neo4j_driver, "Habit", "habit", HABIT)
    await _node(neo4j_driver, "PathStep", "path_step", STEP)

    for state in ("guides", "both", "kept", "partial"):
        await _edge(neo4j_driver, PRINCIPLE[state], "GUIDES_GOAL", GOAL[state])
    await _edge(
        neo4j_driver,
        GOAL["guided"],
        "GUIDED_BY_PRINCIPLE",
        PRINCIPLE["guided"],
        alignment_strength=0.4,
    )
    for state in ("both", "kept"):
        await _edge(neo4j_driver, GOAL[state], "GUIDED_BY_PRINCIPLE", PRINCIPLE[state])
    await _edge(neo4j_driver, PRINCIPLE["kept"], "SUPPORTS_GOAL", GOAL["kept"], **KEPT)
    await _edge(neo4j_driver, PRINCIPLE["partial"], "SUPPORTS_GOAL", GOAL["partial"], weight=0.25)

    await _edge(neo4j_driver, STEP, "GUIDED_BY_PRINCIPLE", PRINCIPLE["guides"])
    await _edge(neo4j_driver, HABIT, "SUPPORTS_GOAL", GOAL["guides"], **HABIT_EDGE)
    return neo4j_driver


async def _migrate(driver: AsyncDriver) -> tuple[int, int, int]:
    return await migration.migrate(driver, await migration.census(driver))


class TestCensus:
    async def test_the_census_reads_each_old_shape_and_the_pairs_they_hold(
        self, old_shapes
    ) -> None:
        found = await migration.census(old_shapes)

        assert {row["principle_uid"] for row in found.principle_side} == {
            PRINCIPLE[state] for state in ("guides", "both", "kept", "partial")
        }
        assert {row["goal_uid"] for row in found.goal_side} == {
            GOAL[state] for state in ("guided", "both", "kept")
        }
        assert found.old_edges == 7
        assert found.pairs == {(PRINCIPLE[state], GOAL[state]) for state in STATES}
        assert len(found.supports) == 2
        assert found.other_guided_by == 1  # the PathStep's
        assert found.stranded == []

    async def test_the_census_writes_nothing(self, old_shapes) -> None:
        before = await _edges(old_shapes)

        await migration.census(old_shapes)

        assert await _edges(old_shapes) == before

    async def test_a_guides_goal_edge_that_is_not_principle_to_goal_is_stranded(
        self, old_shapes
    ) -> None:
        await _edge(old_shapes, HABIT, "GUIDES_GOAL", GOAL["both"])

        found = await migration.census(old_shapes)

        assert [(row["source_uid"], row["target_uid"]) for row in found.stranded] == [
            (HABIT, GOAL["both"])
        ]
        assert "Habit" in found.stranded[0]["source_labels"]
        # It is not counted as a principle-side edge the write would re-type.
        assert HABIT not in {row["principle_uid"] for row in found.principle_side}

    async def test_the_write_refuses_while_an_edge_would_be_stranded(self, old_shapes) -> None:
        await _edge(old_shapes, HABIT, "GUIDES_GOAL", GOAL["both"])
        before = await _edges(old_shapes)
        found = await migration.census(old_shapes)

        with pytest.raises(migration.StrandedEdgesError):
            await migration.migrate(old_shapes, found)

        assert await _edges(old_shapes) == before


class TestRetype:
    @pytest.mark.parametrize("state", STATES)
    async def test_each_pair_ends_with_one_supports_goal_edge_and_no_old_edge(
        self, old_shapes, state: str
    ) -> None:
        await _migrate(old_shapes)

        joined = _between(await _edges(old_shapes), PRINCIPLE[state], GOAL[state])
        assert [edge[:3] for edge in joined] == [("SUPPORTS_GOAL", PRINCIPLE[state], GOAL[state])]

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            ("guides", DEFAULTS),
            ("guided", DEFAULTS),
            ("both", DEFAULTS),
            ("kept", KEPT),
            ("partial", {"weight": 0.25, "essentiality": "supporting"}),
        ],
    )
    async def test_the_defaults_fill_only_what_the_edge_lacks(
        self, old_shapes, state: str, expected: Props
    ) -> None:
        await _migrate(old_shapes)

        joined = _between(await _edges(old_shapes), PRINCIPLE[state], GOAL[state])
        assert [edge[3] for edge in joined] == [expected]

    async def test_the_run_reports_what_it_re_typed(self, old_shapes) -> None:
        assert await _migrate(old_shapes) == (4, 3, 0)

    async def test_alignment_strength_is_on_no_edge(self, old_shapes) -> None:
        assert any("alignment_strength" in edge[3] for edge in await _edges(old_shapes))

        await _migrate(old_shapes)

        assert not [edge for edge in await _edges(old_shapes) if "alignment_strength" in edge[3]]

    async def test_no_guides_goal_edge_and_no_goal_side_guided_by_edge_remains(
        self, old_shapes
    ) -> None:
        await _migrate(old_shapes)

        remaining = [
            edge[:3]
            for edge in await _edges(old_shapes)
            if edge[0] in ("GUIDES_GOAL", "GUIDED_BY_PRINCIPLE")
        ]
        assert remaining == [("GUIDED_BY_PRINCIPLE", STEP, PRINCIPLE["guides"])]

    async def test_a_path_steps_guided_by_principle_edge_is_untouched(self, old_shapes) -> None:
        before = _between(await _edges(old_shapes), STEP, PRINCIPLE["guides"])
        assert before == [("GUIDED_BY_PRINCIPLE", STEP, PRINCIPLE["guides"], {})]

        await _migrate(old_shapes)

        assert _between(await _edges(old_shapes), STEP, PRINCIPLE["guides"]) == before

    async def test_a_habits_supports_goal_edge_is_untouched(self, old_shapes) -> None:
        before = _between(await _edges(old_shapes), HABIT, GOAL["guides"])
        assert before == [("SUPPORTS_GOAL", HABIT, GOAL["guides"], HABIT_EDGE)]

        await _migrate(old_shapes)

        assert _between(await _edges(old_shapes), HABIT, GOAL["guides"]) == before

    async def test_a_second_run_finds_nothing_to_do_and_changes_nothing(self, old_shapes) -> None:
        await _migrate(old_shapes)
        after_first = await _edges(old_shapes)

        again = await migration.census(old_shapes)
        written = await migration.migrate(old_shapes, again)

        assert (again.old_edges, again.tracker_rewrites, again.stranded) == (0, {}, [])
        assert again.pairs == set()
        assert len(again.supports) == len(STATES)
        assert written == (0, 0, 0)
        assert await _edges(old_shapes) == after_first


# ---------------------------------------------------------------------------
# Tracker rows
# ---------------------------------------------------------------------------

ROW_PRINCIPLE = f"/vault/{MARK}/principle.md"
ROW_GOAL = f"/vault/{MARK}/goal.md"
ROW_STEP = f"/vault/{MARK}/step.md"


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
    """A principle file's row, a goal file's row and a PathStep file's row."""
    await _tracker_row(
        old_shapes,
        ROW_PRINCIPLE,
        PRINCIPLE["guides"],
        [f"GUIDES_GOAL|outgoing|{GOAL['guides']}", f"INSPIRES_HABIT|outgoing|{HABIT}"],
    )
    await _tracker_row(
        old_shapes,
        ROW_GOAL,
        GOAL["guided"],
        [f"GUIDED_BY_PRINCIPLE|outgoing|{PRINCIPLE['guided']}", f"SUPPORTS_GOAL|incoming|{HABIT}"],
    )
    await _tracker_row(
        old_shapes, ROW_STEP, STEP, [f"GUIDED_BY_PRINCIPLE|outgoing|{PRINCIPLE['guides']}"]
    )
    return old_shapes


class TestTrackerRows:
    async def test_the_census_lists_the_two_rows_to_rewrite_and_not_the_path_steps(
        self, old_rows
    ) -> None:
        found = await migration.census(old_rows)

        assert set(found.tracker_rewrites) == {ROW_PRINCIPLE, ROW_GOAL}

    async def test_the_principle_files_row_names_supports_goal_outgoing(self, old_rows) -> None:
        await _migrate(old_rows)

        assert (await _rows(old_rows))[ROW_PRINCIPLE]["authored_edges"] == [
            f"INSPIRES_HABIT|outgoing|{HABIT}",
            f"SUPPORTS_GOAL|outgoing|{GOAL['guides']}",
        ]

    async def test_the_goal_files_row_names_supports_goal_incoming(self, old_rows) -> None:
        await _migrate(old_rows)

        assert (await _rows(old_rows))[ROW_GOAL]["authored_edges"] == sorted(
            [f"SUPPORTS_GOAL|incoming|{HABIT}", f"SUPPORTS_GOAL|incoming|{PRINCIPLE['guided']}"]
        )

    async def test_the_goal_files_row_is_the_fingerprint_its_new_fields_compute(
        self, old_rows
    ) -> None:
        """A re-ingest of the edited goal file diffs to nothing: prior == current."""
        await _migrate(old_rows)

        declared = {
            "connections.supporting_principles": [PRINCIPLE["guided"]],
            "connections.supporting_habits": [HABIT],
        }
        fingerprint = authored_edge_fingerprint(
            declared, ENTITY_CONFIGS[EntityType.GOAL].relationship_config
        )
        assert len(fingerprint) == 2
        assert (await _rows(old_rows))[ROW_GOAL]["authored_edges"] == fingerprint

    async def test_the_principle_files_row_is_the_fingerprint_its_new_field_computes(
        self, old_rows
    ) -> None:
        await _migrate(old_rows)

        declared = {
            "connections.supports_goal": [GOAL["guides"]],
            "connections.inspires_habit": [HABIT],
        }
        fingerprint = authored_edge_fingerprint(
            declared, ENTITY_CONFIGS[EntityType.PRINCIPLE].relationship_config
        )
        assert len(fingerprint) == 2
        assert (await _rows(old_rows))[ROW_PRINCIPLE]["authored_edges"] == fingerprint

    async def test_the_path_step_files_row_is_identical(self, old_rows) -> None:
        before = (await _rows(old_rows))[ROW_STEP]

        await _migrate(old_rows)

        assert (await _rows(old_rows))[ROW_STEP] == before
        assert before["authored_edges"] == [f"GUIDED_BY_PRINCIPLE|outgoing|{PRINCIPLE['guides']}"]

    async def test_the_run_reports_two_rows_and_touches_no_other_property(self, old_rows) -> None:
        before = await _rows(old_rows)

        written = await _migrate(old_rows)

        after = await _rows(old_rows)
        assert written[2] == 2
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


# ---------------------------------------------------------------------------
# Rows a real sync wrote
# ---------------------------------------------------------------------------

VAULT_PRINCIPLE = f"principle.{MARK}.vault"
VAULT_GOAL = f"goal.{MARK}.vault"


def _write_vault(vault: Path) -> None:
    write_vault_file(
        vault,
        "vault-principle",
        entity_type="principle",
        uid=VAULT_PRINCIPLE,
        owner=USER,
        connections={"supports_goal": [VAULT_GOAL]},
    )
    write_vault_file(
        vault,
        "vault-goal",
        entity_type="goal",
        uid=VAULT_GOAL,
        owner=USER,
        connections={"supporting_principles": [VAULT_PRINCIPLE]},
    )


async def _authored(driver: AsyncDriver) -> dict[str, list[str]]:
    """Each vault entity's tracker keys, by entity uid."""
    rows = await _run(
        driver,
        """
        MATCH (row:IngestionMetadata) WHERE row.entity_uid IN $uids
        RETURN row.entity_uid AS uid, row.authored_edges AS keys
        """,
        uids=[VAULT_PRINCIPLE, VAULT_GOAL],
    )
    return {row["uid"]: list(row["keys"]) for row in rows}


@pytest.fixture
async def synced_then_set_back(
    neo4j_driver, clean_neo4j, tmp_path: Path
) -> AsyncIterator[tuple[AsyncDriver, Path, dict[str, list[str]]]]:
    """Two files synced by the real door, then the graph set back to the old shapes.

    Yields ``(driver, vault, the keys the sync stored)``. The edge becomes the two old
    edges and each row's key the old key for its side, as the graph held them before
    the re-type.
    """
    await _run(neo4j_driver, "MERGE (u:User {uid: $uid})", uid=USER)
    _write_vault(tmp_path)
    await sync_vault(neo4j_driver, tmp_path)
    stored = await _authored(neo4j_driver)
    assert stored == {
        VAULT_PRINCIPLE: [f"SUPPORTS_GOAL|outgoing|{VAULT_GOAL}"],
        VAULT_GOAL: [f"SUPPORTS_GOAL|incoming|{VAULT_PRINCIPLE}"],
    }

    await _run(
        neo4j_driver,
        """
        MATCH (p {uid: $principle})-[new:SUPPORTS_GOAL]->(g {uid: $goal})
        DELETE new
        CREATE (p)-[:GUIDES_GOAL]->(g)
        CREATE (g)-[:GUIDED_BY_PRINCIPLE]->(p)
        WITH p, g
        MATCH (p_row:IngestionMetadata {entity_uid: p.uid}), (g_row:IngestionMetadata {entity_uid: g.uid})
        SET p_row.authored_edges = ['GUIDES_GOAL|outgoing|' + g.uid],
            g_row.authored_edges = ['GUIDED_BY_PRINCIPLE|outgoing|' + p.uid]
        """,
        principle=VAULT_PRINCIPLE,
        goal=VAULT_GOAL,
    )
    assert [
        edge[0] for edge in _between(await _edges(neo4j_driver), VAULT_PRINCIPLE, VAULT_GOAL)
    ] == [
        "GUIDED_BY_PRINCIPLE",
        "GUIDES_GOAL",
    ]
    yield neo4j_driver, tmp_path, stored
    await _run(neo4j_driver, "MATCH (u:User {uid: $uid}) DETACH DELETE u", uid=USER)


class TestRowsARealSyncWrote:
    async def test_the_rewritten_rows_equal_what_the_sync_stored(
        self, synced_then_set_back
    ) -> None:
        driver, _vault, stored = synced_then_set_back

        await _migrate(driver)

        assert await _authored(driver) == stored

    async def test_a_forced_re_sync_of_the_same_files_retracts_nothing(
        self, synced_then_set_back
    ) -> None:
        driver, vault, stored = synced_then_set_back
        await _migrate(driver)
        migrated = _between(await _edges(driver), VAULT_PRINCIPLE, VAULT_GOAL)
        assert migrated == [("SUPPORTS_GOAL", VAULT_PRINCIPLE, VAULT_GOAL, DEFAULTS)]

        with capture_logs() as logs:
            await sync_vault(driver, vault, force=True)

        assert _between(await _edges(driver), VAULT_PRINCIPLE, VAULT_GOAL) == migrated
        assert await _authored(driver) == stored
        # A key the migration left naming a retired type would be dropped here with a
        # warning instead of being matched; the re-sync must drop none.
        assert [log for log in logs if "not retracted" in str(log.get("event"))] == []

    async def test_dropping_the_field_from_both_files_then_retracts_the_migrated_edge(
        self, synced_then_set_back
    ) -> None:
        """The rewritten keys address the migrated edge: a later drop removes it."""
        driver, vault, _stored = synced_then_set_back
        await _migrate(driver)

        write_vault_file(
            vault, "vault-principle", entity_type="principle", uid=VAULT_PRINCIPLE, owner=USER
        )
        write_vault_file(vault, "vault-goal", entity_type="goal", uid=VAULT_GOAL, owner=USER)
        await sync_vault(driver, vault)

        assert _between(await _edges(driver), VAULT_PRINCIPLE, VAULT_GOAL) == []
        assert await _authored(driver) == {VAULT_PRINCIPLE: [], VAULT_GOAL: []}
