"""A read anchored on something every user links to returns the caller's entities only.

A Ku, a path step, and (when another user's edge points at it) one of the caller's
own goals or habits are all anchors more than one user's activity can name. A reader
that asks "what points at this" takes the viewer and returns the viewer's entities;
the generic related-uid read, asked the same question of an anchor nobody owns,
names no user's entity at all.

Two users each link their own task, habit and principle to the same anchors, by raw
Cypher, so the readers are measured without the link doors' help. Every assertion
has its control: the caller's own entity still comes back.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import pytest_asyncio
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.fasthtml_types import Request
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

CALLER = "user_r5_caller"
OTHER = "user_r5_other"
USERS = (CALLER, OTHER)

KU = "ku.r5.shared"
STEP = "ps.r5.shared"
KNOWLEDGE_UIDS = (KU, STEP)

GOAL = "goal_r5_callers"
HABIT = "habit_r5_callers"

OWN_TASK = "task_r5_own"
FOREIGN_TASK = "task_r5_foreign"
OWN_HABIT = "habit_r5_own"
FOREIGN_HABIT = "habit_r5_foreign"
OWN_PRINCIPLE = "principle_r5_own"
FOREIGN_PRINCIPLE = "principle_r5_foreign"

OWN_MARK = "r5-own-title"
FOREIGN_MARK = "r5-foreign-private"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (n)
            WHERE n.uid IN $users OR n.user_uid IN $users OR n.uid IN $knowledge
            DETACH DELETE n
            """,
            users=list(USERS),
            knowledge=list(KNOWLEDGE_UIDS),
        )


async def _seed_activity(
    driver: AsyncDriver, label: str, uid: str, owner: str, title: str, **properties: str
) -> None:
    async with driver.session() as session:
        await session.run(
            f"""
            MATCH (u:User {{uid: $owner}})
            MERGE (e:Entity:{label} {{uid: $uid}})
            SET e.title = $title, e.description = $title + ' description',
                e.entity_type = $entity_type, e.status = 'active', e.user_uid = $owner,
                e.recurrence_pattern = 'daily', e.priority = 'medium',
                e.created_at = $now, e.updated_at = $now
            SET e += $properties
            MERGE (u)-[:OWNS]->(e)
            """,
            uid=uid,
            owner=owner,
            title=title,
            entity_type=label.lower(),
            properties=properties,
            # ISO text, as the mapper stores every instant.
            now=datetime.now(UTC).isoformat(),
        )


async def _link(driver: AsyncDriver, source: str, edge: RelationshipName, target: str) -> None:
    async with driver.session() as session:
        await session.run(
            f"MATCH (a {{uid: $a}}), (b {{uid: $b}}) MERGE (a)-[:{edge.value} {{confidence: 0.9}}]->(b)",
            a=source,
            b=target,
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def graph(skuel_app: Any) -> AsyncIterator[AsyncDriver]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(driver)
    async with driver.session() as session:
        for uid in USERS:
            await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=uid)
        for label, entity_type, uid in (("Ku", "ku", KU), ("PathStep", "path_step", STEP)):
            await session.run(
                f"""
                MERGE (k:Entity:{label} {{uid: $uid}})
                SET k.title = 'r5 shared ' + $entity_type, k.entity_type = $entity_type,
                    k.created_at = datetime(), k.updated_at = datetime()
                """,
                uid=uid,
                entity_type=entity_type,
            )
    await _seed_activity(driver, "Goal", GOAL, CALLER, "r5 caller goal")
    await _seed_activity(driver, "Habit", HABIT, CALLER, "r5 caller habit")
    for owner, mark, task, habit, principle in (
        (CALLER, OWN_MARK, OWN_TASK, OWN_HABIT, OWN_PRINCIPLE),
        (OTHER, FOREIGN_MARK, FOREIGN_TASK, FOREIGN_HABIT, FOREIGN_PRINCIPLE),
    ):
        # The task names the shared step and the caller's goal the way the doors
        # store both: a node column, and for the goal the edge beside it.
        await _seed_activity(
            driver,
            "Task",
            task,
            owner,
            f"{mark} task",
            source_path_step_uid=STEP,
            fulfills_goal_uid=GOAL,
        )
        await _seed_activity(driver, "Habit", habit, owner, f"{mark} habit")
        await _seed_activity(driver, "Principle", principle, owner, f"{mark} principle")
        await _link(driver, task, RelationshipName.APPLIES_KNOWLEDGE, KU)
        await _link(driver, task, RelationshipName.FULFILLS_GOAL, GOAL)
        await _link(driver, task, RelationshipName.REINFORCES_HABIT, HABIT)
        await _link(driver, habit, RelationshipName.REINFORCES_KNOWLEDGE, KU)
        # A habit and a principle support the same goal over the one edge type.
        await _link(driver, habit, RelationshipName.SUPPORTS_GOAL, GOAL)
        await _link(driver, principle, RelationshipName.SUPPORTS_GOAL, GOAL)
    yield driver
    await _wipe(driver)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def http(skuel_app: Any, graph: AsyncDriver) -> AsyncIterator[httpx.AsyncClient]:
    """The whole route tree, wired by the bootstrap's own entry point, signed in as CALLER."""
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="r5-test-key")
    await _wire_all_routes(
        app, rt, container.services, container.config, container.prometheus_metrics
    )

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    token = mint_token()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
        timeout=60,
    ) as client:
        assert (await client.get(f"/sign-in/{CALLER}")).status_code == 200
        yield client


