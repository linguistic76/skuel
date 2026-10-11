"""The shared route factories answer the shapes their handlers declare, over the bootstrapped app.

The JSON handlers ``hierarchy_api_factory``, ``lateral_route_factory`` and
``activity_link_api_factory`` build name the dict they answer as a TypedDict. mypy holds a
handler's body to that name; these tests hold the response a client receives to it — the
body's keys are the TypedDict's keys (a write's ``_headers`` leave the body for the response
headers).

The habit hierarchy builds its answer by hand (every habit hydrated), so it is read beside
the task one, both from a real parent-child edge written at the add-child door.

Entities are created at the domains' real create doors (``_activity_link_rig.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from adapters.inbound.route_factories.activity_link_api_factory import (
    KnowledgePatternsPayload,
    LinkedPayload,
)
from adapters.inbound.route_factories.hierarchy_api_factory import (
    ChildAddedPayload,
    ChildRemovedPayload,
)
from adapters.inbound.route_factories.lateral_route_factory import (
    BlockedPayload,
    BlockingCreatedPayload,
    BlockingPayload,
    LateralDeletedPayload,
    SiblingsPayload,
)
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.ports.query_types import DerivedSiblingItem, EntityHierarchy, LateralRelationshipItem
from tests.integration._activity_link_rig import create, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzrfpay"
USER = f"user_{MARK}"


def _keys(payload: Any) -> set[str]:  # boundary: any TypedDict class
    """The keys a TypedDict class declares, less the ``_headers`` the boundary moves into headers."""
    return set(payload.__required_keys__ | payload.__optional_keys__) - {"_headers"}


class Env:
    def __init__(self, client: httpx.AsyncClient, uids: dict[str, str]) -> None:
        self.client = client
        self.uids = uids


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(skuel_app: Any) -> AsyncIterator[Env]:  # boundary: fasthtml-app
    async with signed_in_client(skuel_app, USER, MARK) as client:
        uids = {
            "parent": await create(client, "tasks", f"{MARK} parent"),
            "child": await create(client, "tasks", f"{MARK} child"),
            "sibling": await create(client, "tasks", f"{MARK} sibling"),
            "loose": await create(client, "tasks", f"{MARK} loose"),
            "goal": await create(client, "goals", f"{MARK} goal"),
            "habit_parent": await create(client, "habits", f"{MARK} habit parent"),
            "habit_child": await create(client, "habits", f"{MARK} habit child"),
        }
        for segment, parent, child in (
            ("tasks", "parent", "child"),
            ("tasks", "parent", "sibling"),
            ("habits", "habit_parent", "habit_child"),
        ):
            response = await client.post(
                f"/api/{segment}/add-child",
                json={"parent_uid": uids[parent], "child_uid": uids[child]},
            )
            assert response.status_code == 200, response.text
            assert response.json() == {"added": True}
            assert set(response.json()) == _keys(ChildAddedPayload)
        yield Env(client, uids)


@pytest.mark.parametrize(
    ("segment", "parent", "child"),
    [("tasks", "parent", "child"), ("habits", "habit_parent", "habit_child")],
)
async def test_the_hierarchy_route_answers_an_entity_hierarchy(
    env: Env, segment: str, parent: str, child: str
) -> None:
    response = await env.client.get(f"/api/{segment}/hierarchy", params={"uid": env.uids[child]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == _keys(EntityHierarchy)
    assert body["current"]["uid"] == env.uids[child]
    assert [node["uid"] for node in body["ancestors"]] == [env.uids[parent]]
    assert body["depth"] == 1


async def test_remove_child_answers_whether_the_edge_went(env: Env) -> None:
    response = await env.client.post(
        "/api/tasks/remove-child",
        json={"parent_uid": env.uids["parent"], "child_uid": env.uids["loose"]},
    )

    assert response.status_code == 200, response.text
    assert set(response.json()) == _keys(ChildRemovedPayload)


async def test_siblings_are_derived_sibling_rows(env: Env) -> None:
    response = await env.client.get(f"/api/tasks/{env.uids['child']}/lateral/siblings")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == _keys(SiblingsPayload)
    assert [row["uid"] for row in body["siblings"]] == [env.uids["sibling"]]
    assert set(body["siblings"][0]) == _keys(DerivedSiblingItem)
    assert body["count"] == 1


async def test_a_lateral_write_and_its_reads_answer_their_payloads(env: Env) -> None:
    blocker, blocked = env.uids["loose"], env.uids["sibling"]

    created = await env.client.post(
        f"/api/tasks/{blocker}/lateral/blocks",
        data={"target_uid": blocked, "reason": f"{MARK} first"},
    )
    assert created.status_code == 201, created.text
    assert set(created.json()) == _keys(BlockingCreatedPayload)
    assert created.headers["HX-Trigger"] == "relationships-changed"

    blocking = await env.client.get(f"/api/tasks/{blocked}/lateral/blocking")
    assert blocking.status_code == 200, blocking.text
    assert set(blocking.json()) == _keys(BlockingPayload)
    rows = blocking.json()["blocking"]
    assert [row["target_uid"] for row in rows] == [blocker]
    assert set(rows[0]) <= _keys(LateralRelationshipItem)

    outgoing = await env.client.get(f"/api/tasks/{blocker}/lateral/blocked")
    assert outgoing.status_code == 200, outgoing.text
    assert set(outgoing.json()) == _keys(BlockedPayload)

    deleted = await env.client.delete(f"/api/tasks/{blocker}/lateral/blocks/{blocked}")
    assert deleted.status_code == 200, deleted.text
    assert set(deleted.json()) == _keys(LateralDeletedPayload)
    assert deleted.headers["HX-Trigger"] == "relationships-changed"


async def test_a_link_answers_whether_it_linked(env: Env) -> None:
    response = await env.client.post(
        "/api/tasks/link-goal",
        json={"task_uid": env.uids["loose"], "goal_uid": env.uids["goal"]},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"linked": True}
    assert set(response.json()) == _keys(LinkedPayload)


async def test_knowledge_patterns_answer_their_payload(env: Env) -> None:
    response = await env.client.get("/api/tasks/knowledge-patterns")

    assert response.status_code == 200, response.text
    assert set(response.json()) == _keys(KnowledgePatternsPayload)
