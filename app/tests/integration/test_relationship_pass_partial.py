"""A relationship pass that fails part-way reports what its committed batches created.

``BulkUpsertBackend.create_relationships`` runs one transaction per batch. When a later
batch fails, the batches before it are committed: the result carries the edges they
created (``created_targets``) with the failure in ``errors``, so the sync credits what
was written and retries the rest (``tests/unit/services/ingestion/
test_relationship_pass_outcome.py`` holds what the sync does with it).

The failure is forced in the second of two one-item batches: an ordered field whose
value is not a list fails ``size()`` in that batch's statement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from core.ingestion.ingestion_types import RelationshipConfig
from tests.helpers.production_backends import build_production_backends

if TYPE_CHECKING:
    from neo4j import AsyncDriver

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

FIRST = "lp.partialpass.first"
SECOND = "lp.partialpass.second"
STEP = "ps.partialpass.step"
FIELD = "connections.contains_steps"
CONFIG = {
    FIELD: RelationshipConfig(
        rel_type="HAS_STEP", target_label="Entity", direction="outgoing", order_property="sequence"
    )
}


async def test_a_pass_that_fails_part_way_reports_its_committed_creations(
    neo4j_driver: AsyncDriver, clean_neo4j: None
) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            """
            UNWIND $paths AS uid
            CREATE (:Entity:LearningPath {uid: uid, entity_type: 'learning_path'})
            WITH count(*) AS made
            CREATE (:Entity:PathStep {uid: $step, entity_type: 'path_step'})
            """,
            paths=[FIRST, SECOND],
            step=STEP,
        )
    backend = build_production_backends(neo4j_driver)["bulk_upsert_backend"]

    result = await backend.create_relationships(
        "LearningPath",
        "Entity",
        [{"uid": FIRST, FIELD: [STEP]}, {"uid": SECOND, FIELD: 5}],
        CONFIG,
        batch_size=1,
    )

    assert result.is_ok, result
    outcome = result.value
    assert outcome.created_targets == {FIRST: {FIELD: (STEP,)}}
    assert outcome.relationships_created == 1
    assert len(outcome.errors) == 1
    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                "MATCH (:LearningPath {uid: $uid})-[r:HAS_STEP]->() RETURN count(r) AS n",
                uid=FIRST,
            )
        ).single()
    assert record is not None and record["n"] == 1


async def test_a_pass_that_succeeds_reports_no_errors(
    neo4j_driver: AsyncDriver, clean_neo4j: None
) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (:Entity:LearningPath {uid: $path, entity_type: 'learning_path'})
            CREATE (:Entity:PathStep {uid: $step, entity_type: 'path_step'})
            """,
            path=FIRST,
            step=STEP,
        )
    backend = build_production_backends(neo4j_driver)["bulk_upsert_backend"]

    first = await backend.create_relationships(
        "LearningPath", "Entity", [{"uid": FIRST, FIELD: [STEP]}], CONFIG, batch_size=1
    )
    again = await backend.create_relationships(
        "LearningPath", "Entity", [{"uid": FIRST, FIELD: [STEP]}], CONFIG, batch_size=1
    )

    assert first.is_ok and again.is_ok
    assert (first.value.errors, first.value.created_targets) == ([], {FIRST: {FIELD: (STEP,)}})
    assert (again.value.errors, again.value.created_targets) == ([], {})
