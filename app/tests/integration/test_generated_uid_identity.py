"""The one generated uid shape, held by the graph — against a real Neo4j.

- The app gives every uid-bearing label outside :Entity and :User its own uid
  uniqueness constraint (``UID_UNIQUE_LABELS``), so a second node on a uid is
  refused rather than stored.
- A teacher's default group sits at ``default_group_uid`` of the teacher and
  carries ``is_default``; the enrollment MERGE finds it again.
- The move pre-pass reads each gone UserEntry's body with its ``period_key``,
  the mark of a uid derived from its period, so the similarity pass can leave
  periodic notes out; no other node is a similarity source.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from neo4j.exceptions import ConstraintError

from adapters.persistence.neo4j.backends.collab_backends import GroupBackend
from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.neo4j_schema_manager import UID_UNIQUE_LABELS
from core.models.enums.neo_labels import NeoLabel
from core.models.group.group import Group, default_group_uid
from core.models.user_entry.user_entry import periodic_note_uid

if TYPE_CHECKING:
    from neo4j import AsyncDriver

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

TEACHER = "user_zzzgenuid_teacher"
MINTED = "ue_00000000zzzgen01"
PERIODIC = periodic_note_uid("daily", TEACHER, "2026-10-23")
BROKEN = "ue_00000000zzzgen02"
TASK = "task_00000000zzzgen03"
GROUP_UID = "group_00000000zzzgen04"


async def _rows(
    driver: AsyncDriver, query: str, **params: Any
) -> list[Any]:  # boundary: cypher-params
    async with driver.session() as session:
        result = await session.run(query, params)
        return [record async for record in result]


class TestUidConstraints:
    async def test_every_uid_label_outside_entity_and_user_is_constrained(self, skuel_app) -> None:
        driver: AsyncDriver = skuel_app.state.services.neo4j_driver
        constraints = await _rows(
            driver,
            "SHOW CONSTRAINTS YIELD labelsOrTypes, properties, type "
            "WHERE type = 'NODE_PROPERTY_UNIQUENESS' RETURN labelsOrTypes, properties",
        )
        constrained = {
            (tuple(row["labelsOrTypes"]), tuple(row["properties"])) for row in constraints
        }
        missing = [
            label.value
            for label in (*UID_UNIQUE_LABELS, NeoLabel.ENTITY, NeoLabel.USER)
            if ((label.value,), ("uid",)) not in constrained
        ]
        assert missing == []
        plain = await _rows(
            driver, "SHOW INDEXES YIELD name WHERE name = 'group_uid_idx' RETURN name"
        )
        assert plain == []

    async def test_a_second_group_on_one_uid_is_refused(self, skuel_app) -> None:
        driver: AsyncDriver = skuel_app.state.services.neo4j_driver
        await _rows(driver, "CREATE (:Group {uid: $uid, name: 'one'})", uid=GROUP_UID)
        try:
            with pytest.raises(ConstraintError):
                await _rows(driver, "CREATE (:Group {uid: $uid, name: 'two'})", uid=GROUP_UID)
        finally:
            await _rows(driver, "MATCH (g:Group {uid: $uid}) DETACH DELETE g", uid=GROUP_UID)


class TestDefaultGroup:
    async def test_the_merge_lands_on_the_derived_uid_flagged_and_once(
        self, neo4j_driver: AsyncDriver, clean_neo4j: None
    ) -> None:
        await _rows(neo4j_driver, "MERGE (:User {uid: $t})", t=TEACHER)
        groups = GroupBackend(driver=neo4j_driver, label=NeoLabel.GROUP, entity_class=Group)
        try:
            first = await groups.get_or_create_default_group(TEACHER, "2026-10-23T12:00:00+00:00")
            again = await groups.get_or_create_default_group(TEACHER, "2026-10-23T13:00:00+00:00")

            assert first.is_ok and again.is_ok
            assert first.value[0]["group_uid"] == again.value[0]["group_uid"]
            owned = await _rows(
                neo4j_driver,
                "MATCH (:User {uid: $t})-[:OWNS]->(g:Group) RETURN g.uid AS uid, g.is_default AS d",
                t=TEACHER,
            )
            assert [(row["uid"], row["d"]) for row in owned] == [(default_group_uid(TEACHER), True)]
        finally:
            await _rows(neo4j_driver, "MATCH (u:User {uid: $t}) DETACH DELETE u", t=TEACHER)


class TestSimilaritySourceContents:
    async def test_each_live_user_entry_reads_with_its_period(
        self, neo4j_driver: AsyncDriver, clean_neo4j: None
    ) -> None:
        await _rows(
            neo4j_driver,
            """
            CREATE (:Entity:UserEntry {uid: $minted, content: 'a body', metadata: '{}'})
            CREATE (:Entity:UserEntry {uid: $periodic, content: 'a day', metadata: $periodic_md})
            CREATE (:Entity:UserEntry {uid: $broken, content: 'a body', metadata: '{not json'})
            CREATE (:Entity:Task {uid: $task, content: 'a body'})
            """,
            minted=MINTED,
            periodic=PERIODIC,
            periodic_md=json.dumps({"entry_kind": "daily", "period_key": "2026-10-23"}),
            broken=BROKEN,
            task=TASK,
        )
        backend = IngestionBackend(Neo4jQueryExecutor(neo4j_driver))

        result = await backend.get_entity_contents([MINTED, PERIODIC, BROKEN, TASK, "ue_gone"])

        assert result.is_ok, result.expect_error()
        assert sorted((row["uid"], row["period_key"]) for row in result.value) == sorted(
            [(MINTED, None), (PERIODIC, "2026-10-23")]
        )
