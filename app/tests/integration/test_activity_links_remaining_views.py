"""The remaining Activity link views — each read where its kind is named, over the composed app.

ADR-090 §2. A view is one registry definition: an edge type, a direction and the KIND of
entity at the far end. These tests hold the views the Activity links arc's PR 5 settled:

- the goal reads the choices that AFFECT it (``affecting_choices``, "Choices that affect
  this goal") and the events that CELEBRATE it (``celebrating_events``, "Events that
  celebrate this goal") — beside, not instead of, the choices that inspired it and the
  events that contribute; a celebration is not counted in the goal's stored tally;
- the goal's context walk at depth 2 keeps each new view honest: a second goal the same
  choice affects, and a life path a choice or event serves, are not the goal's; a choice
  affecting a SUBGOAL is the goal's at distance 2;
- a view names its kind: the principle's embodying habits are habits (a learning path
  embodying the principle is not one), the event's scheduling choices are choices (a
  PathStep scheduling the event is not one), a habit's reinforcers are tasks and events
  (no habit-reinforces-habit view), and an event's principles are the ones it
  demonstrates — never habits;
- ``PRACTICED_AT_EVENT`` is read by no view: an edge left of that type is on no page and
  in no context;
- the vault door writes a task's ``connections.reinforces_habit`` only to a habit.

Every edge a test reads is written straight into the graph (``write_edge``), so the read
under test is the one thing that decides where it shows. Each control differs from its
case in one dimension.

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.events import GoalContributionsChanged
from core.models.enums.entity_enums import EntityStatus
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from tests.integration._activity_link_rig import (
    RETIRED_PRACTICED,
    create,
    edges_between,
    goal_tally,
    seed_published_learning_path,
    seed_published_path_step,
    signed_in_client,
    store_goal_tally,
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

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzremview"
CALLER = f"user_{MARK}"

AFFECTS_GOAL = RelationshipName.AFFECTS_GOAL.value
CELEBRATES_GOAL = RelationshipName.CELEBRATES_GOAL.value
CONTRIBUTES_TO_GOAL = RelationshipName.CONTRIBUTES_TO_GOAL.value
INSPIRED_BY_CHOICE = RelationshipName.INSPIRED_BY_CHOICE.value
SUBGOAL_OF = RelationshipName.SUBGOAL_OF.value
SERVES_LIFE_PATH = RelationshipName.SERVES_LIFE_PATH.value
EMBODIES_PRINCIPLE = RelationshipName.EMBODIES_PRINCIPLE.value
SCHEDULES_EVENT = RelationshipName.SCHEDULES_EVENT.value
REINFORCES_HABIT = RelationshipName.REINFORCES_HABIT.value
DEMONSTRATES_PRINCIPLE = RelationshipName.DEMONSTRATES_PRINCIPLE.value
[PRACTICED_AT_EVENT] = RETIRED_PRACTICED


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


# ---------------------------------------------------------------------------
# Seeds and reads
# ---------------------------------------------------------------------------


def _title(name: str) -> str:
    return f"{MARK} {name}"


async def _goal(env: Env, name: str) -> str:
    """A TASK_BASED goal — the one measurement a contribution tally is written for."""
    return await create(env.client, "goals", _title(name), measurement_type="task_based")


async def _choice(env: Env, name: str) -> str:
    return await create(env.client, "choices", _title(name))


async def _habit(env: Env, name: str) -> str:
    return await create(env.client, "habits", _title(name))


async def _principle(env: Env, name: str) -> str:
    return await create(env.client, "principles", _title(name))


async def _task(env: Env, name: str) -> str:
    return await create(env.client, "tasks", _title(name))


async def _event(env: Env, name: str) -> str:
    return await create(
        env.client,
        "events",
        _title(name),
        event_date=(date.today() + timedelta(days=1)).isoformat(),
        start_time="09:00",
        end_time="10:00",
    )


async def _life_path(env: Env, name: str) -> str:
    """The caller's own LifePath node — the far end of a ``SERVES_LIFE_PATH`` edge."""
    uid = f"lifepath.{MARK}.{name.replace(' ', '-')}"
    async with env.driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $user})
            MERGE (p:Entity:LifePath {uid: $uid})
            SET p.title = $title, p.entity_type = 'life_path', p.status = 'active',
                p.user_uid = $user
            MERGE (u)-[:OWNS]->(p)
            """,
            uid=uid,
            title=_title(name),
            user=CALLER,
        )
    return uid


def _uids(raw: dict[str, Any], bucket: str) -> set[str]:  # boundary: raw context payload
    """The uids one raw context bucket holds (a list, or one entry for a single view)."""
    value = raw.get(bucket)
    entries = value if isinstance(value, list) else [value] if value else []
    return {entry["uid"] for entry in entries if isinstance(entry, dict)}


def _everywhere(raw: dict[str, Any]) -> set[str]:  # boundary: raw context payload
    """Every uid any bucket of a raw context holds."""
    return {uid for bucket in raw for uid in _uids(raw, bucket)}


def _distances(raw: dict[str, Any], bucket: str) -> dict[str, int]:  # boundary: raw context
    value = raw.get(bucket)
    entries = value if isinstance(value, list) else [value] if value else []
    return {entry["uid"]: entry["distance"] for entry in entries if isinstance(entry, dict)}


async def _context(env: Env, domain: str, uid: str) -> dict[str, Any]:  # boundary: raw context
    """The domain's cross-domain context for ``uid``, at the default depth (2)."""
    result = await getattr(env.services, domain).relationships.get_cross_domain_context(uid)
    assert result.is_ok, result
    return result.value


