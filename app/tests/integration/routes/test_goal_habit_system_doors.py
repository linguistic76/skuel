"""The goal page's habit section over the bootstrapped app: link a habit, change its tier,
unlink it, replace the whole system.

Each door verifies the goal's owner at the route and admits the habit as the caller's own
(``HABIT_FAR_END``); the edge is ``(Habit)-[:SUPPORTS_GOAL {weight, essentiality}]->(Goal)``.
Held here against the app's own graph:

- a habit linked from the page's form shows on the goal page and the habit page, with its
  tier, and the edge holds the properties the create doors write;
- a tier change from the page lands on the edge and nothing else on either node changes;
  the tier buckets and the dashboard's habit read see the new tier;
- a principle's ``SUPPORTS_GOAL`` on the same goal is untouched by every habit door, a
  habit door handed the principle's uid included;
- another user's habit is not found and no edge is written; another user's goal is not
  found at any door;
- two tier changes at once leave one edge;
- the replace door makes the system exactly what it names: a habit linked after the
  caller read the system, and not named, is unlinked;
- a habit-based goal's figure follows a link, a second link and each unlink, down to 0
  when the last habit leaves.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from html import unescape
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.type_hints import EntityUID
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, edges_between, signed_in_client, wipe

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

    from adapters.inbound.fasthtml_types import FastHTMLApp

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzgoalhabits"
CALLER = seed_user_uid(MARK)
STRANGER = seed_user_uid(f"{MARK}-stranger")
STRANGERS_HABIT = f"habit.{MARK}-not-yours"
STRANGERS_GOAL = f"goal.{MARK}-not-yours"
HTMX = {"HX-Request": "true"}
_TRIALS = 5


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    services: Any  # boundary: the composed Services container
    driver: AsyncDriver


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(skuel_app: FastHTMLApp) -> AsyncIterator[Env]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        yield Env(client=client, services=skuel_app.state.services, driver=driver)
    await wipe(driver, STRANGER, MARK)


# ---------------------------------------------------------------------------
# Seeds and reads
# ---------------------------------------------------------------------------


async def _goal(
    env: Env,
    title: str,
    measurement: str = "percentage",
    **fields: Any,  # boundary: JSON body fields
) -> str:
    """A goal made at the JSON create door."""
    return await create(
        env.client, "goals", f"{MARK} {title}", measurement_type=measurement, **fields
    )


async def _habit(
    env: Env,
    title: str,
    **fields: Any,  # boundary: JSON body fields
) -> str:
    """A habit made at the JSON create door."""
    return await create(env.client, "habits", f"{MARK} {title}", **fields)


async def _principle_supporting(env: Env, goal: str) -> str:
    """A principle linked to ``goal`` at the principle link door."""
    principle = await create(env.client, "principles", f"{MARK} principle for {goal}")
    linked = await env.client.post(
        "/api/goals/link-principle", json={"goal_uid": goal, "principle_uid": principle}
    )
    assert linked.status_code == 200, linked.text
    return principle


async def _props(env: Env, label: str, uid: str) -> dict[str, Any]:  # boundary: raw node
    async with env.driver.session() as session:
        record = await (
            await session.run(f"MATCH (n:{label} {{uid: $uid}}) RETURN properties(n) AS p", uid=uid)
        ).single()
    assert record is not None, uid
    return dict(record["p"])


def _without_clock(node: dict[str, Any]) -> dict[str, Any]:  # boundary: raw node
    return {key: value for key, value in node.items() if key != "updated_at"}


async def _supports(
    env: Env, source: str, goal: str
) -> list[dict[str, Any]]:  # boundary: raw relationship properties
    """The properties of each ``SUPPORTS_GOAL`` edge from ``source`` to ``goal``."""
    return [
        edge.properties
        for edge in await edges_between(env.driver, source, goal)
        if edge.type == "SUPPORTS_GOAL" and edge.source == source
    ]


async def _set_streak(env: Env, habit: str, streak: int) -> None:
    async with env.driver.session() as session:
        await session.run(
            "MATCH (h:Habit {uid: $uid}) SET h.current_streak = $streak", uid=habit, streak=streak
        )


async def _link(env: Env, goal: str, habit: str, tier: str | None = None) -> httpx.Response:
    body = {"habit_uid": habit} | ({"essentiality": tier} if tier else {})
    return await env.client.post(f"/api/goals/{goal}/habits", json=body)


async def _unlink(env: Env, goal: str, habit: str) -> httpx.Response:
    return await env.client.post(f"/api/goals/{goal}/habits/unlink", json={"habit_uid": habit})


async def _retier(env: Env, goal: str, habit: str, tier: str) -> httpx.Response:
    return await env.client.post(
        f"/api/goals/{goal}/habits/essentiality",
        json={"habit_uid": habit, "new_essentiality": tier},
    )


async def _replace(env: Env, goal: str, **tiers: list[str]) -> httpx.Response:
    return await env.client.post(f"/api/goals/{goal}/habits/system", json=tiers)


def _attribute(tag: str, name: str) -> str:
    match = re.search(rf"""{name}=(?:"([^"]*)"|'([^']*)')""", tag)
    assert match is not None, (name, tag)
    return unescape(match.group(1) or match.group(2))


