"""An edit that newly links a Ku credits it, once — over the bootstrapped app (CORE tier).

A task's owner links the Kus it applies at create and at ``POST /api/tasks/update``
(``applies_knowledge_uids``, a replace of the owner's set). The substance counter
(``times_applied_in_tasks`` on the Ku) is fed by ``KnowledgeAppliedInTask`` — or
``KnowledgeBulkAppliedInTask`` for two or more — and the update credits only the links
its write created: the guarded write reads, under the task's lock, which far ends no
edge already joined (``build_guarded_link_query``).

- An edit that adds a Ku credits that Ku, once; the Ku already linked is not credited.
- An edit that adds two Kus credits both in one bulk event.
- An edit that names a Ku a grounding pass inferred makes the link the owner's and
  credits nothing: grounding credited it when it inferred it.
- An edit that re-sends the same set credits nothing.

Each test creates its task at the real create door, linking ``KU_NAMED``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.constants import EmbeddingGeometry
from core.events.embedding_events import EmbeddingStored
from core.events.knowledge_substance_events import (
    KnowledgeAppliedInTask,
    KnowledgeBulkAppliedInTask,
)
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, published, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

    from adapters.inbound.fasthtml_types import FastHTMLApp
    from services_bootstrap import Services

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "taskeditcredit"
OWNER = seed_user_uid(f"{MARK}_owner")
KU_NAMED = f"ku.{MARK}.named"
KU_ADDED = f"ku.{MARK}.added"
KU_ADDED_TWO = f"ku.{MARK}.added-two"
KU_BREATH = f"ku.{MARK}.breath"
DIM = EmbeddingGeometry.DIMENSION


def _axis(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index] = 1.0
    return vector


# Axes no other module's Kus carry: the grounding pass reads the whole Ku index.
BREATH = _axis(DIM - 1)
ELSEWHERE = _axis(DIM - 2)


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    services: Services
    driver: AsyncDriver


@dataclass(frozen=True)
class Credit:
    """One substance event: the task it names and the Kus it credits."""

    task_uid: str
    knowledge_uids: tuple[str, ...]
    bulk: bool


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(skuel_app: FastHTMLApp) -> AsyncIterator[Env]:
    services: Services = skuel_app.state.services
    driver: AsyncDriver = services.neo4j_driver
    async with signed_in_client(skuel_app, OWNER, MARK) as client:
        async with driver.session() as session:
            await session.run(
                f"""
                CREATE VECTOR INDEX ku_embedding_idx IF NOT EXISTS
                FOR (n:{NeoLabel.KU.value}) ON (n.embedding)
                OPTIONS {{indexConfig: {{
                    `vector.dimensions`: {DIM}, `vector.similarity_function`: 'cosine'
                }}}}
                """
            )
            await session.run(
                """
                UNWIND $kus AS ku
                MERGE (k:Entity:Ku {uid: ku})
                SET k.title = ku, k.entity_type = 'ku', k.publication_state = 'published'
                """,
                kus=[KU_NAMED, KU_ADDED, KU_ADDED_TWO, KU_BREATH],
            )
        for uid, vector in (
            (KU_BREATH, BREATH),
            (KU_NAMED, ELSEWHERE),
            (KU_ADDED, ELSEWHERE),
            (KU_ADDED_TWO, ELSEWHERE),
        ):
            await _store_vector(driver, NeoLabel.KU, uid, vector)
        async with driver.session() as session:
            await session.run("CALL db.awaitIndexes(120)")
        yield Env(client=client, services=services, driver=driver)


async def _store_vector(
    driver: AsyncDriver, label: NeoLabel, uid: str, vector: list[float]
) -> None:
    """The embedding writer's properties on one node."""
    embeddings = build_production_backends(driver)["embeddings_backend"]
    stored = await embeddings.store_embedding_metadata(
        label, uid, vector, "v1", "text-embedding-3-small", f"{uid}-hash"
    )
    assert stored.is_ok and stored.value, stored


async def _task(env: Env, title: str) -> str:
    """A task created at the door with its owner's link to ``KU_NAMED``."""
    return await create(env.client, "tasks", f"{MARK} {title}", applies_knowledge_uids=[KU_NAMED])