async def _page(env: Env, segment: str, uid: str) -> str:
    response = await env.client.get(f"/{segment}/detail/content?uid={uid}")
    assert response.status_code == 200, response.text[:500]
    return response.text


# ---------------------------------------------------------------------------
# A. The goal reads the choices that affect it and the events that celebrate it
# ---------------------------------------------------------------------------


async def test_a_choice_that_affects_the_goal_is_listed_where_the_goal_names_it(env: Env) -> None:
    goal = await _goal(env, "A affected")
    choice = await _choice(env, "A affecting")
    await write_edge(env.driver, choice, AFFECTS_GOAL, goal)

    raw = await _context(env, "goals", goal)
    page = await _page(env, "goals", goal)

    assert _uids(raw, "affecting_choices") == {choice}
    assert _title("A affecting") in under_heading(page, "Choices that affect this goal")


async def test_an_event_that_celebrates_the_goal_is_listed_where_the_goal_names_it(
    env: Env,
) -> None:
    goal = await _goal(env, "A celebrated")
    event = await _event(env, "A celebrating")
    await write_edge(env.driver, event, CELEBRATES_GOAL, goal)

    raw = await _context(env, "goals", goal)
    page = await _page(env, "goals", goal)

    assert _uids(raw, "celebrating_events") == {event}
    assert _uids(raw, "contributing_events") == set()
    assert _title("A celebrating") in under_heading(page, "Events that celebrate this goal")


async def test_an_event_that_contributes_and_celebrates_is_listed_under_both(env: Env) -> None:
    goal = await _goal(env, "A both events")
    event = await _event(env, "A both event")
    await write_edge(env.driver, event, CONTRIBUTES_TO_GOAL, goal)
    await write_edge(env.driver, event, CELEBRATES_GOAL, goal)

    raw = await _context(env, "goals", goal)
    page = await _page(env, "goals", goal)

    assert _uids(raw, "contributing_events") == {event}
    assert _uids(raw, "celebrating_events") == {event}
    for heading in ("Events that contribute to this goal", "Events that celebrate this goal"):
        assert _title("A both event") in under_heading(page, heading), heading


async def test_a_choice_that_inspires_and_affects_is_listed_under_both(env: Env) -> None:
    goal = await _goal(env, "A both choices")
    choice = await _choice(env, "A both choice")
    await write_edge(env.driver, goal, INSPIRED_BY_CHOICE, choice)
    await write_edge(env.driver, choice, AFFECTS_GOAL, goal)

    raw = await _context(env, "goals", goal)
    page = await _page(env, "goals", goal)

    assert _uids(raw, "inspired_by_choice") == {choice}
    assert _uids(raw, "affecting_choices") == {choice}
    for heading in ("Choices that inspired this goal", "Choices that affect this goal"):
        assert _title("A both choice") in under_heading(page, heading), heading


async def _completed_event(env: Env, name: str) -> str:
    event = await _event(env, name)
    result = await env.services.events.update_event(
        event, EventUpdateIntent(status=EntityStatus.COMPLETED.value)
    )
    assert result.is_ok, result
    return event


async def _recount(env: Env, goal: str, contributor: str) -> None:
    """Announce a change to the goal's contributions — the tally's one trigger."""
    await env.services.event_bus.publish_async(
        GoalContributionsChanged(
            user_uid=UserUID(CALLER), goal_uids=(goal,), contributor_uids=(contributor,)
        )
    )


