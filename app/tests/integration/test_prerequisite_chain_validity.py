"""A prerequisite edge's validity window is read as instants on both sides.

``build_simple_prerequisite_chain`` keeps an edge only while it is valid: ``valid_from``
has passed and ``valid_until`` has not. Both properties are ISO strings — written by
``RelationshipMetadata.to_neo4j_properties`` — and the check bound its "as of"
moment as a raw naive ``datetime``, which the driver sends as a LOCAL DATETIME. A
string never compares with a temporal in Neo4j, so an edge carrying any validity
window was dropped, current or not. Both sides now go through ``datetime()``.

Latent in the stored graph (no edge carries a window today), which is why the edges
here carry the properties the real writer produces.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from core.infrastructure.relationships.semantic_relationships import RelationshipMetadata
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

TARGET = "ps.utc-arc.target"
CURRENT = "ps.utc-arc.current-window"
EXPIRED = "ps.utc-arc.expired-window"
NOT_YET = "ps.utc-arc.future-window"
OPEN = "ps.utc-arc.no-window"


@pytest_asyncio.fixture
async def ps_backend(neo4j_driver, clean_neo4j) -> PsBackend:
    backend = PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    for uid in (TARGET, CURRENT, EXPIRED, NOT_YET, OPEN):
        created = await backend.create(PathStep(uid=uid, title=uid))
        assert created.is_ok, created

    now = datetime.now()
    windows = {
        CURRENT: RelationshipMetadata(
            valid_from=now - timedelta(days=30), valid_until=now + timedelta(days=30)
        ),
        EXPIRED: RelationshipMetadata(
            valid_from=now - timedelta(days=60), valid_until=now - timedelta(days=1)
        ),
        NOT_YET: RelationshipMetadata(valid_from=now + timedelta(days=1)),
        OPEN: RelationshipMetadata(),
    }
    linked = await backend.create_relationships_batch(
        [
            (TARGET, uid, RelationshipName.REQUIRES_KNOWLEDGE.value, meta.to_neo4j_properties())
            for uid, meta in windows.items()
        ]
    )
    assert linked.is_ok, linked
    return backend


class TestPrerequisiteValidityWindow:
    async def test_only_currently_valid_prerequisites_are_returned(
        self, ps_backend, neo4j_driver
    ) -> None:
        async with neo4j_driver.session() as session:
            result = await session.run(
                """
                MATCH (:Entity {uid: $target})-[r:REQUIRES_KNOWLEDGE]->(p)
                RETURN p.uid AS uid, valueType(r.valid_from) AS t
                """,
                target=TARGET,
            )
            shapes = {record["uid"]: record["t"] async for record in result}
        # The premise: the writer stores the window as strings.
        assert shapes[CURRENT].startswith("STRING"), shapes
        assert shapes[OPEN] == "NULL", shapes

        chain = await ps_backend.find_prerequisite_chain(TARGET, depth=3, min_confidence=0.0)

        assert chain.is_ok, chain
        assert {row["prereq"]["uid"] for row in chain.value} == {CURRENT, OPEN}
