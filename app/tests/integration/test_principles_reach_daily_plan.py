"""
Principles reach the daily plan — the lookups a built UserContext carries, and their two readers.
==================================================================================================

The rich build reads what each of the user's active principles is linked to — the goals it
supports (``SUPPORTS_GOAL``), the tasks aligned with it (``ALIGNED_WITH_PRINCIPLE``) and the
habits that carry it (``EMBODIES_PRINCIPLE`` and ``INSPIRES_HABIT``) — into three lookups:
``principles_by_goal`` / ``principles_by_task`` / ``principles_by_habit``. Two readers use them:

- the daily plan's principle slot (method 1 → ``get_aligned_principles_for_user``): the
  principles linked to today's tasks or to an active goal, weighted by strength;
- the relevance score of a ``ContextualTask`` / ``ContextualHabit`` (``_compute_relevance``):
  lifted by the most deeply held principle the entity is linked to.

The learner (the T_ tasks below due today, no goals, no prerequisites — otherwise identical):

    P_CORE      core       <- T_CORE (task create door), H_CORE (habit link door)
    P_EXPL      exploring  <- T_EXPL (task create door), -> H_EXPL (principle link door, INSPIRES_HABIT)
    P_GOAL      moderate   -> G (goal link door); 11 more tasks aligned, due next week
    P_DONE      core       <- T_DONE, due today and completed: a finished task guides nothing today
    P_ARCHIVED  core       <- T_ARCH, H_ARCH, -> G, then archived: guides nothing
    P_FOREIGN   another user's principle, linked raw to T_FOREIGN, H_FOREIGN and G
    T_NONE, H_NONE         linked to nothing

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.integration._activity_link_rig import create, signed_in_client, write_edge

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

    from core.services.user import UserContext

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzprdp"
USER = f"user_{MARK}"
OTHER = f"user_{MARK}_other"  # owns the foreign principle; never signs in
FOREIGN_PRINCIPLE = f"principle_{MARK}_foreign"
MANY = 11  # one past the principles row's display slice


class Env:
    def __init__(
        self,
        client: httpx.AsyncClient,
        services: Any,  # boundary: the composed Services container
        uids: dict[str, str],
    ) -> None:
        self.client = client
        self.services = services
        self.uids = uids


async def _seed_foreign_principle(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (o:User {uid: $other})
            MERGE (p:Entity:Principle {uid: $principle})
            SET p.title = $principle, p.entity_type = 'principle', p.status = 'active',
                p.user_uid = $other, p.strength = 'core'
            MERGE (o)-[:OWNS]->(p)
            """,
            other=OTHER,
            principle=FOREIGN_PRINCIPLE,
        )


async def _post_ok(client: httpx.AsyncClient, url: str, body: dict[str, str]) -> None:
    response = await client.post(url, json=body)
    assert response.status_code == 200, (url, response.text)


async def _set_status(client: httpx.AsyncClient, segment: str, uid: str, status: str) -> None:
    response = await client.post(f"/api/{segment}/{uid}/status", data={"status": status})
    assert response.status_code == 200, response.text
    assert "Missing status" not in response.text and "Invalid status" not in response.text


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[Env]:
    async with signed_in_client(skuel_app, USER, MARK) as client:
        today = today_in(current_zone())
        later = (today + timedelta(days=7)).isoformat()
        principles = {
            "p_core": "core",
            "p_expl": "exploring",
            "p_goal": "moderate",
            "p_archived": "core",
            "p_done": "core",
        }
        uids = {
            name: await create(client, "principles", f"{MARK} {name}", strength=strength)
            for name, strength in principles.items()
        }
        uids["g"] = await create(client, "goals", f"{MARK} goal", goal_type="outcome")

        async def task(name: str, *principle_uids: str, due: str = today.isoformat()) -> str:
            return await create(
                client,
                "tasks",
                f"{MARK} {name}",
                aligned_principle_uids=list(principle_uids),
                due_date=due,
            )

        uids["t_none"] = await task("t_none")
        uids["t_core"] = await task("t_core", uids["p_core"])
        uids["t_expl"] = await task("t_expl", uids["p_expl"])
        uids["t_arch"] = await task("t_arch", uids["p_archived"])
        uids["t_foreign"] = await task("t_foreign")
        uids["t_done"] = await task("t_done", uids["p_done"])
        for i in range(MANY):
            uids[f"t_many_{i}"] = await task(f"t_many_{i}", uids["p_goal"], due=later)

        for name in ("h_none", "h_core", "h_expl", "h_arch", "h_foreign"):
            uids[name] = await create(client, "habits", f"{MARK} {name}")
        for habit, principle in (("h_core", "p_core"), ("h_arch", "p_archived")):
            await _post_ok(
                client,
                "/api/habits/link-principle",
                {"habit_uid": uids[habit], "principle_uid": uids[principle]},
            )
        await _post_ok(
            client,
            f"/api/principles/link?uid={uids['p_expl']}",
            {"link_type": "habit", "target_uid": uids["h_expl"]},
        )
        for principle in ("p_goal", "p_archived"):
            await _post_ok(
                client,
                "/api/goals/link-principle",
                {"goal_uid": uids["g"], "principle_uid": uids[principle]},
            )
        await _set_status(client, "principles", uids["p_archived"], "archived")
        await _set_status(client, "tasks", uids["t_done"], "completed")

        services = skuel_app.state.services
        driver = services.neo4j_driver
        await _seed_foreign_principle(driver)
        await write_edge(driver, uids["t_foreign"], "ALIGNED_WITH_PRINCIPLE", FOREIGN_PRINCIPLE)
        await write_edge(driver, uids["h_foreign"], "EMBODIES_PRINCIPLE", FOREIGN_PRINCIPLE)
        await write_edge(driver, FOREIGN_PRINCIPLE, "SUPPORTS_GOAL", uids["g"])
        yield Env(client, services, uids)
        async with driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.uid IN [$other, $principle] DETACH DELETE n",
                other=OTHER,
                principle=FOREIGN_PRINCIPLE,
            )


