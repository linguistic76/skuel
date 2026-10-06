"""A goal's supporters are read by kind, and a link is removed by kind.

``SUPPORTS_GOAL`` points into a goal from three kinds of node: a habit, a principle
and a PathStep. Every reader of the goal's supporters names the kind it reads.

Three supporters of one goal (a habit, a principle, a published PathStep), each read
through every path that lists a goal's supporters:

- the keyed reads (``supporting_habits``, ``supporting_principles``, the three habit
  tier keys), one goal at a time and batched;
- the goal's page;
- the path-aware cross-domain context the analytics use;
- ``GoalRelationships.fetch``;
- the goal-achieved context (``GoalsBackend.get_achievement_context``);
- the habit-based progress tally;
- ``GET /api/principles/goal``.

The habit is a supporting habit and nothing else is; the principle is a supporting
principle and nothing else is; the PathStep is listed by none of them.

The transitive case: a habit that embodies a principle that supports a goal does not
itself support the goal, and a principle that inspires a habit that supports a goal
does not itself support that goal.

Unlinking: ``GoalsService.unlink_goal_from_principle`` removes a principle's link and
``unlink_goal_from_habit`` a habit's; neither removes the other kind's, whichever uid
it is handed. A principle file that stops declaring ``connections.supports_goal``
loses the edge on its next sync.

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.relationship_names import RelationshipName
from core.services.goals.goal_relationships import GoalRelationships
from tests.integration._activity_link_rig import (
    create,
    edges_between,
    seed_published_path_step,
    signed_in_client,
    sync_vault,
    under_heading,
    write_edge,
    write_vault_file,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    import httpx
    from neo4j import AsyncDriver

    from core.models.goal.goal import Goal
    from core.ports.query_types import LinkedHabitTally

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzpglink"
CALLER = f"user_{MARK}"

SUPPORTS_GOAL = RelationshipName.SUPPORTS_GOAL.value
EMBODIES_PRINCIPLE = RelationshipName.EMBODIES_PRINCIPLE.value
INSPIRES_HABIT = RelationshipName.INSPIRES_HABIT.value

HABITS_HEADING = "Habits that support this goal"
PRINCIPLES_HEADING = "Principles that support this goal"
TIER_KEYS = ("essential_habits", "critical_habits", "optional_habits")


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    services: Any  # boundary: the composed Services container
    driver: AsyncDriver


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[Env]:
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        yield Env(
            client=client,
            services=skuel_app.state.services,
            driver=skuel_app.state.services.neo4j_driver,
        )


async def _related(
    service: Any,  # boundary: a composed domain facade (goals, principles)
    key: str,
    uid: str,
) -> list[str]:
    read = await service.relationships.get_related_uids(key, uid)
    assert read.is_ok, read
    return list(read.value)


# ---------------------------------------------------------------------------
# One goal, three kinds of supporter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Supported:
    """One goal and its three supporters, each joined by an untiered SUPPORTS_GOAL."""

    goal: str
    habit: str
    principle: str
    step: str

    habit_title = f"{MARK} supporting habit"
    principle_title = f"{MARK} supporting principle"
    step_title = f"{MARK} supporting path step"


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def supported(env: Env) -> Supported:
    found = Supported(
        goal=await create(env.client, "goals", f"{MARK} supported goal"),
        habit=await create(env.client, "habits", Supported.habit_title),
        principle=await create(env.client, "principles", Supported.principle_title),
        step=f"ps.{MARK}.supporter",
    )
    await seed_published_path_step(env.driver, found.step, Supported.step_title)
    for supporter in (found.habit, found.principle, found.step):
        await write_edge(env.driver, supporter, SUPPORTS_GOAL, found.goal)
    return found


async def test_the_seed_holds_three_supporters_of_three_kinds(
    env: Env, supported: Supported
) -> None:
    """The premise every test below reads against: all three edges are stored."""
    async with env.driver.session() as session:
        result = await session.run(
            """
            MATCH (s)-[:SUPPORTS_GOAL]->(:Goal {uid: $goal})
            RETURN s.uid AS uid, [l IN labels(s) WHERE l <> 'Entity'] AS kinds, s.entity_type AS t
            """,
            goal=supported.goal,
        )
        stored = {row["uid"]: (row["kinds"], row["t"]) async for row in result}

    assert stored == {
        supported.habit: (["Habit"], "habit"),
        supported.principle: (["Principle"], "principle"),
        supported.step: (["PathStep"], "path_step"),
    }


async def test_supporting_habits_reads_the_habit_only(env: Env, supported: Supported) -> None:
    assert await _related(env.services.goals, "supporting_habits", supported.goal) == [
        supported.habit
    ]


async def test_supporting_principles_reads_the_principle_only(
    env: Env, supported: Supported
) -> None:
    assert await _related(env.services.goals, "supporting_principles", supported.goal) == [
        supported.principle
    ]


@pytest.mark.parametrize("tier_key", TIER_KEYS)
async def test_a_tier_key_reads_nothing_from_untiered_edges(
    env: Env, supported: Supported, tier_key: str
) -> None:
    assert await _related(env.services.goals, tier_key, supported.goal) == []


async def test_an_essential_principle_is_not_an_essential_habit(
    env: Env, supported: Supported
) -> None:
    """With both edges marked essential, the habit tier key returns the habit alone."""
    essential = {"essentiality": "essential"}
    await write_edge(env.driver, supported.habit, SUPPORTS_GOAL, supported.goal, essential)
    await write_edge(env.driver, supported.principle, SUPPORTS_GOAL, supported.goal, essential)
    try:
        read = await _related(env.services.goals, "essential_habits", supported.goal)
        batched = await env.services.goals.relationships.batch_get_related_uids(
            "essential_habits", [supported.goal]
        )
    finally:
        async with env.driver.session() as session:
            await session.run(
                "MATCH ()-[r:SUPPORTS_GOAL]->(:Goal {uid: $goal}) REMOVE r.essentiality",
                goal=supported.goal,
            )

    assert read == [supported.habit]
    assert batched.is_ok, batched
    assert batched.value == {supported.goal: [supported.habit]}


@pytest.mark.parametrize(
    ("key", "kind"),
    [
        ("supporting_habits", "habit"),
        ("supporting_principles", "principle"),
        *((tier_key, None) for tier_key in TIER_KEYS),
    ],
)
async def test_the_batched_read_agrees_with_the_single_read(
    env: Env, supported: Supported, key: str, kind: str | None
) -> None:
    batched = await env.services.goals.relationships.batch_get_related_uids(key, [supported.goal])

    assert batched.is_ok, batched
    expected = [getattr(supported, kind)] if kind else []
    assert batched.value.get(supported.goal, []) == expected
    assert await _related(env.services.goals, key, supported.goal) == expected


async def test_the_goal_page_lists_each_supporter_under_its_own_heading(
    env: Env, supported: Supported
) -> None:
    response = await env.client.get(f"/goals/detail/content?uid={supported.goal}")
    assert response.status_code == 200, response.text[:500]
    page = response.text

    habits = under_heading(page, HABITS_HEADING)
    principles = under_heading(page, PRINCIPLES_HEADING)

    assert Supported.habit_title in habits
    assert Supported.principle_title not in habits
    assert Supported.principle_title in principles
    assert Supported.habit_title not in principles
    assert Supported.step_title not in page, "a PathStep supporter is under no heading"


async def test_the_path_aware_goal_context_separates_habits_from_principles(
    env: Env, supported: Supported
) -> None:
    typed = await env.services.goals.relationships.get_cross_domain_context_typed(supported.goal)

    assert typed.is_ok, typed
    assert [habit.uid for habit in typed.value.habits] == [supported.habit]
    assert [principle.uid for principle in typed.value.principles] == [supported.principle]


async def test_the_raw_goal_context_puts_the_path_step_in_no_bucket(
    env: Env, supported: Supported
) -> None:
    raw = await env.services.goals.relationships.get_cross_domain_context(supported.goal, depth=1)

    assert raw.is_ok, raw
    buckets = {
        name: [entry["uid"] for entry in entries]
        for name, entries in raw.value.items()
        if isinstance(entries, list) and entries
    }
    assert buckets == {
        "contributing_habits": [supported.habit],
        "supporting_principles": [supported.principle],
    }


async def test_goal_relationships_fetch_separates_habits_from_principles(
    env: Env, supported: Supported
) -> None:
    fetched = await GoalRelationships.fetch(supported.goal, env.services.goals.relationships)

    assert fetched.supporting_habit_uids == [supported.habit]
    assert fetched.supporting_principle_uids == [supported.principle]
    assert fetched.essential_habit_uids == []
    assert fetched.critical_habit_uids == []
    assert fetched.optional_habit_uids == []


async def test_the_achievement_context_separates_habits_from_principles(
    env: Env, supported: Supported
) -> None:
    context = await env.services.goals.backend.get_achievement_context(supported.goal, CALLER)

    assert context.is_ok, context
    assert len(context.value) == 1
    row = context.value[0]
    assert [habit["uid"] for habit in row["habits"]] == [supported.habit]
    assert [principle["uid"] for principle in row["principles"]] == [supported.principle]


async def test_the_habit_progress_tally_counts_the_one_habit(
    env: Env, supported: Supported
) -> None:
    seen: list[LinkedHabitTally] = []

    def read_only(_goal: Goal, tally: LinkedHabitTally) -> None:
        seen.append(tally)

    recomputed = await env.services.goals.backend.recompute_progress_from_linked_habits(
        supported.goal, CALLER, read_only
    )

    assert recomputed.is_ok, recomputed
    assert [tally["total_habits"] for tally in seen] == [1]


async def test_the_principles_of_a_goal_endpoint_returns_the_principle_only(
    env: Env, supported: Supported
) -> None:
    response = await env.client.get(f"/api/principles/goal?goal_uid={supported.goal}")

    assert response.status_code == 200, response.text
    assert [principle["uid"] for principle in response.json()] == [supported.principle]


# ---------------------------------------------------------------------------
# The transitive case
# ---------------------------------------------------------------------------


def _bucket(
    raw: dict[str, Any],  # boundary: raw cross-domain context
    name: str,
) -> dict[str, int]:
    """One context bucket as uid -> distance."""
    return {entry["uid"]: entry["distance"] for entry in raw[name]}


async def test_a_habit_does_not_support_the_goal_its_principle_supports(env: Env) -> None:
    habit = await create(env.client, "habits", f"{MARK} transitive habit")
    principle = await create(env.client, "principles", f"{MARK} embodied principle")
    reached_goal = await create(env.client, "goals", f"{MARK} goal the principle supports")
    own_goal = await create(env.client, "goals", f"{MARK} goal the habit supports")
    await write_edge(env.driver, habit, EMBODIES_PRINCIPLE, principle)
    await write_edge(env.driver, principle, SUPPORTS_GOAL, reached_goal)
    await write_edge(env.driver, habit, SUPPORTS_GOAL, own_goal)
    assert await edges_between(env.driver, habit, reached_goal) == []

    context = await env.services.habits.relationships.get_cross_domain_context(habit)

    assert context.is_ok, context
    assert _bucket(context.value, "supported_goals") == {own_goal: 1}
    assert _bucket(context.value, "embodied_principles") == {principle: 1}


async def test_a_principle_does_not_support_the_goal_its_habit_supports(env: Env) -> None:
    principle = await create(env.client, "principles", f"{MARK} transitive principle")
    habit = await create(env.client, "habits", f"{MARK} inspired habit")
    reached_goal = await create(env.client, "goals", f"{MARK} goal the habit alone supports")
    own_goal = await create(env.client, "goals", f"{MARK} goal the principle supports")
    await write_edge(env.driver, principle, INSPIRES_HABIT, habit)
    await write_edge(env.driver, habit, SUPPORTS_GOAL, reached_goal)
    await write_edge(env.driver, principle, SUPPORTS_GOAL, own_goal)
    assert await edges_between(env.driver, principle, reached_goal) == []

    context = await env.services.principles.relationships.get_cross_domain_context(principle)

    assert context.is_ok, context
    assert _bucket(context.value, "supported_goals") == {own_goal: 1}
    assert _bucket(context.value, "inspired_habits") == {habit: 1}


# ---------------------------------------------------------------------------
# Unlinking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    goal: str
    habit: str
    principle: str


async def _goal_with_a_habit_and_a_principle(env: Env, name: str) -> Pair:
    """A goal linked to one habit and one principle through the service's own doors."""
    pair = Pair(
        goal=await create(env.client, "goals", f"{MARK} {name} goal"),
        habit=await create(env.client, "habits", f"{MARK} {name} habit"),
        principle=await create(env.client, "principles", f"{MARK} {name} principle"),
    )
    assert (await env.services.goals.link_goal_to_habit(pair.goal, pair.habit)).is_ok
    assert (await env.services.goals.link_goal_to_principle(pair.goal, pair.principle)).is_ok
    assert await _supporters(env, pair) == ([pair.habit], [pair.principle], [pair.goal])
    return pair