async def test_a_celebrating_event_is_not_counted_in_the_goal_tally(env: Env) -> None:
    """Two goals, each with one completed event and a stale 0 / 1 tally: the event that
    celebrates leaves its goal at 0 / 0; the control, the same seed with the event
    contributing instead, is counted 1 / 1 — so the recount ran in both."""
    celebrated = await _goal(env, "A tally celebrated")
    contributed = await _goal(env, "A tally contributed")
    celebrating = await _completed_event(env, "A tally celebrating")
    contributing = await _completed_event(env, "A tally contributing")
    await write_edge(env.driver, celebrating, CELEBRATES_GOAL, celebrated)
    await write_edge(env.driver, contributing, CONTRIBUTES_TO_GOAL, contributed)
    await store_goal_tally(env.driver, celebrated, 0, 1)
    await store_goal_tally(env.driver, contributed, 0, 1)

    await _recount(env, celebrated, celebrating)
    await _recount(env, contributed, contributing)

    assert await goal_tally(env.driver, celebrated) == (0, 0)
    assert await goal_tally(env.driver, contributed) == (1, 1)


# ---------------------------------------------------------------------------
# B. The goal's walk at depth 2
# ---------------------------------------------------------------------------


async def test_a_second_goal_the_choice_affects_is_not_the_goals(env: Env) -> None:
    """goal <-AFFECTS_GOAL- choice -AFFECTS_GOAL-> other goal: the walk reaches the choice
    (it is the goal's affecting choice), and the other goal is in none of the goal's
    buckets."""
    goal = await _goal(env, "B centre")
    other = await _goal(env, "B other")
    choice = await _choice(env, "B shared choice")
    await write_edge(env.driver, choice, AFFECTS_GOAL, goal)
    await write_edge(env.driver, choice, AFFECTS_GOAL, other)

    raw = await _context(env, "goals", goal)

    assert _uids(raw, "affecting_choices") == {choice}
    assert other not in _everywhere(raw)


async def test_a_life_path_a_choice_or_event_serves_is_not_the_goals(env: Env) -> None:
    """The goal serves its own life path; the choice that affects it and the event that
    celebrates it each serve another. Only the goal's own is its life path — and the walk
    reached both intermediates."""
    goal = await _goal(env, "B life centre")
    own = await _life_path(env, "B own")
    via_choice = await _life_path(env, "B via choice")
    via_event = await _life_path(env, "B via event")
    choice = await _choice(env, "B life choice")
    event = await _event(env, "B life event")
    await write_edge(env.driver, goal, SERVES_LIFE_PATH, own)
    await write_edge(env.driver, choice, AFFECTS_GOAL, goal)
    await write_edge(env.driver, choice, SERVES_LIFE_PATH, via_choice)
    await write_edge(env.driver, event, CELEBRATES_GOAL, goal)
    await write_edge(env.driver, event, SERVES_LIFE_PATH, via_event)

    raw = await _context(env, "goals", goal)

    assert _uids(raw, "affecting_choices") == {choice}
    assert _uids(raw, "celebrating_events") == {event}
    assert _uids(raw, "life_path") == {own}
    assert not {via_choice, via_event} & _everywhere(raw)


async def test_a_choice_affecting_a_subgoal_is_the_goals_at_distance_two(env: Env) -> None:
    """subgoal -SUBGOAL_OF-> goal, choice -AFFECTS_GOAL-> subgoal: the choice's incident
    edge points into a goal, so it is the goal's affecting choice, two hops out."""
    goal = await _goal(env, "B parent")
    subgoal = await _goal(env, "B subgoal")
    choice = await _choice(env, "B subgoal choice")
    await write_edge(env.driver, subgoal, SUBGOAL_OF, goal)
    await write_edge(env.driver, choice, AFFECTS_GOAL, subgoal)

    raw = await _context(env, "goals", goal)

    assert _uids(raw, "sub_goals") == {subgoal}
    assert _distances(raw, "affecting_choices") == {choice: 2}


# ---------------------------------------------------------------------------
# C. A view names its kind
# ---------------------------------------------------------------------------


async def test_the_principles_embodying_habits_are_habits_not_learning_paths(env: Env) -> None:
    principle = await _principle(env, "C embodied")
    habit = await _habit(env, "C embodying habit")
    path = f"lp.{MARK}.embodying"
    await seed_published_learning_path(env.driver, path, _title("C embodying path"))
    await write_edge(env.driver, habit, EMBODIES_PRINCIPLE, principle)
    await write_edge(env.driver, path, EMBODIES_PRINCIPLE, principle)

    raw = await _context(env, "principles", principle)
    typed = await env.services.principles.relationships.get_cross_domain_context_typed(principle)
    page = await _page(env, "principles", principle)

    assert _uids(raw, "embodying_habits") == {habit}
    assert typed.is_ok, typed
    assert {h.uid for h in typed.value.habits} == {habit}
    assert _title("C embodying habit") in under_heading(page, "Habits that embody this principle")
    assert _title("C embodying path") not in page


