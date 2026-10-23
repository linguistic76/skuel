"""The grounding pass reads knowledge notes and activity notes, never a private one.

``EntryGroundingBackend.get_pending_entries`` picks the entries a post-sync pass
grounds: an embedded entry on a pipeline ``Pipeline.knowledge_grounded`` names
(knowledge notes; activity notes, periodic notes included), whose grounding stamp
is missing or stale. A ``private: true`` entry is excluded by name, even one that
still carries a vector — the shape a note left behind when it turned private
before its re-sync removed the vector. A turn-in, a plain note or an LLM output
is never pending, vector or not.

Entries are created through ``UserEntryService.create_entry`` (the vault door's
upsert) and embedded through the embeddings writer, so the pending read sees the
properties those writers store. The pass itself runs over the real backend with
a stand-in Ku vector index that matches every entry to one published Ku.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
from adapters.persistence.neo4j.entry_grounding_backend import EntryGroundingBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.constants import EmbeddingGeometry
from core.events.knowledge_substance_events import KnowledgeReflectedInEntry
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.embeddings_service import EmbeddingsService
from core.services.entry_grounding_service import EntryGroundingService
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import Result
from tests.integration.user_entry.test_extract_activities_pipeline import _seed_ku

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.services.user_entry.user_entry_service import UserEntryService

KU = "ku.g3.decisions"
KNOWLEDGE = "ue_g3_knowledge"
DAILY = "ue_g3_daily"
WEEKLY = "ue_g3_weekly"
PRIVATE_DAILY = "ue_g3_private_daily"
PRIVATE_KNOWLEDGE_WITH_VECTOR = "ue_g3_private_knowledge"
PRIVATE_DAILY_WITH_VECTOR = "ue_g3_private_daily_vector"
PLAIN_WITH_VECTOR = "ue_g3_plain"
SUMMARY_WITH_VECTOR = "ue_g3_summary"

GROUNDED = {KNOWLEDGE, DAILY, WEEKLY}


def _embeddings_service(neo4j_driver: AsyncDriver) -> EmbeddingsService:
    """The one embedding writer over a real backend; the inference client is inert."""
    client = MagicMock()
    client.model = "text-embedding-3-small"
    client.dimension = EmbeddingGeometry.DIMENSION
    client.max_input_chars = 20000
    return EmbeddingsService(
        EmbeddingsBackend(Neo4jQueryExecutor(neo4j_driver)), embedding_client=client
    )


async def _create(
    service: UserEntryService,
    owner: str,
    uid: str,
    pipeline: Pipeline,
    private: bool = False,
) -> None:
    result = await service.create_entry(
        request=UserEntryCreateRequest(
            uid=uid,
            title=uid,
            content=f"Decided to keep the morning walk ({uid}).",
            pipeline=pipeline,
            private=private,
        ),
        user_uid=owner,
    )
    assert result.is_ok, result.expect_error()


async def _embed(neo4j_driver: AsyncDriver, uid: str) -> None:
    """Store a vector through the writer's own path, whatever the entry's pipeline."""
    async with neo4j_driver.session() as session:
        record = await (
            await session.run("MATCH (e:UserEntry {uid: $uid}) RETURN e", uid=uid)
        ).single()
    assert record is not None, uid
    stored = await _embeddings_service(neo4j_driver).store_embedding_with_metadata(
        uid=uid,
        label=NeoLabel.USER_ENTRY.value,
        embedding=[0.1] * EmbeddingGeometry.DIMENSION,
        text=build_embedding_text(EntityType.USER_ENTRY, dict(record["e"])),
    )
    assert stored.is_ok, stored.expect_error()


async def _set_private(neo4j_driver: AsyncDriver, uid: str) -> None:
    """Mark an embedded entry private without touching its vector."""
    async with neo4j_driver.session() as session:
        await session.run("MATCH (e:UserEntry {uid: $uid}) SET e.private = true", uid=uid)


@pytest.fixture
async def seeded(
    clean_neo4j: object, user_entry_service: UserEntryService, neo4j_driver: AsyncDriver, seed_user
) -> str:
    owner = await seed_user("user_g3_owner")
    await _seed_ku(neo4j_driver, KU)
    for uid, pipeline in (
        (KNOWLEDGE, Pipeline.KNOWLEDGE),
        (DAILY, Pipeline.EXTRACT_ACTIVITIES),
        (WEEKLY, Pipeline.EXTRACT_ACTIVITIES),
        (PRIVATE_KNOWLEDGE_WITH_VECTOR, Pipeline.KNOWLEDGE),
        (PRIVATE_DAILY_WITH_VECTOR, Pipeline.EXTRACT_ACTIVITIES),
        (PLAIN_WITH_VECTOR, Pipeline.NONE),
        (SUMMARY_WITH_VECTOR, Pipeline.LLM_SUMMARY),
    ):
        await _create(user_entry_service, owner, uid, pipeline)
        await _embed(neo4j_driver, uid)
    await _set_private(neo4j_driver, PRIVATE_KNOWLEDGE_WITH_VECTOR)
    await _set_private(neo4j_driver, PRIVATE_DAILY_WITH_VECTOR)
    # A private activity note the door created private: no vector was ever stored.
    await _create(
        user_entry_service, owner, PRIVATE_DAILY, Pipeline.EXTRACT_ACTIVITIES, private=True
    )
    return owner


class _EveryEntryMatchesTheKu:
    """Stand-in Ku vector index: every vector matches the one seeded Ku."""

    async def find_similar_by_vector(self, **_kwargs: object) -> Result[list[dict[str, object]]]:
        return Result.ok([{"node": {"uid": KU, "title": "Decisions"}, "score": 0.9}])


class _CapturingBus:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish_async(self, event: object) -> None:
        self.published.append(event)


async def _linked_entries(neo4j_driver: AsyncDriver) -> set[str]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (e:UserEntry)-[r:APPLIES_KNOWLEDGE {inferred: true}]->(:Ku {uid: $ku})"
            " RETURN e.uid AS uid",
            ku=KU,
        )
        return {record["uid"] async for record in result}


@pytest.mark.integration
class TestGroundingPending:
    @pytest.mark.asyncio
    async def test_pending_is_the_non_private_knowledge_and_activity_notes(
        self, seeded: str, neo4j_driver: AsyncDriver
    ) -> None:
        backend = EntryGroundingBackend(Neo4jQueryExecutor(neo4j_driver))

        pending = await backend.get_pending_entries(user_uid=seeded)

        assert pending.is_ok, pending
        assert {row["uid"] for row in pending.value} == GROUNDED

    @pytest.mark.asyncio
    async def test_force_still_excludes_private_and_other_pipelines(
        self, seeded: str, neo4j_driver: AsyncDriver
    ) -> None:
        backend = EntryGroundingBackend(Neo4jQueryExecutor(neo4j_driver))

        pending = await backend.get_pending_entries(user_uid=seeded, force=True)

        assert pending.is_ok, pending
        assert {row["uid"] for row in pending.value} == GROUNDED

    @pytest.mark.asyncio
    async def test_the_pass_grounds_activity_notes_and_credits_each_once(
        self, seeded: str, neo4j_driver: AsyncDriver
    ) -> None:
        bus = _CapturingBus()
        service = EntryGroundingService(
            backend=EntryGroundingBackend(Neo4jQueryExecutor(neo4j_driver)),
            vector_search=_EveryEntryMatchesTheKu(),  # type: ignore[arg-type]
            event_bus=bus,  # type: ignore[arg-type]
        )

        report = await service.ground_pending(UserUID(seeded))

        assert report.is_ok, report
        assert report.value.entries_scanned == len(GROUNDED)
        assert await _linked_entries(neo4j_driver) == GROUNDED
        credited = sorted(
            event.entry_uid
            for event in bus.published
            if isinstance(event, KnowledgeReflectedInEntry)
        )
        assert credited == sorted(GROUNDED)

        # Stamped: a second pass over unchanged text reads nothing.
        again = await service.ground_pending(UserUID(seeded))
        assert again.is_ok and again.value.entries_scanned == 0
