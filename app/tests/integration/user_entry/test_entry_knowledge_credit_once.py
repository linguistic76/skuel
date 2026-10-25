"""An entry's link to a piece of knowledge is credited once, whichever writer made it.

An entry's ``APPLIES_KNOWLEDGE`` edge has two writers: the owner's ``@ku()``
reference on an EXTRACT_ACTIVITIES entry (``UserEntryService.link_applied_knowledge``
→ ``UserEntryBackend.write_applied_knowledge``) and the grounding pass
(``EntryGroundingBackend.write_applies_knowledge``). Each new edge publishes one
``KnowledgeReflectedInEntry`` — a substance credit, which is never taken back. So:

- an inferred edge the owner then names is not credited again, and becomes the
  owner's own (its inference stamp is cleared);
- a link the owner removed and then names is linked again without a second credit;
- an edge the owner named is not re-made or re-stamped by the grounding pass;
- of the two writers racing on one pair, exactly one reports a new edge.

Everything from the extractor outward is the real code over real Neo4j; entity
creation goes through the pipeline suite's graph-writing task stub.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from adapters.persistence.neo4j.entry_grounding_backend import EntryGroundingBackend
from core.events.knowledge_substance_events import KnowledgeReflectedInEntry
from core.models.enums.pipeline import Pipeline
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.dsl.activity_extractor import ActivityExtractorService
from core.services.user_entry.user_entry_processing_service import (
    UserEntryProcessingService,
)
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration.user_entry.test_extract_activities_pipeline import (
    _GraphTasksStub,
    _seed_ku,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.events.base import BaseEvent
    from core.models.user_entry.user_entry import UserEntry
    from core.services.user_entry.user_entry_service import UserEntryService


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def credited(self) -> list[str]:
        return [e.knowledge_uid for e in self.events if isinstance(e, KnowledgeReflectedInEntry)]


async def _entry(user_entry_service: UserEntryService, user_uid: str, content: str) -> UserEntry:
    result = await user_entry_service.create_entry(
        request=UserEntryCreateRequest(
            title="Daily", content=content, pipeline=Pipeline.EXTRACT_ACTIVITIES
        ),
        user_uid=user_uid,
    )
    assert result.is_ok, result
    entry, _share = result.value
    return entry


async def _process(
    neo4j_driver: AsyncDriver, user_entry_service: UserEntryService, entry: UserEntry
) -> list[str]:
    bus = _RecordingBus()
    dispatcher = UserEntryProcessingService(
        entry_service=user_entry_service,
        event_bus=bus,
        activity_extractor=ActivityExtractorService(tasks_service=_GraphTasksStub(neo4j_driver)),
    )
    result = await dispatcher.process(entry, force=True)
    assert result.is_ok, result
    return bus.credited()


async def _edges(neo4j_driver: AsyncDriver, entry_uid: str, ku_uid: str) -> list[dict[str, object]]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (:UserEntry {uid: $entry})-[r:APPLIES_KNOWLEDGE]->(:Ku {uid: $ku})
            RETURN r.inferred AS inferred, r.confidence AS confidence,
                   r.grounded_at AS grounded_at
            """,
            entry=entry_uid,
            ku=ku_uid,
        )
        return await result.data()


@pytest.fixture
def grounding(neo4j_driver: AsyncDriver) -> EntryGroundingBackend:
    return build_production_backends(neo4j_driver)["entry_grounding_backend"]