async def _supporters(env: Env, pair: Pair) -> tuple[list[str], list[str], list[str]]:
    """(the goal's habits, the goal's principles, the principle's goals), by keyed read."""
    return (
        await _related(env.services.goals, "supporting_habits", pair.goal),
        await _related(env.services.goals, "supporting_principles", pair.goal),
        await _related(env.services.principles, "supported_goals", pair.principle),
    )


async def test_unlinking_the_principle_removes_it_at_both_ends_and_keeps_the_habit(
    env: Env,
) -> None:
    pair = await _goal_with_a_habit_and_a_principle(env, "unlink-principle")

    unlinked = await env.services.goals.unlink_goal_from_principle(pair.goal, pair.principle)

    assert unlinked.is_ok, unlinked
    assert await _supporters(env, pair) == ([pair.habit], [], [])
    assert await edges_between(env.driver, pair.principle, pair.goal) == []
    assert len(await edges_between(env.driver, pair.habit, pair.goal)) == 1


async def test_unlink_habit_handed_the_principle_removes_nothing(env: Env) -> None:
    pair = await _goal_with_a_habit_and_a_principle(env, "unlink-wrong-kind")

    unlinked = await env.services.goals.unlink_goal_from_habit(pair.goal, pair.principle)

    assert unlinked.is_ok, unlinked
    assert await _supporters(env, pair) == ([pair.habit], [pair.principle], [pair.goal])
    assert len(await edges_between(env.driver, pair.principle, pair.goal)) == 1