def _tag(html: str, marker: str) -> str:
    match = re.search(rf"<(?:form|button|select)[^>]*{marker}[^>]*>", html)
    assert match is not None, marker
    return match.group(0)


async def _content(env: Env, page_url: str, content_prefix: str) -> str:
    shell = await env.client.get(page_url)
    assert shell.status_code == 200
    content = re.search(rf'hx-get="({re.escape(content_prefix)}[^"]*)"', shell.text)
    assert content is not None, "the detail shell loads its body over HTMX"
    page = await env.client.get(unescape(content.group(1)), headers=HTMX)
    assert page.status_code == 200
    return page.text


async def _habit_section(env: Env, goal: str) -> str:
    """The goal page's habit section, loaded as the page loads it."""
    page = await _content(env, f"/goals/detail?uid={goal}", "/goals/detail/content")
    return await _section_from(env, page)


async def _section_from(env: Env, detail_html: str) -> str:
    """The habit section a rendered detail view loads."""
    loader = re.search(r'hx-get="(/goals/habits\?uid=[^"]*)"', detail_html)
    assert loader is not None, "the detail view loads its habit section"
    section = await env.client.get(unescape(loader.group(1)), headers=HTMX)
    assert section.status_code == 200, section.text
    return section.text


def _selected_tier(section: str, habit: str) -> str:
    select = re.search(
        rf"<select[^>]*data-goal-habit-tier-select=\"{re.escape(habit)}\"[^>]*>(.*?)</select>",
        section,
        re.DOTALL,
    )
    assert select is not None, f"no tier select for {habit}"
    (chosen,) = re.findall(r"<option[^>]*value=\"(\w+)\"[^>]*selected", select.group(1))
    return chosen


# ---------------------------------------------------------------------------
# Linking from the page
# ---------------------------------------------------------------------------


async def test_a_habit_linked_from_the_page_shows_on_both_pages_with_its_tier(env: Env) -> None:
    goal = await _goal(env, "page-link")
    habit = await _habit(env, "page-link habit")
    section = await _habit_section(env, goal)
    assert "No habits support this goal yet." in section

    form = _tag(section, "data-goal-link-habit")
    assert _attribute(form, "hx-target") == f"#goal-detail-{goal}"
    # The form's own encoding: FastHTML's ``Form`` declares multipart, and htmx sends it.
    assert _attribute(form, "enctype") == "multipart/form-data"
    swapped = await env.client.post(
        _attribute(form, "hx-post"),
        files={"habit_uid": (None, habit), "essentiality": (None, "critical")},
        headers=HTMX,
    )

    assert swapped.status_code == 200, swapped.text
    assert f'id="goal-detail-{goal}"' in swapped.text
    section = await _section_from(env, swapped.text)
    assert _selected_tier(section, habit) == "critical"
    habit_page = await _content(env, f"/habits/detail?uid={habit}", "/habits/detail/content")
    assert "Goals this habit supports" in habit_page
    assert f"{MARK} page-link" in habit_page

    # The edge holds what a create door writes, at the tier the page chose.
    created_goal = await _goal(env, "page-link created", supporting_habit_uids=[habit])
    assert await _supports(env, habit, created_goal) == [
        {"weight": 1.0, "essentiality": "supporting"}
    ]
    assert await _supports(env, habit, goal) == [{"weight": 1.0, "essentiality": "critical"}]