@pytest.mark.integration
class TestEntryKnowledgeCreditedOnce:
    @pytest.mark.asyncio
    async def test_an_inferred_link_the_owner_names_becomes_theirs_without_a_second_credit(
        self, neo4j_driver, user_entry_service, seed_user, grounding
    ):
        user_uid = await seed_user(seed_user_uid(f"credit_{uuid4().hex[:6]}"))
        inferred = await _seed_ku(neo4j_driver, f"ku.it.inferred-{uuid4().hex[:6]}")
        fresh = await _seed_ku(neo4j_driver, f"ku.it.fresh-{uuid4().hex[:6]}")
        entry = await _entry(
            user_entry_service,
            user_uid,
            f"- [ ] Read on it @context(task) @ku({inferred})\n"
            f"- [ ] Read on more @context(task) @ku({fresh})\n",
        )
        written = await grounding.write_applies_knowledge(entry.uid, inferred, 0.74)
        assert written.is_ok and written.value is True

        credited = await _process(neo4j_driver, user_entry_service, entry)

        # Control: the reference no edge stood for is credited, once.
        assert credited == [fresh]
        assert await _edges(neo4j_driver, entry.uid, inferred) == [
            {"inferred": None, "confidence": None, "grounded_at": None}
        ]

    @pytest.mark.asyncio
    async def test_a_removed_link_the_owner_names_relinks_without_a_second_credit(
        self, neo4j_driver, user_entry_service, seed_user, grounding
    ):
        user_uid = await seed_user(seed_user_uid(f"credit_{uuid4().hex[:6]}"))
        removed = await _seed_ku(neo4j_driver, f"ku.it.removed-{uuid4().hex[:6]}")
        fresh = await _seed_ku(neo4j_driver, f"ku.it.fresh-{uuid4().hex[:6]}")
        entry = await _entry(
            user_entry_service,
            user_uid,
            f"- [ ] Read on it @context(task) @ku({removed})\n"
            f"- [ ] Read on more @context(task) @ku({fresh})\n",
        )
        # The grounding pass links and credits the pair; the owner removes it.
        assert (await grounding.write_applies_knowledge(entry.uid, removed, 0.74)).value is True
        removal = await grounding.remove_grounded_edge(entry.uid, removed, UserUID(user_uid))
        assert removal.is_ok and removal.value is not None

        credited = await _process(neo4j_driver, user_entry_service, entry)

        assert credited == [fresh]
        assert await _edges(neo4j_driver, entry.uid, removed) == [
            {"inferred": None, "confidence": None, "grounded_at": None}
        ]

    @pytest.mark.asyncio
    async def test_the_grounding_pass_leaves_a_named_link_alone(
        self, neo4j_driver, user_entry_service, seed_user, grounding
    ):
        user_uid = await seed_user(seed_user_uid(f"credit_{uuid4().hex[:6]}"))
        named = await _seed_ku(neo4j_driver, f"ku.it.named-{uuid4().hex[:6]}")
        entry = await _entry(
            user_entry_service, user_uid, f"- [ ] Read on it @context(task) @ku({named})\n"
        )

        assert await _process(neo4j_driver, user_entry_service, entry) == [named]
        written = await grounding.write_applies_knowledge(entry.uid, named, 0.9)

        assert written.is_ok and written.value is False
        assert await _edges(neo4j_driver, entry.uid, named) == [
            {"inferred": None, "confidence": None, "grounded_at": None}
        ]
        # A re-run of the extraction credits nothing it credited before.
        assert await _process(neo4j_driver, user_entry_service, entry) == []

    @pytest.mark.asyncio
    async def test_of_two_writers_racing_on_one_pair_exactly_one_makes_the_edge(
        self, neo4j_driver, user_entry_backend, seed_user, grounding
    ):
        for _ in range(20):
            entry_uid = f"ue.credit-race-{uuid4().hex[:8]}"
            ku_uid = await _seed_ku(neo4j_driver, f"ku.it.race-{uuid4().hex[:8]}")
            async with neo4j_driver.session() as session:
                await session.run(
                    "CREATE (:Entity:UserEntry {uid: $uid, entity_type: 'user_entry', "
                    "pipeline: 'extract_activities', title: 'race'})",
                    uid=entry_uid,
                )

            explicit, inferred = await asyncio.gather(
                user_entry_backend.write_applied_knowledge(entry_uid, ku_uid),
                grounding.write_applies_knowledge(entry_uid, ku_uid, 0.8),
            )

            assert explicit.is_ok and explicit.value is not None, explicit
            assert inferred.is_ok, inferred
            made = int(explicit.value["created"]) + int(inferred.value)
            assert made == 1, (explicit.value, inferred.value)
            assert len(await _edges(neo4j_driver, entry_uid, ku_uid)) == 1