@pytest.mark.parametrize(
    "url",
    [
        f"/api/tasks/goal?goal_uid={GOAL}",
        f"/api/tasks/habit?habit_uid={HABIT}",
        f"/api/principles/goal?goal_uid={GOAL}",
        f"/explore/ps/{STEP}/tasks",
    ],
)
async def test_a_reverse_read_route_returns_the_callers_entity_and_not_the_other_users(
    http: httpx.AsyncClient, url: str
) -> None:
    response = await http.get(url)

    assert response.status_code == 200, response.text
    assert OWN_MARK in response.text
    assert FOREIGN_MARK not in response.text
    assert "_r5_foreign" not in response.text


async def test_the_goals_principle_read_returns_its_principle_and_not_its_habit(
    http: httpx.AsyncClient,
) -> None:
    """The caller's habit supports the goal over the same edge type the principle does."""
    response = await http.get(f"/api/principles/goal?goal_uid={GOAL}")

    assert response.status_code == 200, response.text
    assert OWN_PRINCIPLE in response.text
    assert OWN_HABIT not in response.text


async def test_the_task_readers_return_the_viewers_tasks(
    skuel_app: Any, graph: AsyncDriver
) -> None:
    tasks = skuel_app.state.services.tasks

    for_step = await tasks.get_tasks_for_path_step(STEP, CALLER)
    for_goal = await tasks.get_tasks_for_goal(GOAL, CALLER)
    for_habit = await tasks.get_tasks_for_habit(HABIT, CALLER)
    others = await tasks.get_tasks_for_path_step(STEP, OTHER)

    for result in (for_step, for_goal, for_habit):
        assert result.is_ok, result
        assert [task.uid for task in result.value] == [OWN_TASK]
    assert [task.uid for task in others.value] == [FOREIGN_TASK]


async def test_a_generic_read_from_a_shared_anchor_names_no_users_entity(
    skuel_app: Any, graph: AsyncDriver
) -> None:
    """Asked of a Ku, the Activity backend's related-uid reads return nobody's task;
    asked of the caller's task, they still return the Ku."""
    backend = skuel_app.state.services.tasks.search.backend

    uids = await backend.get_related_uids(
        KU, RelationshipName.APPLIES_KNOWLEDGE, direction="incoming"
    )
    entities = await backend.get_related_entities(
        KU, RelationshipName.APPLIES_KNOWLEDGE, direction="incoming"
    )
    control = await backend.get_related_uids(
        OWN_TASK, RelationshipName.APPLIES_KNOWLEDGE, direction="outgoing"
    )

    assert uids.is_ok and uids.value == []
    assert entities.is_ok and entities.value == []
    assert control.is_ok and control.value == [KU]


async def test_the_semantic_filter_returns_the_viewers_entities(
    skuel_app: Any, graph: AsyncDriver
) -> None:
    backend = skuel_app.state.services.habits.core.backend
    pattern = f"(n:Habit)-[r:{RelationshipName.REINFORCES_KNOWLEDGE.value}]->(target)"

    callers = await backend.find_uids_by_semantic_filter(
        pattern=pattern, target_uid=KU, min_confidence=0.5, user_uid=CALLER
    )
    others = await backend.find_uids_by_semantic_filter(
        pattern=pattern, target_uid=KU, min_confidence=0.5, user_uid=OTHER
    )

    assert callers.is_ok and callers.value == [OWN_HABIT]
    assert others.is_ok and others.value == [FOREIGN_HABIT]