async def test_linking_a_linked_habit_keeps_one_edge_at_the_tier_given(env: Env) -> None:
    goal = await _goal(env, "relink")
    habit = await _habit(env, "relink habit")

    assert (await _link(env, goal, habit, "essential")).status_code == 200
    assert (await _link(env, goal, habit)).status_code == 200

    assert await _supports(env, habit, goal) == [{"weight": 1.0, "essentiality": "supporting"}]


# ---------------------------------------------------------------------------
# Changing a tier
# ---------------------------------------------------------------------------


async def test_a_tier_change_from_the_page_changes_the_tier_and_nothing_else(env: Env) -> None:
    goal = await _goal(env, "retier")
    habit = await _habit(env, "retier habit")
    assert (await _link(env, goal, habit)).status_code == 200
    goal_before = _without_clock(await _props(env, "Goal", goal))
    habit_before = _without_clock(await _props(env, "Habit", habit))

    select = _tag(await _habit_section(env, goal), f'data-goal-habit-tier-select="{habit}"')
    assert _attribute(select, "name") == "new_essentiality"
    swapped = await env.client.post(
        _attribute(select, "hx-post"),
        data={"new_essentiality": "essential", **json.loads(_attribute(select, "hx-vals"))},
        headers=HTMX,
    )

    assert swapped.status_code == 200, swapped.text
    assert await _supports(env, habit, goal) == [{"weight": 1.0, "essentiality": "essential"}]
    assert _without_clock(await _props(env, "Goal", goal)) == goal_before
    assert _without_clock(await _props(env, "Habit", habit)) == habit_before
    assert _selected_tier(await _section_from(env, swapped.text), habit) == "essential"

    goals = env.services.goals
    essential = await goals.relationships.get_related_uids("essential_habits", EntityUID(goal))
    catch_all = await goals.relationships.get_related_uids("supporting_habits", EntityUID(goal))
    assert (essential.value, catch_all.value) == ([habit], [habit])
    windows = await goals.backend.get_supporting_habit_windows(goal, "2026-01-01", "2026-01-31")
    assert [(row["habit"].uid, row["essentiality"]) for row in windows.value] == [
        (habit, "essential")
    ]


async def test_a_tier_change_on_a_habit_not_linked_is_not_found_and_links_nothing(
    env: Env,
) -> None:
    goal = await _goal(env, "retier-unlinked")
    habit = await _habit(env, "retier-unlinked habit")

    answer = await _retier(env, goal, habit, "essential")

    assert answer.status_code == 404
    assert await _supports(env, habit, goal) == []


async def test_two_tier_changes_at_once_leave_one_edge(env: Env) -> None:
    for trial in range(_TRIALS):
        goal = await _goal(env, f"race-retier-{trial}")
        habit = await _habit(env, f"race-retier habit {trial}")
        assert (await _link(env, goal, habit)).status_code == 200

        answers = await asyncio.gather(
            _retier(env, goal, habit, "essential"), _retier(env, goal, habit, "optional")
        )

        assert [answer.status_code for answer in answers] == [200, 200]
        (edge,) = await _supports(env, habit, goal)
        assert edge["essentiality"] in {"essential", "optional"}


# ---------------------------------------------------------------------------
# Unlinking, and the principle beside the habits
# ---------------------------------------------------------------------------


