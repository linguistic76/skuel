"""A task is grounded to the Kus it applies once its embedding is stored, as an entry is.

The path is the one the FULL tier runs, in-process over the testcontainer: the Tasks
create and update doors (``TasksCoreService``) request the task's embedding, the
embedding worker generates and stores it through the one embedding writer and
announces ``EmbeddingStored``, and ``TaskGroundingService`` queries the real Ku
vector index (``ku_embedding_idx``) with the stored vector and writes
``(task)-[:APPLIES_KNOWLEDGE {inferred: true, confidence, grounded_at}]->(ku)``. Only
the inference client is a stand-in: it maps a text to a fixed vector by the word it
holds, and every Ku's vector is stored by the same writer.

- A task grounds to the published Ku its vector matches, and the new edge credits
  the Ku once (``KnowledgeAppliedInTask``); a Ku below the threshold is not linked.
- A draft Ku is never grounded: the vector query withholds it from the candidates,
  and the write refuses it besides.
- A removal is recorded and never re-inferred, by a re-ground of changed text or by
  a forced pass.
- Unchanged text does not re-ground: the worker announces no new vector, and a pass
  over the task reads it as stamped.
- Changed text re-grounds: the new vector's Ku is linked.
- A cancelled task is never grounded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from core.constants import EmbeddingGeometry
from core.events.embedding_events import EmbeddingStored
from core.events.knowledge_substance_events import KnowledgeAppliedInTask
from core.models.enums import EntityStatus
from core.models.enums.neo_labels import NeoLabel
from core.models.task.task_request import TaskCreateRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.models.type_hints import UserUID
from core.services.background.embedding_worker import EmbeddingBackgroundWorker
from core.services.embeddings_service import EmbeddingsService
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.services.tasks.task_grounding_service import TaskGroundingService
from core.services.tasks.tasks_core_service import TasksCoreService
from core.utils.result_simplified import Result
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

    from adapters.persistence.neo4j.task_grounding_backend import TaskGroundingBackend

DIM = EmbeddingGeometry.DIMENSION
OWNER = seed_user_uid("task_grounding_owner")

KU_BREATH = "ku.taskground.breath"
KU_BREATH_NEXT = "ku.taskground.breath-next"  # seeded only by the tests that need it
KU_STILLNESS = "ku.taskground.stillness"
KU_DRAFT = "ku.taskground.draft"
KU_FAR = "ku.taskground.far"


def _axis(index: int) -> list[float]:
    """A unit vector along one axis: score 1.0 with itself, 0.5 with any other axis."""
    vector = [0.0] * DIM
    vector[index] = 1.0
    return vector


BREATH = _axis(0)
STILLNESS = _axis(1)
ELSEWHERE = _axis(2)
FAR = _axis(3)


def _vector_for(text: str) -> list[float]:
    """The stand-in model: a text about the breath, or stillness, or neither."""
    lowered = text.lower()
    if "stillness" in lowered:
        return STILLNESS
    if "breath" in lowered:
        return BREATH
    return ELSEWHERE


class _Model:
    """The inference client the embedding writer calls; only ``embed`` is stood in."""

    model = "text-embedding-3-small"
    dimension = DIM
    max_input_chars = 20000

    async def embed(self, text: str) -> Result[list[float]]:
        return Result.ok(_vector_for(text))


@dataclass
class Rig:
    driver: AsyncDriver
    tasks: TasksCoreService
    worker: EmbeddingBackgroundWorker
    grounding: TaskGroundingService
    backend: TaskGroundingBackend
    embeddings: EmbeddingsService
    applied: list[KnowledgeAppliedInTask]
    stored: list[EmbeddingStored]

    async def create(self, title: str, description: str = "") -> str:
        result = await self.tasks.create_task(
            TaskCreateRequest(title=title, description=description or None), UserUID(OWNER)
        )
        assert result.is_ok, result
        return result.value.uid

    async def update(self, uid: str, intent: TaskUpdateIntent) -> None:
        result = await self.tasks.update_task(uid, intent)
        assert result.is_ok, result

    async def settle(self) -> None:
        """Run the worker's queue to empty — the embedding, then the grounding it announces."""
        await self.worker.drain()

    async def seed_ku(self, uid: str, vector: list[float], state: str = "published") -> None:
        async with self.driver.session() as session:
            await session.run(
                """
                MERGE (k:Entity:Ku {uid: $uid})
                SET k.title = $uid, k.entity_type = 'ku', k.publication_state = $state
                """,
                uid=uid,
                state=state,
            )
        stored = await self.embeddings.store_embedding_with_metadata(
            uid=uid, label=NeoLabel.KU.value, embedding=vector, text=uid
        )
        assert stored.is_ok, stored
        async with self.driver.session() as session:
            await session.run("CALL db.awaitIndexes(120)")

    async def inferred(self, task_uid: str) -> dict[str, dict[str, object]]:
        """Each inferred edge from the task: Ku uid -> its provenance."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (:Task {uid: $uid})-[r:APPLIES_KNOWLEDGE]->(k:Ku)
                WHERE r.inferred
                RETURN k.uid AS ku, r.confidence AS confidence,
                       r.grounded_at IS NOT NULL AS stamped
                """,
                uid=task_uid,
            )
            return {
                record["ku"]: {"confidence": record["confidence"], "stamped": record["stamped"]}
                async for record in result
            }


