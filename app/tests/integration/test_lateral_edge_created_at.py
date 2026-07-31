"""Lateral edge ``created_at`` is a real instant, in one representation, stamped once.

``LateralRelationshipService.create_lateral_relationship`` used to set
``rel_metadata["created_at"] = "timestamp()"`` and hand the dict to
``SET r += $metadata`` — a query *parameter*. Neo4j never evaluates parameter
values as expressions, so every lateral edge ever created through this path
(BLOCKS, PREREQUISITE_FOR, ALTERNATIVE_TO, COMPLEMENTARY_TO, …) carried the
literal 11-character string ``"timestamp()"`` instead of a time. The auto-created
inverse edge reused the same dict, so inverses carried it too.

Three separate guarantees are pinned here, because the obvious fix satisfies
only the first:

1. The value is a **real instant** — ``test_created_at_is_a_parseable_instant``.
2. It is an **ISO string, not a Neo4j temporal** —
   ``test_edge_metadata_survives_the_json_boundary`` and
   ``test_stamp_agrees_with_the_ingestion_edge_writer``. This is not a stylistic
   preference. Two writers reach these same edge types: this service, and the
   edge-YAML ingestion door, whose only gate is ``RelationshipName`` membership
   (``validate_edge_data``), so every lateral type is ingestible. That door
   stamps ``datetime.now().isoformat()``. Moving the stamp into Cypher as
   ``datetime()`` would put a ``neo4j.time.DateTime`` and an ISO string on the
   same property of the same edge population — *and* break the read path, since
   ``get_relationships`` projects ``properties(r)`` wholesale into a JSON API
   response where a ``neo4j.time.DateTime`` is not serializable.
3. **This writer** no longer rewrites it — ``test_recreate_preserves_created_at``.
   ``MERGE`` + an unconditional ``SET r += $metadata`` rewrote the stamp on
   every re-assert; it is now ``ON CREATE SET``.

The third guarantee is deliberately scoped to this writer, not to the property.
The edge-YAML ingestion door still rewrites ``created_at`` on every re-ingest
(``SET r += $props`` after its own ``MERGE``, with a fresh stamp from
``prepare_edge_data``), so an edge authored in the vault has its stamp refreshed
by each ``./dev vault-sync``. That is measured, not theoretical: of 77 vault
files declaring ``type: Edge``, 41 carry a lateral type — RELATED_TO 23,
PREREQUISITE_FOR 9, COMPLEMENTARY_TO 6, BLOCKS 3. It is a separate defect in a
separate subsystem, affecting all 77 rather than only the lateral ones, and is
tracked separately; claiming it fixed here would be the overstatement these
tests exist to prevent.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from neo4j import Record

from adapters.inbound.boundary import jsonable_content
from adapters.persistence.neo4j.backends.collab_backends import LateralRelationshipBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.relationship_names import RelationshipName
from core.services.ingestion.preparer import prepare_edge_data
from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

PARENT_UID = "goal_stamp_parent"
SOURCE_UID = "goal_stamp_source"
TARGET_UID = "goal_stamp_target"
_FIXTURE_UIDS = [PARENT_UID, SOURCE_UID, TARGET_UID]

# The exact defect string. Named so a grep for it lands here.
LITERAL_DEFECT = "timestamp()"


@pytest.fixture
def service(neo4j_driver) -> LateralRelationshipService:
    """The real service over the real backend — nothing stubbed."""
    return LateralRelationshipService(
        backend=LateralRelationshipBackend(executor=Neo4jQueryExecutor(neo4j_driver))
    )


@pytest_asyncio.fixture(loop_scope="session")
async def two_children(neo4j_driver):
    """Two goals under one parent.

    The shared parent is load-bearing: ``BLOCKS`` declares
    ``requires_same_parent``, so without it validation refuses and every test
    below would pass vacuously on an edge that was never written.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (p:Entity:Goal {uid: $parent, title: 'Cross an ocean',
                                   entity_type: 'goal', status: 'active'})
            CREATE (s:Entity:Goal {uid: $source, title: 'Fix the hull',
                                   entity_type: 'goal', status: 'active'})
            CREATE (t:Entity:Goal {uid: $target, title: 'Provision the boat',
                                   entity_type: 'goal', status: 'active'})
            CREATE (p)-[:HAS_SUBGOAL]->(s)
            CREATE (p)-[:HAS_SUBGOAL]->(t)
            """,
            parent=PARENT_UID,
            source=SOURCE_UID,
            target=TARGET_UID,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_FIXTURE_UIDS
        )


async def _read_edge(neo4j_driver, rel_type: RelationshipName, source: str, target: str) -> Record:
    """Read one edge's full property map, directed source→target.

    Fails loudly when the edge is absent. Every caller here needs it to exist,
    so this doubles as their shared positive control: without it a write that
    never landed would surface as a confusing subscript error several lines
    later rather than as "the edge is missing".
    """
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"""
            MATCH (:Entity {{uid: $source}})-[r:{rel_type.value}]->(:Entity {{uid: $target}})
            RETURN properties(r) AS props, valueType(r.created_at) AS value_type
            """,
            source=source,
            target=target,
        )
        record = await result.single()
    assert record is not None, f"no {rel_type.value} edge {source} -> {target}: write never landed"
    return record


class TestTheValueIsARealInstant:
    async def test_created_at_is_a_parseable_instant(self, service, neo4j_driver, two_children):
        """RED before the fix: the property held the literal string ``timestamp()``."""
        created = await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
        )
        assert not created.is_error, created.expect_error()

        # `_read_edge` asserts the edge exists, so a missing stamp below is a
        # stamping failure rather than an empty match.
        record = await _read_edge(neo4j_driver, RelationshipName.BLOCKS, SOURCE_UID, TARGET_UID)
        stamp = record["props"]["created_at"]

        assert stamp != LITERAL_DEFECT
        # Parsing is the real assertion — it fails on any non-instant, not just
        # on the one string the old code happened to write.
        parsed = datetime.fromisoformat(stamp)
        assert abs((datetime.now() - parsed).total_seconds()) < 300

    async def test_inverse_edge_carries_the_same_instant(self, service, neo4j_driver, two_children):
        """The inverse reused the same metadata dict, so it inherited the defect."""
        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
        )

        forward = await _read_edge(neo4j_driver, RelationshipName.BLOCKS, SOURCE_UID, TARGET_UID)
        # BLOCKS is asymmetric with inverse BLOCKED_BY, written target→source.
        # `_read_edge` asserts, so a missing auto-inverse fails here by name.
        inverse = await _read_edge(
            neo4j_driver, RelationshipName.BLOCKED_BY, TARGET_UID, SOURCE_UID
        )

        assert inverse["props"]["created_at"] != LITERAL_DEFECT
        datetime.fromisoformat(inverse["props"]["created_at"])
        # Both halves of one pair record one instant, not two near-misses.
        assert inverse["props"]["created_at"] == forward["props"]["created_at"]

    async def test_a_late_inverse_adopts_the_forward_stamp(
        self, service, neo4j_driver, two_children
    ):
        """The inverse can be created long after its forward half.

        Reachable three ways: an earlier call passed ``auto_inverse=False``, a
        ``delete_inverse=False`` removed only the inverse, or the earlier
        inverse write failed — ``_create_inverse_relationship`` only logs, so
        that leaves a forward edge with no inverse and no error to the caller.

        On the later re-assert the forward ``MERGE`` preserves its original
        stamp while the inverse is genuinely new, so a freshly generated
        timestamp would split one pair across two instants.
        """
        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
            auto_inverse=False,
        )
        forward_first = await _read_edge(
            neo4j_driver, RelationshipName.BLOCKS, SOURCE_UID, TARGET_UID
        )

        # Positive control: the inverse really is absent, so the re-assert below
        # exercises the late-creation path rather than a plain no-op.
        async with neo4j_driver.session() as session:
            result = await session.run(
                f"""
                MATCH (:Entity {{uid: $t}})-[r:{RelationshipName.BLOCKED_BY.value}]->
                      (:Entity {{uid: $s}})
                RETURN count(r) AS n
                """,
                t=TARGET_UID,
                s=SOURCE_UID,
            )
            assert (await result.single())["n"] == 0

        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
        )

        forward_second = await _read_edge(
            neo4j_driver, RelationshipName.BLOCKS, SOURCE_UID, TARGET_UID
        )
        inverse = await _read_edge(
            neo4j_driver, RelationshipName.BLOCKED_BY, TARGET_UID, SOURCE_UID
        )

        # The forward edge kept its original stamp through the re-assert...
        assert forward_second["props"]["created_at"] == forward_first["props"]["created_at"]
        # ...and the late inverse adopted it rather than stamping "now".
        assert inverse["props"]["created_at"] == forward_first["props"]["created_at"]


class TestTheRepresentationIsAnISOString:
    async def test_edge_metadata_survives_the_json_boundary(
        self, service, neo4j_driver, two_children
    ):
        """``properties(r)`` is JSON-serialized on all 9 domains' lateral GET routes.

        This is the guard that makes the ISO-string decision durable: a Cypher
        ``datetime()`` stamp would return a ``neo4j.time.DateTime`` here, which
        ``jsonable_content`` cannot serialize — the route would 500.
        """
        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
        )

        found = await service.get_lateral_relationships(
            entity_uid=SOURCE_UID,
            relationship_types=[RelationshipName.BLOCKS],
        )
        assert not found.is_error, found.expect_error()
        assert found.value, "positive control: the read path returned no relationship"
        assert "created_at" in found.value[0]["metadata"], (
            "positive control: created_at is not in the projected metadata, so "
            "serializing it below would prove nothing"
        )

        # The real boundary serializer, not a stand-in.
        encoded = jsonable_content(found.value)
        assert isinstance(encoded[0]["metadata"]["created_at"], str)

    async def test_stamp_agrees_with_the_ingestion_edge_writer(
        self, service, neo4j_driver, two_children
    ):
        """The two writers that reach these edge types must agree on the shape.

        Asserting agreement rather than a hand-copied format string: if
        ``prepare_edge_data`` ever changes representation, this fails instead of
        silently letting the two drift onto one property.
        """
        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
        )
        record = await _read_edge(neo4j_driver, RelationshipName.BLOCKS, SOURCE_UID, TARGET_UID)
        lateral_stamp = record["props"]["created_at"]

        ingestion_stamp = prepare_edge_data(
            {"from": "ku:a", "to": "ku:b", "relationship": RelationshipName.BLOCKS.value}
        )["properties"]["created_at"]

        assert type(lateral_stamp) is type(ingestion_stamp)
        # Neo4j sees a STRING, not a temporal — the property type in the graph is
        # what a future reader will have to cope with.
        assert record["value_type"].startswith("STRING")
        # Same tz-awareness: mixing naive and aware ISO strings on one property
        # breaks both comparison and lexicographic ordering.
        assert (
            datetime.fromisoformat(lateral_stamp).tzinfo
            is datetime.fromisoformat(ingestion_stamp).tzinfo
        )


class TestTheStampRecordsFirstCreation:
    async def test_recreate_preserves_created_at(self, service, neo4j_driver, two_children):
        """``MERGE`` + unconditional ``SET r +=`` rewrote ``created_at`` every time."""
        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
            metadata={"reason": "first assertion"},
        )
        first = await _read_edge(neo4j_driver, RelationshipName.BLOCKS, SOURCE_UID, TARGET_UID)

        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
            metadata={"reason": "second assertion"},
        )
        second = await _read_edge(neo4j_driver, RelationshipName.BLOCKS, SOURCE_UID, TARGET_UID)

        # Positive control: the re-assert really did reach the edge. Without
        # this, a create that silently failed would satisfy the guarantee below.
        assert first["props"]["reason"] == "first assertion"
        assert second["props"]["reason"] == "second assertion"

        assert second["props"]["created_at"] == first["props"]["created_at"]


class TestTheCallerCannotSupplyTheStamp:
    """``created_at`` is stamped by the service, never taken from the caller.

    ``create_lateral_relationship`` is a public, domain-agnostic API documented
    as accepting arbitrary "relationship properties". The backend applies
    ``SET r += $metadata`` *after* its ``ON CREATE SET``, so a caller-supplied
    ``created_at`` would land last and undo both guarantees — including
    reintroducing the exact literal this PR removes. No caller passes one today;
    these pin that the guarantee is structural rather than caller discipline.
    """

    async def test_caller_supplied_created_at_is_ignored_on_create(
        self, service, neo4j_driver, two_children
    ):
        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
            metadata={"created_at": LITERAL_DEFECT, "reason": "forged stamp"},
        )
        record = await _read_edge(neo4j_driver, RelationshipName.BLOCKS, SOURCE_UID, TARGET_UID)

        # Positive control: the rest of the caller's metadata still lands, so
        # this is a targeted strip and not a dropped write.
        assert record["props"]["reason"] == "forged stamp"
        assert record["props"]["created_at"] != LITERAL_DEFECT
        datetime.fromisoformat(record["props"]["created_at"])

    async def test_caller_supplied_created_at_cannot_rewrite_an_existing_edge(
        self, service, neo4j_driver, two_children
    ):
        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
        )
        first = await _read_edge(neo4j_driver, RelationshipName.BLOCKS, SOURCE_UID, TARGET_UID)

        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
            metadata={"created_at": "1999-01-01T00:00:00", "reason": "re-asserted"},
        )
        second = await _read_edge(neo4j_driver, RelationshipName.BLOCKS, SOURCE_UID, TARGET_UID)

        assert second["props"]["reason"] == "re-asserted"
        assert second["props"]["created_at"] == first["props"]["created_at"]

    async def test_the_callers_metadata_dict_is_not_mutated(self, service, two_children):
        """Creating an edge must not be observable as a side effect on the input."""
        caller_metadata: dict[str, object] = {"reason": "mine"}
        await service.create_lateral_relationship(
            source_uid=SOURCE_UID,
            target_uid=TARGET_UID,
            relationship_type=RelationshipName.BLOCKS,
            metadata=caller_metadata,
        )
        assert caller_metadata == {"reason": "mine"}