async def test_unlink_from_the_page_removes_the_habit_only(env: Env) -> None:
    goal = await _goal(env, "unlink")
    habit = await _habit(env, "unlink habit")
    assert (await _link(env, goal, habit, "optional")).status_code == 200

    button = _tag(await _habit_section(env, goal), f'data-goal-habit-unlink="{habit}"')
    swapped = await env.client.post(
        _attribute(button, "hx-post"), data=json.loads(_attribute(button, "hx-vals")), headers=HTMX
    )

    assert swapped.status_code == 200, swapped.text
    assert await _supports(env, habit, goal) == []
    assert "No habits support this goal yet." in await _section_from(env, swapped.text)
    assert (await _unlink(env, goal, habit)).status_code == 200, "a repeat changes nothing"


async def test_no_habit_door_touches_a_principle_that_supports_the_goal(env: Env) -> None:
    goal = await _goal(env, "principle-beside")
    habit = await _habit(env, "principle-beside habit")
    principle = await _principle_supporting(env, goal)
    principle_edges = await _supports(env, principle, goal)
    assert len(principle_edges) == 1

    answers = [
        await _link(env, goal, habit, "critical"),
        await _retier(env, goal, habit, "essential"),
        await _retier(env, goal, principle, "essential"),
        await _link(env, goal, principle),
        await _unlink(env, goal, principle),
        await _unlink(env, goal, habit),
        await _replace(env, goal, essential_habit_uids=[habit]),
        await _replace(env, goal),
    ]

    assert [answer.status_code for answer in answers] == [200, 200, 404, 404, 200, 200, 200, 200]
    assert await _supports(env, principle, goal) == principle_edges
    assert await _supports(env, habit, goal) == []
    section = await _habit_section(env, goal)
    assert principle not in section, "the habit section lists habits only"


# ---------------------------------------------------------------------------
# Another user's habit, another user's goal
# ---------------------------------------------------------------------------


async def _seed_stranger(env: Env) -> None:
    async with env.driver.session() as session:
        await session.run(
            """
            MERGE (u:User {uid: $stranger}) SET u.title = $stranger
            MERGE (h:Entity:Habit {uid: $habit})
            SET h.entity_type = 'habit', h.user_uid = $stranger, h.title = 'Not yours',
                h.status = 'active', h.current_streak = 50
            MERGE (g:Entity:Goal {uid: $goal})
            SET g.entity_type = 'goal', g.user_uid = $stranger, g.title = 'Not yours',
                g.status = 'active', g.measurement_type = 'percentage'
            MERGE (u)-[:OWNS]->(h)
            MERGE (u)-[:OWNS]->(g)
            MERGE (h)-[:SUPPORTS_GOAL {weight: 1.0, essentiality: 'supporting'}]->(g)
            """,
            stranger=STRANGER,
            habit=STRANGERS_HABIT,
            goal=STRANGERS_GOAL,
        )


async def test_another_users_habit_is_not_found_and_nothing_is_written(env: Env) -> None:
    await _seed_stranger(env)
    goal = await _goal(env, "foreign-habit")
    mine = await _habit(env, "foreign-habit mine")
    assert (await _link(env, goal, mine, "critical")).status_code == 200

    answers = [
        await _link(env, goal, STRANGERS_HABIT),
        await _replace(env, goal, essential_habit_uids=[STRANGERS_HABIT]),
        await _replace(env, goal, supporting_habit_uids=[STRANGERS_HABIT, mine]),
    ]

    assert [answer.status_code for answer in answers] == [404, 404, 404]
    assert await _supports(env, STRANGERS_HABIT, goal) == []
    assert await _supports(env, mine, goal) == [{"weight": 1.0, "essentiality": "critical"}]


async def test_another_users_goal_is_not_found_at_any_door_and_keeps_its_habit(
    env: Env,
) -> None:
    await _seed_stranger(env)
    mine = await _habit(env, "foreign-goal mine")
    before = await _supports(env, STRANGERS_HABIT, STRANGERS_GOAL)

    answers = [
        await _link(env, STRANGERS_GOAL, mine),
        await _retier(env, STRANGERS_GOAL, STRANGERS_HABIT, "optional"),
        await _unlink(env, STRANGERS_GOAL, STRANGERS_HABIT),
        await _replace(env, STRANGERS_GOAL),
        await env.client.get(f"/goals/habits?uid={STRANGERS_GOAL}", headers=HTMX),
    ]

    assert [answer.status_code for answer in answers] == [404, 404, 404, 404, 404]
    assert await _supports(env, STRANGERS_HABIT, STRANGERS_GOAL) == before
    assert await _supports(env, mine, STRANGERS_GOAL) == []