@pytest_asyncio.fixture
async def rig(neo4j_driver: AsyncDriver, clean_neo4j: object) -> AsyncIterator[Rig]:
    async with neo4j_driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=OWNER)
        await session.run("MATCH (:User {uid: $uid})-[:OWNS]->(n) DETACH DELETE n", uid=OWNER)
    backends = build_production_backends(neo4j_driver)
    bus = InMemoryEventBus()
    embeddings = EmbeddingsService(backends["embeddings_backend"], embedding_client=_Model())
    worker = EmbeddingBackgroundWorker(event_bus=bus, embeddings_service=embeddings)
    worker.subscribe()
    grounding = TaskGroundingService(
        backend=backends["task_grounding_backend"],
        vector_search=Neo4jVectorSearchService(backends["vector_search_backend"]),
        event_bus=bus,
    )
    bus.subscribe(EmbeddingStored, grounding.handle_embedding_stored)
    applied: list[KnowledgeAppliedInTask] = []
    stored: list[EmbeddingStored] = []

    async def _on_applied(event: KnowledgeAppliedInTask) -> None:
        applied.append(event)

    async def _on_stored(event: EmbeddingStored) -> None:
        stored.append(event)

    bus.subscribe(KnowledgeAppliedInTask, _on_applied)
    bus.subscribe(EmbeddingStored, _on_stored)
    the_rig = Rig(
        driver=neo4j_driver,
        tasks=TasksCoreService(backend=backends["tasks_backend"], event_bus=bus),
        worker=worker,
        grounding=grounding,
        backend=backends["task_grounding_backend"],
        embeddings=embeddings,
        applied=applied,
        stored=stored,
    )
    await the_rig.seed_ku(KU_BREATH, BREATH)
    await the_rig.seed_ku(KU_STILLNESS, STILLNESS)
    await the_rig.seed_ku(KU_DRAFT, BREATH, state="draft")
    await the_rig.seed_ku(KU_FAR, FAR)
    yield the_rig
    async with neo4j_driver.session() as session:
        await session.run("MATCH (:User {uid: $uid})-[:OWNS]->(n) DETACH DELETE n", uid=OWNER)


