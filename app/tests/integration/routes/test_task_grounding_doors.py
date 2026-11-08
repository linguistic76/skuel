"""The doors around a task's inferred knowledge, over the bootstrapped app (CORE tier).

``TaskGroundingService`` writes ``(task)-[:APPLIES_KNOWLEDGE {inferred: true}]->(ku)``
once the embedding worker announces a stored task vector (``EmbeddingStored``). The
worker runs in FULL only, so in CORE nothing announces and a task carries only the
knowledge its owner links. Each test creates a task at the real create door, linking
one Ku by name, and stores a vector on it through the embedding writer — the shape a
task embedded under FULL keeps.

- **CORE writes nothing.** A create and a text edit at the doors leave no inferred
  edge and none of the keyword properties. Control: announcing the vector on the
  app's own bus grounds the task, so the composed handler is wired and only the
  announcement is missing.
- **The removal door** removes an inferred link and records it; another user's
  request, the owner's link, and a link already removed answer 404.
- **The owner's update door** promotes an inferred link it names to the owner's,
  and a replace of the owner's links leaves an inferred one in place.
- **The owner's cached context** reads a link grounding wrote after the context was
  built: the pass announces ``EntityLinksChanged``, as every link door does.
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
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import UserUID
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, signed_in_client

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

MARK = "taskgrounddoor"
OWNER = seed_user_uid(f"{MARK}_owner")
STRANGER = seed_user_uid(f"{MARK}_stranger")
KU_BREATH = f"ku.{MARK}.breath"
KU_NAMED = f"ku.{MARK}.named"
DIM = EmbeddingGeometry.DIMENSION
KEYWORD_PROPERTIES = (
    "knowledge_confidence_scores",
    "knowledge_inference_metadata",
    "learning_opportunities_count",
)


def _axis(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index] = 1.0
    return vector


BREATH = _axis(0)
NAMED = _axis(1)


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    stranger: httpx.AsyncClient
    services: Services
    driver: AsyncDriver


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(skuel_app: FastHTMLApp) -> AsyncIterator[Env]:
    services: Services = skuel_app.state.services
    driver: AsyncDriver = services.neo4j_driver
    async with (
        signed_in_client(skuel_app, OWNER, MARK) as client,
        signed_in_client(skuel_app, STRANGER, f"{MARK}stranger") as stranger,
    ):
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
                kus=[KU_BREATH, KU_NAMED],
            )
        for uid, vector in ((KU_BREATH, BREATH), (KU_NAMED, NAMED)):
            await _store_vector(driver, NeoLabel.KU, uid, vector)
        async with driver.session() as session:
            await session.run("CALL db.awaitIndexes(120)")
        yield Env(client=client, stranger=stranger, services=services, driver=driver)


async def _store_vector(
    driver: AsyncDriver, label: NeoLabel, uid: str, vector: list[float]
) -> None:
    """The embedding writer's properties on one node."""
    embeddings = build_production_backends(driver)["embeddings_backend"]
    stored = await embeddings.store_embedding_metadata(
        label, uid, vector, "v1", "text-embedding-3-small", f"{uid}-hash"
    )
    assert stored.is_ok and stored.value, stored


async def _embedded_task(env: Env, title: str) -> str:
    """A task created at the door with its owner's link to ``KU_NAMED``, then embedded."""
    task = await create(env.client, "tasks", f"{MARK} {title}", applies_knowledge_uids=[KU_NAMED])
    await _store_vector(env.driver, NeoLabel.TASK, task, BREATH)
    return task


async def _announce(env: Env, task: str) -> None:
    """What the FULL tier's worker publishes once it stores a task's vector."""
    assert env.services.event_bus is not None
    await env.services.event_bus.publish_async(
        EmbeddingStored(entity_uid=task, entity_type=EntityType.TASK.value)
    )


async def _links(env: Env, task: str) -> dict[str, bool]:
    """Each Ku the task applies -> whether the link is inferred (vs its owner's)."""
    async with env.driver.session() as session:
        result = await session.run(
            """
            MATCH (:Task {uid: $uid})-[r:APPLIES_KNOWLEDGE]->(k:Ku)
            RETURN k.uid AS ku, coalesce(r.inferred, false) AS inferred,
                   r.confidence IS NOT NULL OR r.grounded_at IS NOT NULL AS stamped
            """,
            uid=task,
        )
        links: dict[str, bool] = {}
        async for record in result:
            assert record["inferred"] == record["stamped"], dict(record)
            links[record["ku"]] = bool(record["inferred"])
        return links