async def test_the_events_scheduling_choices_are_choices_not_path_steps(env: Env) -> None:
    event = await _event(env, "C scheduled")
    choice = await _choice(env, "C scheduling choice")
    step = f"ps.{MARK}.scheduling"
    await seed_published_path_step(env.driver, step, _title("C scheduling step"))
    await write_edge(env.driver, choice, SCHEDULES_EVENT, event)
    await write_edge(env.driver, step, SCHEDULES_EVENT, event)

    raw = await _context(env, "events", event)
    page = await _page(env, "events", event)

    assert _uids(raw, "scheduled_by_choices") == {choice}
    assert _title("C scheduling choice") in under_heading(page, "Choices that scheduled this event")
    assert _title("C scheduling step") not in page


async def test_a_habits_reinforcers_are_tasks_and_events_and_no_habit_view_exists(
    env: Env,
) -> None:
    habit = await _habit(env, "C reinforced")
    task = await _task(env, "C reinforcing task")
    event = await _event(env, "C reinforcing event")
    other = await _habit(env, "C reinforcing habit")
    for source in (task, event, other):
        await write_edge(env.driver, source, REINFORCES_HABIT, habit)

    raw = await _context(env, "habits", habit)

    assert _uids(raw, "reinforcing_tasks") == {task}
    assert _uids(raw, "reinforcing_events") == {event}
    assert "reinforcing_habits" not in raw
    assert other not in _everywhere(raw)


async def test_an_events_demonstrated_principle_is_not_among_its_habits(env: Env) -> None:
    """The control in the same graph: the habit the event reinforces is its habit."""
    event = await _event(env, "C demonstrating")
    principle = await _principle(env, "C demonstrated")
    habit = await _habit(env, "C event habit")
    await write_edge(env.driver, event, DEMONSTRATES_PRINCIPLE, principle)
    await write_edge(env.driver, event, REINFORCES_HABIT, habit)

    raw = await _context(env, "events", event)
    typed = await env.services.events.relationships.get_cross_domain_context_typed(event)

    assert _uids(raw, "demonstrated_principles") == {principle}
    assert typed.is_ok, typed
    assert {h.uid for h in typed.value.habits} == {habit}


async def test_a_practiced_at_event_edge_is_read_by_no_view(env: Env) -> None:
    """A habit and a principle each hold a ``PRACTICED_AT_EVENT`` edge into the event: the
    event's context, its habits and its page carry neither. The control in the same
    graph: the principle the event demonstrates is on the page."""
    event = await _event(env, "C practiced")
    habit = await _habit(env, "C practicing habit")
    principle = await _principle(env, "C practicing principle")
    demonstrated = await _principle(env, "C demonstrated control")
    await write_edge(env.driver, habit, PRACTICED_AT_EVENT, event)
    await write_edge(env.driver, principle, PRACTICED_AT_EVENT, event)
    await write_edge(env.driver, event, DEMONSTRATES_PRINCIPLE, demonstrated)

    raw = await _context(env, "events", event)
    typed = await env.services.events.relationships.get_cross_domain_context_typed(event)
    page = await _page(env, "events", event)

    assert not {habit, principle} & _everywhere(raw)
    assert typed.is_ok, typed
    assert typed.value.habits == []
    assert _title("C demonstrated control") in under_heading(
        page, "Principles this event demonstrates"
    )
    assert _title("C practicing habit") not in page
    assert _title("C practicing principle") not in page


# ---------------------------------------------------------------------------
# D. The vault door writes a task's habit link only to a habit
# ---------------------------------------------------------------------------


async def test_a_task_files_reinforces_habit_naming_a_goal_writes_no_edge(
    env: Env, tmp_path: Path
) -> None:
    """Two task files differ only in the kind their ``connections.reinforces_habit`` names:
    the habit gets its edge, the goal none."""
    habit = await _habit(env, "D habit")
    goal = await _goal(env, "D goal")
    named = {"habit": habit, "goal": goal}
    for kind, target in named.items():
        write_vault_file(
            tmp_path,
            f"d-{kind}",
            entity_type="task",
            uid=f"task.{MARK}.d-{kind}",
            owner=CALLER,
            connections={"reinforces_habit": [target]},
        )

    await sync_vault(env.driver, tmp_path, event_bus=env.services.event_bus)

    habit_edges = await edges_between(env.driver, f"task.{MARK}.d-habit", habit)
    goal_edges = await edges_between(env.driver, f"task.{MARK}.d-goal", goal)
    assert [(e.type, e.source, e.target) for e in habit_edges] == [
        (REINFORCES_HABIT, f"task.{MARK}.d-habit", habit)
    ]
    assert goal_edges == []