@pytest.mark.integration
@pytest.mark.asyncio
class TestTaskGrounding:
    async def test_a_new_task_grounds_to_the_published_ku_its_vector_matches(
        self, rig: Rig
    ) -> None:
        task = await rig.create("Notice the breath before work")

        await rig.settle()

        assert [event.entity_uid for event in rig.stored] == [task]
        links = await rig.inferred(task)
        assert set(links) == {KU_BREATH}, links
        assert links[KU_BREATH]["confidence"] == pytest.approx(1.0)
        assert links[KU_BREATH]["stamped"]
        assert [(event.knowledge_uid, event.task_uid) for event in rig.applied] == [
            (KU_BREATH, task)
        ]
        assert rig.applied[0].user_uid == OWNER

    async def test_a_draft_ku_is_never_a_candidate(self, rig: Rig) -> None:
        """The vector query withholds the draft, though its vector matches exactly."""
        task = await rig.create("Notice the breath at noon")
        await rig.settle()

        dry = await rig.grounding.ground_pending(source_uid=task, force=True, apply=False)

        assert dry.is_ok, dry
        candidates = {c.ku_uid for outcome in dry.value.outcomes for c in outcome.written}
        assert KU_DRAFT not in candidates
        assert KU_DRAFT not in await rig.inferred(task)

    async def test_the_write_refuses_a_draft_ku(self, rig: Rig) -> None:
        """The write's own gate: a draft handed to it links nothing."""
        task = await rig.create("Notice the breath at dusk")

        written = await rig.backend.write_applies_knowledge(task, KU_DRAFT, 0.9)

        assert written.is_ok and written.value is False
        assert KU_DRAFT not in await rig.inferred(task)

    async def test_a_removed_link_is_never_re_inferred(self, rig: Rig) -> None:
        task = await rig.create("Notice the breath on the walk")
        await rig.settle()
        assert KU_BREATH in await rig.inferred(task)

        removed = await rig.grounding.remove(task, KU_BREATH, UserUID(OWNER))
        assert removed.is_ok and removed.value is True
        assert await rig.inferred(task) == {}

        # Changed text that still matches the Ku re-grounds the task ...
        await rig.update(task, TaskUpdateIntent(title="Notice the breath on the long walk"))
        await rig.settle()
        assert [event.entity_uid for event in rig.stored] == [task, task]
        # ... and neither that pass nor a forced one re-infers the removed pair.
        forced = await rig.grounding.ground_pending(source_uid=task, force=True)
        assert forced.is_ok, forced
        assert await rig.inferred(task) == {}
        assert [event.knowledge_uid for event in rig.applied] == [KU_BREATH]

    async def test_unchanged_text_does_not_re_ground(self, rig: Rig) -> None:
        task = await rig.create("Notice the breath in the evening")
        await rig.settle()
        # A Ku the task's vector matches, published after its pass: only a new pass links it.
        await rig.seed_ku(KU_BREATH_NEXT, BREATH)

        await rig.update(task, TaskUpdateIntent(title="Notice the breath in the evening"))
        await rig.update(task, TaskUpdateIntent(priority="high"))
        await rig.settle()

        assert [event.entity_uid for event in rig.stored] == [task]
        again = await rig.grounding.ground_pending(source_uid=task)
        assert again.is_ok and again.value.scanned == 0
        assert set(await rig.inferred(task)) == {KU_BREATH}

    async def test_changed_text_re_grounds(self, rig: Rig) -> None:
        task = await rig.create("Notice the breath")
        await rig.settle()

        await rig.update(task, TaskUpdateIntent(title="Sit in stillness"))
        await rig.settle()

        assert [event.entity_uid for event in rig.stored] == [task, task]
        links = await rig.inferred(task)
        assert set(links) == {KU_BREATH, KU_STILLNESS}, links
        assert [event.knowledge_uid for event in rig.applied] == [KU_BREATH, KU_STILLNESS]

    async def test_a_cancelled_task_is_never_grounded(self, rig: Rig) -> None:
        task = await rig.create("Notice the breath, then drop it")
        await rig.update(task, TaskUpdateIntent(status=EntityStatus.CANCELLED.value))

        await rig.settle()

        assert [event.entity_uid for event in rig.stored] == [task]
        assert await rig.inferred(task) == {}
        written = await rig.backend.write_applies_knowledge(task, KU_BREATH, 0.9)
        assert written.is_ok and written.value is False


def test_the_stand_in_model_separates_the_three_texts() -> None:
    """Control on the rig: each text lands on its own axis, so a match is the word's."""
    assert _vector_for("the Breath") == BREATH
    assert _vector_for("stillness and breath") == STILLNESS
    assert _vector_for("a walk") == ELSEWHERE