# ---------------------------------------------------------------------------
# Replacing the whole system
# ---------------------------------------------------------------------------


async def test_a_replace_makes_the_system_exactly_what_it_names(env: Env) -> None:
    """The rule: a replace is the whole system. A habit linked by another door after the
    caller read the system, and not named in the replace, is unlinked."""
    goal = await _goal(env, "replace")
    first = await _habit(env, "replace first")
    second = await _habit(env, "replace second")
    later = await _habit(env, "replace later")
    principle = await _principle_supporting(env, goal)
    assert (await _link(env, goal, first, "critical")).status_code == 200
    read_by_the_caller = await _habit_section(env, goal)
    assert later not in read_by_the_caller
    assert (await _link(env, goal, later, "essential")).status_code == 200

    replaced = await _replace(env, goal, essential_habit_uids=[first], optional_habit_uids=[second])

    assert replaced.status_code == 200, replaced.text
    assert await _supports(env, first, goal) == [{"weight": 1.0, "essentiality": "essential"}]
    assert await _supports(env, second, goal) == [{"weight": 1.0, "essentiality": "optional"}]
    assert await _supports(env, later, goal) == []
    assert len(await _supports(env, principle, goal)) == 1
    links = await env.services.goals.get_habit_system(goal)
    assert [(link.habit_uid, link.essentiality.value) for link in links.value] == [
        (first, "essential"),
        (second, "optional"),
    ]


async def test_a_habit_in_two_tiers_is_refused_and_the_system_stays(env: Env) -> None:
    goal = await _goal(env, "replace-twice")
    habit = await _habit(env, "replace-twice habit")
    assert (await _link(env, goal, habit)).status_code == 200

    answer = await _replace(env, goal, essential_habit_uids=[habit], optional_habit_uids=[habit])

    assert answer.status_code == 400
    assert await _supports(env, habit, goal) == [{"weight": 1.0, "essentiality": "supporting"}]


# ---------------------------------------------------------------------------
# A habit-based goal's figure follows its habits
# ---------------------------------------------------------------------------


async def test_a_habit_based_goals_figure_follows_each_link_and_unlink(env: Env) -> None:
    """The figure is the habits' average streak against the target (10 days): 4 → 40%,
    4 and 8 → 60%, 8 alone → 80%, none → 0%."""
    goal = await _goal(env, "figure", "habit_based", target_value=10)
    short = await _habit(env, "figure short")
    long = await _habit(env, "figure long")
    await _set_streak(env, short, 4)
    await _set_streak(env, long, 8)

    async def figure() -> tuple[float, float]:
        node = await _props(env, "Goal", goal)
        return (node["progress_percentage"], node["current_value"])

    assert (await _link(env, goal, short)).status_code == 200
    assert await figure() == (40.0, 4.0)
    assert (await _link(env, goal, long, "essential")).status_code == 200
    assert await figure() == (60.0, 6.0)
    assert (await _unlink(env, goal, short)).status_code == 200
    assert await figure() == (80.0, 8.0)
    assert (await _retier(env, goal, long, "optional")).status_code == 200
    assert await figure() == (80.0, 8.0), "the tier does not enter the average"
    assert (await _replace(env, goal)).status_code == 200
    assert await figure() == (0.0, 0.0)


async def test_a_link_leaves_another_measurement_types_figure_alone(env: Env) -> None:
    goal = await _goal(env, "figure-percentage")
    habit = await _habit(env, "figure-percentage habit")
    await _set_streak(env, habit, 9)
    recorded = await env.client.post(f"/api/goals/{goal}/progress", json={"progress": 30})
    assert recorded.status_code == 200, recorded.text

    assert (await _link(env, goal, habit)).status_code == 200

    assert (await _props(env, "Goal", goal))["progress_percentage"] == 30.0
