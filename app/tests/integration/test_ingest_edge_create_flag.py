"""The ingestion edge writer's create-vs-update flag reports what ``MERGE`` actually did.

``IngestionWriteBackend.ingest_edge`` computed the flag as::

    MERGE (a)-[r:{rel_type}]->(b)
    SET r += $props
    RETURN ..., CASE WHEN r.created_at = $props.created_at THEN true ELSE false END AS created

Cypher clauses run in order, so by the time ``RETURN`` was evaluated,
``SET r += $props`` had already written ``r.created_at = $props.created_at``. The
comparison was trivially equal and the flag was **always true** — and there is no
input that produced ``false``, because ``prepare_edge_data`` seeds ``created_at``
unconditionally and both callers pass that dict straight through. Re-ingesting an
existing edge logged "Created" and returned ``{"created": True}`` to the caller.

The same unconditional ``SET r += $props`` also rewrote ``created_at`` on every
re-ingest, so an edge's original creation time was lost on each vault re-sync.
Both halves are fixed together — the stamp moves to ``ON CREATE SET`` and the flag
is captured from the ``MERGE`` itself rather than inferred after the write. This
mirrors #889, which made the same change to the lateral-relationship edge writer.

Four guarantees are pinned separately, because the obvious fix satisfies only the
first two and the last two are what keep it from over-reaching:

1. The flag distinguishes create from update — ``TestTheFlagReportsWhatMergeDid``.
2. ``created_at`` records first appearance — ``test_reingest_preserves_created_at``.
3. Every *other* property still refreshes — ``test_reingest_refreshes_the_rest``.
   Without this, deleting ``SET r += $props`` outright would satisfy (2).
4. The create signal leaves nothing behind — ``TestTheCreateSignalIsTransient``.
   ``properties(r)`` is projected wholesale into the JSON response of all 9
   domains' lateral GET routes, and every lateral type is edge-YAML ingestible
   (``validate_edge_data`` gates on ``RelationshipName`` membership alone), so an
   internal marker that survived the write would become part of the API contract.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from core.models.relationship_names import RelationshipName
from core.services.ingestion.preparer import prepare_edge_data

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Vault files author colons; the graph stores dots (``normalize_uid``).
SOURCE_AUTHORED = "ku:edgeflag-source"
TARGET_AUTHORED = "ku:edgeflag-target"
SOURCE_UID = "ku.edgeflag-source"
TARGET_UID = "ku.edgeflag-target"
_FIXTURE_UIDS = [SOURCE_UID, TARGET_UID]

REL = RelationshipName.RELATED_TO


def _prepare(evidence: str) -> dict[str, Any]:
    """Build edge data exactly as the ingestion door does, via the real preparer.

    ``evidence`` differs per call so a re-ingest can be shown to have actually
    reached the edge — otherwise a silently-failed second write would satisfy the
    "created_at is preserved" assertion for the wrong reason.
    """
    return prepare_edge_data(
        {
            "from": SOURCE_AUTHORED,
            "to": TARGET_AUTHORED,
            "relationship": REL.value,
            "evidence": evidence,
        }
    )


@pytest_asyncio.fixture(loop_scope="session")
async def two_entities(neo4j_driver):
    """The two endpoints the edge is written between.

    Load-bearing: ``ingest_edge`` returns no rows when either endpoint is
    missing, and the service turns that into a not-found error — so without
    these nodes every assertion below would be unreachable rather than passing.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (:Entity:Ku {uid: $source, title: 'Caffeine', entity_type: 'ku'})
            CREATE (:Entity:Ku {uid: $target, title: 'Restlessness', entity_type: 'ku'})
            """,
            source=SOURCE_UID,
            target=TARGET_UID,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_FIXTURE_UIDS
        )


async def _read_edge(neo4j_driver) -> Any:
    """Read the edge's full property map, directed source→target."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"""
            MATCH (:Entity {{uid: $source}})-[r:{REL.value}]->(:Entity {{uid: $target}})
            RETURN properties(r) AS props
            """,
            source=SOURCE_UID,
            target=TARGET_UID,
        )
        return await result.single()


async def _count_edges(neo4j_driver) -> int:
    """How many source→target edges of this type exist."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"""
            MATCH (:Entity {{uid: $source}})-[r:{REL.value}]->(:Entity {{uid: $target}})
            RETURN count(r) AS n
            """,
            source=SOURCE_UID,
            target=TARGET_UID,
        )
        record = await result.single()
        return int(record["n"])


class TestTheFlagReportsWhatMergeDid:
    async def test_first_ingest_reports_created(self, ingestion_service, two_entities):
        """The positive control for the whole file: the flag can be ``True``.

        Without this, a fix that hard-wired ``created`` to ``False`` would pass
        every other test here.
        """
        result = await ingestion_service.ingest_edge(_prepare("first"))

        assert not result.is_error, result.expect_error()
        assert result.value["created"] is True

    async def test_reingest_reports_updated(self, ingestion_service, neo4j_driver, two_entities):
        """RED before the fix: the flag was ``True`` on every re-ingest."""
        first = await ingestion_service.ingest_edge(_prepare("first"))
        assert not first.is_error, first.expect_error()
        assert first.value["created"] is True

        second = await ingestion_service.ingest_edge(_prepare("second"))
        assert not second.is_error, second.expect_error()

        # Positive control: the re-ingest landed on the *same* edge. Had it
        # created a second parallel edge, a ``True`` flag would be honest and
        # this test would be testing the wrong thing.
        assert await _count_edges(neo4j_driver) == 1

        assert second.value["created"] is False


class TestCreatedAtRecordsFirstAppearance:
    async def test_reingest_preserves_created_at(
        self, ingestion_service, neo4j_driver, two_entities
    ):
        """RED before the fix: ``SET r += $props`` rewrote the stamp every time."""
        first_data = _prepare("first")
        assert not (await ingestion_service.ingest_edge(first_data)).is_error

        second_data = _prepare("second")
        # Positive control: the two runs really do carry different stamps, so
        # "preserved" is a claim with content. When the written value is a
        # constant, every "value unchanged" assertion passes vacuously.
        assert second_data["properties"]["created_at"] != first_data["properties"]["created_at"], (
            "the two ingest runs stamped the same instant — this test would be vacuous"
        )

        assert not (await ingestion_service.ingest_edge(second_data)).is_error

        record = await _read_edge(neo4j_driver)
        assert record is not None
        assert record["props"]["created_at"] == first_data["properties"]["created_at"]

    async def test_reingest_refreshes_the_rest(self, ingestion_service, neo4j_driver, two_entities):
        """Only ``created_at`` is frozen — every other property still updates.

        This is what separates "stamp ``created_at`` once" from "stop writing on
        re-ingest": dropping ``SET r += $props`` altogether would satisfy the
        preservation test above and fail here.
        """
        first_data = _prepare("first")
        assert not (await ingestion_service.ingest_edge(first_data)).is_error

        second_data = _prepare("second")
        assert not (await ingestion_service.ingest_edge(second_data)).is_error

        record = await _read_edge(neo4j_driver)
        assert record is not None
        assert record["props"]["evidence"] == "second"
        assert record["props"]["updated_at"] == second_data["properties"]["updated_at"]
        assert record["props"]["updated_at"] != first_data["properties"]["updated_at"]


class TestTheCreateSignalIsTransient:
    async def test_no_internal_marker_survives_on_the_edge(
        self, ingestion_service, neo4j_driver, two_entities
    ):
        """Whatever carries ``MERGE``'s create signal must not persist.

        ``get_relationships`` projects ``properties(r)`` wholesale into a JSON API
        response, so any leftover bookkeeping property becomes part of the
        contract for all 9 domains' lateral GET routes.
        """
        assert not (await ingestion_service.ingest_edge(_prepare("first"))).is_error
        after_create = set((await _read_edge(neo4j_driver))["props"])

        # Positive control: the projection is not simply empty, which would make
        # the "no internal keys" assertion below true for the wrong reason.
        assert "created_at" in after_create

        assert not (await ingestion_service.ingest_edge(_prepare("second"))).is_error
        after_update = set((await _read_edge(neo4j_driver))["props"])

        # Both branches of the MERGE, since a marker may be written on either.
        assert not [key for key in after_create if key.startswith("_")], after_create
        assert not [key for key in after_update if key.startswith("_")], after_update