async def test_unlink_principle_handed_the_habit_removes_nothing(env: Env) -> None:
    pair = await _goal_with_a_habit_and_a_principle(env, "unlink-wrong-kind-mirror")

    unlinked = await env.services.goals.unlink_goal_from_principle(pair.goal, pair.habit)

    assert unlinked.is_ok, unlinked
    assert await _supporters(env, pair) == ([pair.habit], [pair.principle], [pair.goal])
    assert len(await edges_between(env.driver, pair.habit, pair.goal)) == 1


async def test_unlinking_the_habit_removes_it_and_keeps_the_principle(env: Env) -> None:
    pair = await _goal_with_a_habit_and_a_principle(env, "unlink-habit")

    unlinked = await env.services.goals.unlink_goal_from_habit(pair.goal, pair.habit)

    assert unlinked.is_ok, unlinked
    assert await _supporters(env, pair) == ([], [pair.principle], [pair.goal])
    assert await edges_between(env.driver, pair.habit, pair.goal) == []
    assert len(await edges_between(env.driver, pair.principle, pair.goal)) == 1


async def test_a_principle_file_that_drops_supports_goal_retracts_the_edge(
    env: Env, tmp_path: Path
) -> None:
    principle, goal = f"principle.{MARK}.retract", f"goal.{MARK}.retract"
    write_vault_file(tmp_path, "retract-goal", entity_type="goal", uid=goal, owner=CALLER)
    write_vault_file(
        tmp_path,
        "retract-principle",
        entity_type="principle",
        uid=principle,
        owner=CALLER,
        connections={"supports_goal": [goal]},
    )
    await sync_vault(env.driver, tmp_path)
    assert await _related(env.services.goals, "supporting_principles", goal) == [principle]
    assert await _related(env.services.principles, "supported_goals", principle) == [goal]

    write_vault_file(
        tmp_path, "retract-principle", entity_type="principle", uid=principle, owner=CALLER
    )
    await sync_vault(env.driver, tmp_path)

    assert await edges_between(env.driver, principle, goal) == []
    assert await _related(env.services.goals, "supporting_principles", goal) == []
    assert await _related(env.services.principles, "supported_goals", principle) == []