async def _rich(env: Env) -> UserContext:
    # The builder itself, past the context cache: the module seeds after the app may build.
    built = await env.services.context.context_builder.build_rich(USER)
    assert built.is_ok, built
    return built.value


async def test_the_rich_build_carries_every_link_of_every_active_principle(env: Env) -> None:
    context = await _rich(env)
    u = env.uids

    assert context.principles_by_goal == {u["g"]: [u["p_goal"]]}
    assert context.principles_by_task == {
        u["t_core"]: [u["p_core"]],
        u["t_expl"]: [u["p_expl"]],
        u["t_done"]: [u["p_done"]],  # every status of task
        # every aligned task, past the principles row's display slice of ten
        **{u[f"t_many_{i}"]: [u["p_goal"]] for i in range(MANY)},
    }
    assert context.principles_by_habit == {
        u["h_core"]: [u["p_core"]],  # the habit embodies it
        u["h_expl"]: [u["p_expl"]],  # the principle inspires it
    }
    # an archived principle is no core principle — the standard build's line
    assert u["p_archived"] not in context.core_principle_uids
    assert set(context.core_principle_uids) == {u["p_core"], u["p_expl"], u["p_goal"], u["p_done"]}


async def test_the_standard_build_carries_no_principle_lookups(env: Env) -> None:
    built = await env.services.context.context_builder.build(USER)
    assert built.is_ok, built

    assert built.value.principles_by_goal == {}
    assert built.value.principles_by_task == {}
    assert built.value.principles_by_habit == {}


async def test_the_daily_plan_names_the_principles_linked_to_today(env: Env) -> None:
    intelligence = env.services.context_intelligence.create(await _rich(env))
    intelligence.zpd_service = None
    u = env.uids

    plan = await intelligence.get_ready_to_work_on_today()

    assert plan.is_ok, plan
    # today's task, weighted core (0.3 x 1.5) > the active goal, moderate (0.2 x 1.1)
    # > today's task, exploring (0.3 x 0.7); archived and foreign principles never, nor
    # a principle whose only task due today is completed
    assert plan.value.principles == (u["p_core"], u["p_goal"], u["p_expl"])


async def test_the_principle_slot_names_its_connected_activities(env: Env) -> None:
    u = env.uids

    result = await env.services.principles.get_aligned_principles_for_user(await _rich(env))

    assert result.is_ok, result
    by_uid = {p.uid: p for p in result.value}
    assert set(by_uid) == {u["p_core"], u["p_goal"], u["p_expl"]}
    assert by_uid[u["p_core"]].connected_task_uids == (u["t_core"],)
    assert by_uid[u["p_goal"]].connected_goal_uids == (u["g"],)
    assert by_uid[u["p_goal"]].connected_task_uids == ()  # its tasks are not due today
    assert by_uid[u["p_core"]].relevance_score == pytest.approx(0.45)
    assert by_uid[u["p_goal"]].relevance_score == pytest.approx(0.22)
    assert by_uid[u["p_expl"]].relevance_score == pytest.approx(0.21)


async def test_practice_opportunities_are_todays_open_aligned_tasks(env: Env) -> None:
    u = env.uids

    result = await env.services.principles.get_principle_practice_opportunities_for_user(
        await _rich(env), limit=50
    )

    assert result.is_ok, result
    assert {(o.principle_uid, o.activity_uid) for o in result.value} == {
        (u["p_core"], u["t_core"]),
        (u["p_expl"], u["t_expl"]),
    }  # not the completed T_DONE, nor P_GOAL's tasks due next week


async def test_a_task_ranks_by_how_deeply_its_principle_is_held(env: Env) -> None:
    u = env.uids

    result = await env.services.tasks.get_actionable_tasks_for_user(await _rich(env), limit=50)

    assert result.is_ok, result
    relevance = {t.uid: t.relevance_score for t in result.value}
    # neutral 0.5, lifted toward 1.0 by the principle's importance (core 1.0, exploring 0.2)
    assert relevance[u["t_core"]] == pytest.approx(1.0)
    assert relevance[u["t_expl"]] == pytest.approx(0.6)
    for unmoved in ("t_none", "t_arch", "t_foreign"):
        assert relevance[u[unmoved]] == pytest.approx(0.5), unmoved
    ranked = [t.uid for t in result.value if t.uid in {u["t_core"], u["t_expl"], u["t_none"]}]
    assert ranked == [u["t_core"], u["t_expl"], u["t_none"]]


async def test_a_habit_ranks_by_how_deeply_its_principle_is_held(env: Env) -> None:
    u = env.uids

    result = await env.services.habits.get_habit_priorities_for_user(await _rich(env), limit=50)

    assert result.is_ok, result
    relevance = {h.uid: h.relevance_score for h in result.value}
    # (lifted base) x 0.6 + (no streak) x 0.4
    assert relevance[u["h_core"]] == pytest.approx(0.6)
    assert relevance[u["h_expl"]] == pytest.approx(0.36)
    for unmoved in ("h_none", "h_arch", "h_foreign"):
        assert relevance[u[unmoved]] == pytest.approx(0.3), unmoved
    ranked = [h.uid for h in result.value if h.uid in {u["h_core"], u["h_expl"], u["h_none"]}]
    assert ranked == [u["h_core"], u["h_expl"], u["h_none"]]