async def _rejected(env: Env, task: str) -> list[str]:
    async with env.driver.session() as session:
        record = await (
            await session.run(
                "MATCH (t:Task {uid: $uid}) RETURN coalesce(t.grounding_rejected_ku_uids, []) AS r",
                uid=task,
            )
        ).single()
    assert record is not None
    return list(record["r"])


async def _update(env: Env, task: str, **fields: object) -> None:
    response = await env.client.post(f"/api/tasks/update?uid={task}", json=fields)
    assert response.status_code == 200, response.text


async def test_core_writes_nothing(env: Env) -> None:
    task = await _embedded_task(env, "notice the breath")

    await _update(env, task, title=f"{MARK} notice the breath at noon")

    assert await _links(env, task) == {KU_NAMED: False}
    async with env.driver.session() as session:
        record = await (
            await session.run(
                "MATCH (t:Task {uid: $uid}) RETURN [k IN keys(t) WHERE k IN $names] AS present",
                uid=task,
                names=list(KEYWORD_PROPERTIES),
            )
        ).single()
    assert record is not None and record["present"] == []

    # Control: the composed handler grounds once the vector is announced.
    await _announce(env, task)
    assert await _links(env, task) == {KU_NAMED: False, KU_BREATH: True}


async def test_the_removal_door_removes_an_inferred_link_and_records_it(env: Env) -> None:
    task = await _embedded_task(env, "breathe before replying")
    await _announce(env, task)
    assert await _links(env, task) == {KU_NAMED: False, KU_BREATH: True}
    foreign = await env.stranger.post(
        "/api/tasks/grounding/remove", params={"uid": task, "ku_uid": KU_BREATH}
    )
    assert foreign.status_code == 404, foreign.text
    assert await _links(env, task) == {KU_NAMED: False, KU_BREATH: True}

    removed = await env.client.post(
        "/api/tasks/grounding/remove", params={"uid": task, "ku_uid": KU_BREATH}
    )

    assert removed.status_code == 200, removed.text
    assert removed.json() == {"uid": task, "ku_uid": KU_BREATH, "removed": True}
    assert await _links(env, task) == {KU_NAMED: False}
    assert await _rejected(env, task) == [KU_BREATH]
    again = await env.client.post(
        "/api/tasks/grounding/remove", params={"uid": task, "ku_uid": KU_BREATH}
    )
    assert again.status_code == 404
    owners = await env.client.post(
        "/api/tasks/grounding/remove", params={"uid": task, "ku_uid": KU_NAMED}
    )
    assert owners.status_code == 404
    assert await _links(env, task) == {KU_NAMED: False}
    # A later announcement does not re-infer the removed pair.
    await _announce(env, task)
    assert await _links(env, task) == {KU_NAMED: False}


async def test_an_update_naming_an_inferred_ku_makes_it_the_owners(env: Env) -> None:
    task = await _embedded_task(env, "count ten breaths")
    await _announce(env, task)
    assert await _links(env, task) == {KU_NAMED: False, KU_BREATH: True}

    await _update(env, task, applies_knowledge_uids=[KU_NAMED, KU_BREATH])

    assert await _links(env, task) == {KU_NAMED: False, KU_BREATH: False}
    removed = await env.client.post(
        "/api/tasks/grounding/remove", params={"uid": task, "ku_uid": KU_BREATH}
    )
    assert removed.status_code == 404


async def test_replacing_the_owners_links_leaves_the_inferred_one(env: Env) -> None:
    task = await _embedded_task(env, "breathe through the doorway")
    await _announce(env, task)
    assert await _links(env, task) == {KU_NAMED: False, KU_BREATH: True}

    await _update(env, task, applies_knowledge_uids=[])

    assert await _links(env, task) == {KU_BREATH: True}


async def test_the_owners_cached_context_reads_a_grounded_link(env: Env) -> None:
    task = await _embedded_task(env, "breathe at the threshold")
    users = env.services.user
    assert users is not None
    before = await users.get_rich_unified_context(UserUID(OWNER))
    assert before.is_ok, before
    assert before.value.task_knowledge_applied.get(task) == [KU_NAMED]

    await _announce(env, task)

    after = await users.get_rich_unified_context(UserUID(OWNER))
    assert after.is_ok, after
    assert sorted(after.value.task_knowledge_applied.get(task, [])) == sorted([KU_NAMED, KU_BREATH])
