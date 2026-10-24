"""A link is written on the facts its write reads — over real HTTP and a real graph.

A link door admits its far end (``core/services/mixins/link_edge_guard.py``) in reads
taken before the write. The write itself re-asserts that rule in the statement that
merges the edge (``write_guarded_links``), so a far end unpublished, re-owned or deleted
between the admission and the write is refused there, as a uid that names nothing is —
and a replacement (the Events and Tasks update doors) deletes the old edge in the same
transaction that writes the new one, so a refused new link leaves the old one in place.

The window between the admission and the write is opened on purpose: the admission
(``UnifiedRelationshipService.admit_far_ends``, or the Tasks update's
``partition_link_edges``) is wrapped so that, once it has admitted the far end, another
writer changes that far end. Each test has a control: the same request with nothing
changed in the window links.

The routes are the bootstrap's own, over the composed app
(``tests/integration/_activity_link_rig.py``); entities are created at the real create
doors.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

import core.services.tasks_service as tasks_service_module
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.relationship_names import RelationshipName
from core.services.mixins.link_edge_guard import AdmittedFarEnds, LinkFarEnd
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import (
    Edge,
    create,
    edges_between,
    signed_in_client,
    wipe,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    import httpx
    from neo4j import AsyncDriver

    from core.utils.result_simplified import Result

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzlinkatom"
CALLER = seed_user_uid(f"{MARK}")
OTHER = seed_user_uid(f"{MARK}_other")  # takes a far end over in the window; never signs in

REQUIRES_KNOWLEDGE = RelationshipName.REQUIRES_KNOWLEDGE.value
REINFORCES_HABIT = RelationshipName.REINFORCES_HABIT.value
CELEBRATES_GOAL = RelationshipName.CELEBRATES_GOAL.value
CONTRIBUTES_TO_GOAL = RelationshipName.CONTRIBUTES_TO_GOAL.value

Mutation = Callable[[str], Awaitable[None]]
_Service = UnifiedRelationshipService[Any, Any, Any]  # boundary: any domain's service is patched

_EVENT_FIELDS = {"event_date": "2026-11-01", "start_time": "09:00", "end_time": "10:00"}


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    driver: AsyncDriver


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[Env]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        yield Env(client=client, driver=driver)
    await wipe(driver, OTHER, MARK)


async def _run(driver: AsyncDriver, query: str, **params: Any) -> None:  # boundary: Cypher params
    async with driver.session() as session:
        await session.run(query, **params)


async def _seed_ku(env: Env, name: str) -> str:
    """A shared Ku, published: no owner, ``publication_state: published``."""
    uid = f"ku.{MARK}-{name}"
    await _run(
        env.driver,
        """
        MERGE (k:Entity:Ku {uid: $uid})
        SET k.title = $uid, k.entity_type = 'ku', k.status = 'active',
            k.publication_state = 'published'
        """,
        uid=uid,
    )
    return uid


def _unpublish(env: Env) -> Mutation:
    async def mutate(uid: str) -> None:
        await _run(
            env.driver, "MATCH (n:Entity {uid: $uid}) SET n.publication_state = 'draft'", uid=uid
        )

    return mutate


def _reown(env: Env) -> Mutation:
    """Move the node to ``OTHER`` in every spelling ownership has."""

    async def mutate(uid: str) -> None:
        await _run(
            env.driver,
            """
            MATCH (n:Entity {uid: $uid})
            OPTIONAL MATCH (:User)-[owns:OWNS]->(n)
            DELETE owns
            WITH DISTINCT n
            MERGE (other:User {uid: $other}) SET other.title = $other
            SET n.user_uid = $other
            MERGE (other)-[:OWNS]->(n)
            """,
            uid=uid,
            other=OTHER,
        )

    return mutate


def _delete(env: Env) -> Mutation:
    async def mutate(uid: str) -> None:
        await _run(env.driver, "MATCH (n:Entity {uid: $uid}) DETACH DELETE n", uid=uid)

    return mutate


def _change_after_admission(
    monkeypatch: pytest.MonkeyPatch, far_uid: str, mutate: Mutation
) -> None:
    """Change ``far_uid`` once the relationship service has admitted it."""
    admit = UnifiedRelationshipService.admit_far_ends

    async def admit_then_change(
        self: _Service,
        from_uid: str,
        to_uids: Sequence[str],
        far_end: LinkFarEnd,
    ) -> Result[AdmittedFarEnds]:
        admitted = await admit(self, from_uid, to_uids, far_end)
        if admitted.is_ok and far_uid in to_uids:
            await mutate(far_uid)
        return admitted

    monkeypatch.setattr(UnifiedRelationshipService, "admit_far_ends", admit_then_change)


def _change_after_task_partition(
    monkeypatch: pytest.MonkeyPatch, far_uid: str, mutate: Mutation
) -> None:
    """Change ``far_uid`` once the Tasks update door has admitted its edges."""
    partition = tasks_service_module.partition_link_edges

    async def partition_then_change(backend: Any, **kwargs: Any) -> Any:  # boundary: guard kwargs
        result = await partition(backend, **kwargs)
        if result.is_ok and any(c.other_uid == far_uid for c in kwargs["candidates"]):
            await mutate(far_uid)
        return result

    monkeypatch.setattr(tasks_service_module, "partition_link_edges", partition_then_change)


def _edge_types(edges: list[Edge], source: str, target: str) -> set[str]:
    return {edge.type for edge in edges if edge.source == source and edge.target == target}


def _masked(
    response: httpx.Response, uid: str
) -> tuple[int, dict[str, Any]]:  # boundary: a JSON error body
    """Status and JSON body with the requested uid masked and the timestamp dropped."""
    body = {
        key: value.replace(uid, "<uid>") if isinstance(value, str) else value
        for key, value in response.json().items()
        if key != "timestamp"
    }
    return response.status_code, body


class TestALinkDoorRefusesAFarEndThatChangedAfterItsAdmission:
    async def test_a_ku_unpublished_after_its_admission_is_not_linked(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        goal = await create(env.client, "goals", f"{MARK} knowledge goal")
        ku = await _seed_ku(env, "unpublished")
        _change_after_admission(monkeypatch, ku, _unpublish(env))

        response = await env.client.post(
            "/api/goals/link-knowledge", json={"goal_uid": goal, "knowledge_uid": ku}
        )
        missing = await env.client.post(
            "/api/goals/link-knowledge",
            json={"goal_uid": goal, "knowledge_uid": f"ku_{MARK}_names_nothing"},
        )

        assert _masked(response, ku) == _masked(missing, f"ku_{MARK}_names_nothing")
        assert response.status_code == 404
        assert _edge_types(await edges_between(env.driver, goal, ku), goal, ku) == set()

    async def test_control_a_ku_left_published_is_linked(self, env: Env) -> None:
        goal = await create(env.client, "goals", f"{MARK} knowledge goal control")
        ku = await _seed_ku(env, "published")

        response = await env.client.post(
            "/api/goals/link-knowledge", json={"goal_uid": goal, "knowledge_uid": ku}
        )

        assert response.status_code == 200, response.text[:500]
        assert _edge_types(await edges_between(env.driver, goal, ku), goal, ku) == {
            REQUIRES_KNOWLEDGE
        }

    async def test_a_habit_taken_over_after_its_admission_is_not_linked(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        event = await create(env.client, "events", f"{MARK} habit event", **_EVENT_FIELDS)
        habit = await create(env.client, "habits", f"{MARK} taken habit")
        _change_after_admission(monkeypatch, habit, _reown(env))

        response = await env.client.post(
            f"/api/events/update?uid={event}", json={"reinforces_habit_uid": habit}
        )

        assert response.status_code == 404, response.text[:500]
        assert _edge_types(await edges_between(env.driver, event, habit), event, habit) == set()

    async def test_control_a_habit_left_the_callers_is_linked(self, env: Env) -> None:
        event = await create(env.client, "events", f"{MARK} habit event control", **_EVENT_FIELDS)
        habit = await create(env.client, "habits", f"{MARK} kept habit")

        response = await env.client.post(
            f"/api/events/update?uid={event}", json={"reinforces_habit_uid": habit}
        )

        assert response.status_code == 200, response.text[:500]
        assert _edge_types(await edges_between(env.driver, event, habit), event, habit) == {
            REINFORCES_HABIT
        }


class TestAReplacementKeepsTheOldLinkWhenTheNewOneIsRefused:
    async def _event_celebrating(self, env: Env, name: str) -> tuple[str, str]:
        event = await create(env.client, "events", f"{MARK} {name}", **_EVENT_FIELDS)
        old_goal = await create(env.client, "goals", f"{MARK} {name} old goal")
        linked = await env.client.post(
            f"/api/events/update?uid={event}", json={"milestone_celebration_for_goal": old_goal}
        )
        assert linked.status_code == 200, linked.text[:500]
        return event, old_goal

    async def test_an_events_goal_deleted_after_its_admission_keeps_the_old_goal(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        event, old_goal = await self._event_celebrating(env, "replace event")
        new_goal = await create(env.client, "goals", f"{MARK} replace event new goal")
        _change_after_admission(monkeypatch, new_goal, _delete(env))

        response = await env.client.post(
            f"/api/events/update?uid={event}", json={"milestone_celebration_for_goal": new_goal}
        )

        assert _edge_types(await edges_between(env.driver, event, old_goal), event, old_goal) == {
            CELEBRATES_GOAL
        }
        assert response.status_code == 404, response.text[:500]

    async def test_control_an_events_goal_is_replaced(self, env: Env) -> None:
        event, old_goal = await self._event_celebrating(env, "replace event control")
        new_goal = await create(env.client, "goals", f"{MARK} replace event control new goal")

        response = await env.client.post(
            f"/api/events/update?uid={event}", json={"milestone_celebration_for_goal": new_goal}
        )

        assert response.status_code == 200, response.text[:500]
        assert (
            _edge_types(await edges_between(env.driver, event, old_goal), event, old_goal) == set()
        )
        assert _edge_types(await edges_between(env.driver, event, new_goal), event, new_goal) == {
            CELEBRATES_GOAL
        }

    async def _task_contributing(self, env: Env, name: str) -> tuple[str, str]:
        old_goal = await create(env.client, "goals", f"{MARK} {name} old goal")
        task = await create(
            env.client, "tasks", f"{MARK} {name}", contributes_to_goal_uids=[old_goal]
        )
        return task, old_goal

    async def test_a_tasks_goal_deleted_after_its_admission_keeps_the_old_goal(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task, old_goal = await self._task_contributing(env, "replace task")
        new_goal = await create(env.client, "goals", f"{MARK} replace task new goal")
        _change_after_task_partition(monkeypatch, new_goal, _delete(env))

        response = await env.client.post(
            f"/api/tasks/update?uid={task}", json={"contributes_to_goal_uids": [new_goal]}
        )

        assert _edge_types(await edges_between(env.driver, task, old_goal), task, old_goal) == {
            CONTRIBUTES_TO_GOAL
        }
        assert response.status_code == 404, response.text[:500]

    async def test_control_a_tasks_goal_set_is_replaced(self, env: Env) -> None:
        task, old_goal = await self._task_contributing(env, "replace task control")
        new_goal = await create(env.client, "goals", f"{MARK} replace task control new goal")

        response = await env.client.post(
            f"/api/tasks/update?uid={task}", json={"contributes_to_goal_uids": [new_goal]}
        )

        assert response.status_code == 200, response.text[:500]
        assert _edge_types(await edges_between(env.driver, task, old_goal), task, old_goal) == set()
        assert _edge_types(await edges_between(env.driver, task, new_goal), task, new_goal) == {
            CONTRIBUTES_TO_GOAL
        }