async def _edit(env: Env, task: str, knowledge_uids: list[str]) -> list[Credit]:
    """Post the task's knowledge set at the update door; returns what it credited."""
    bus = env.services.event_bus
    assert bus is not None
    with published(bus, KnowledgeAppliedInTask, KnowledgeBulkAppliedInTask) as seen:
        response = await env.client.post(
            f"/api/tasks/update?uid={task}", json={"applies_knowledge_uids": knowledge_uids}
        )
    assert response.status_code == 200, response.text
    credits: list[Credit] = []
    for event in seen:
        if isinstance(event, KnowledgeBulkAppliedInTask):
            credits.append(Credit(event.task_uid, event.knowledge_uids, bulk=True))
        else:
            assert isinstance(event, KnowledgeAppliedInTask), event
            credits.append(Credit(event.task_uid, (event.knowledge_uid,), bulk=False))
    return credits


async def _applied_count(env: Env, ku_uid: str) -> int:
    async with env.driver.session() as session:
        record = await (
            await session.run(
                "MATCH (k:Ku {uid: $uid}) RETURN coalesce(k.times_applied_in_tasks, 0) AS n",
                uid=ku_uid,
            )
        ).single()
    assert record is not None, ku_uid
    return int(record["n"])


async def _links(env: Env, task: str) -> dict[str, bool]:
    """Each Ku the task applies -> whether the link is inferred (vs its owner's)."""
    async with env.driver.session() as session:
        result = await session.run(
            """
            MATCH (:Task {uid: $uid})-[r:APPLIES_KNOWLEDGE]->(k:Ku)
            RETURN k.uid AS ku, coalesce(r.inferred, false) AS inferred
            """,
            uid=task,
        )
        return {record["ku"]: bool(record["inferred"]) async for record in result}


async def test_an_edit_that_adds_a_ku_credits_it_once(env: Env) -> None:
    task = await _task(env, "practise the added step")
    before = await _applied_count(env, KU_ADDED)
    named_before = await _applied_count(env, KU_NAMED)

    credits = await _edit(env, task, [KU_NAMED, KU_ADDED])

    assert credits == [Credit(task, (KU_ADDED,), bulk=False)]
    assert await _applied_count(env, KU_ADDED) == before + 1
    assert await _applied_count(env, KU_NAMED) == named_before
    assert await _links(env, task) == {KU_NAMED: False, KU_ADDED: False}


async def test_an_edit_that_adds_two_kus_credits_both_in_one_event(env: Env) -> None:
    task = await _task(env, "practise two added steps")

    credits = await _edit(env, task, [KU_ADDED_TWO, KU_NAMED, KU_ADDED])

    assert credits == [Credit(task, (KU_ADDED_TWO, KU_ADDED), bulk=True)]


async def test_an_edit_naming_an_inferred_ku_promotes_it_and_credits_nothing(env: Env) -> None:
    task = await _task(env, "notice the breath")
    await _store_vector(env.driver, NeoLabel.TASK, task, BREATH)
    bus = env.services.event_bus
    assert bus is not None
    with published(bus, KnowledgeAppliedInTask) as grounded:
        await bus.publish_async(EmbeddingStored(entity_uid=task, entity_type=EntityType.TASK.value))
    # Grounding inferred the link and credited it.
    assert [event.knowledge_uid for event in grounded] == [KU_BREATH]
    assert await _links(env, task) == {KU_NAMED: False, KU_BREATH: True}
    before = await _applied_count(env, KU_BREATH)

    credits = await _edit(env, task, [KU_NAMED, KU_BREATH])

    assert credits == []
    assert await _applied_count(env, KU_BREATH) == before
    assert await _links(env, task) == {KU_NAMED: False, KU_BREATH: False}


async def test_an_edit_that_resends_the_same_set_credits_nothing(env: Env) -> None:
    task = await _task(env, "practise the named step")
    before = await _applied_count(env, KU_NAMED)

    credits = await _edit(env, task, [KU_NAMED])

    assert credits == []
    assert await _applied_count(env, KU_NAMED) == before
