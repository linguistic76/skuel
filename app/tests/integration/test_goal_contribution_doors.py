"""Every door that changes a goal's contributions moves its stored tally — with no status change.

A task or an event contributes to a goal through ``(contributor)-[:CONTRIBUTES_TO_GOAL]->
(Goal)``. Gaining or losing one changes a TASK_BASED goal's tally as surely as a status
change does, so every door that writes or removes the edge — or a task's
``completion_updates_goal`` — announces ``GoalContributionsChanged`` and the goal is
recounted. Each test drives one door of the census and reads the tally the recompute
WROTE. Where a test needs a contribution in place before the door, it is written with no
door at all (the edge straight into the graph, the goal's figures stored as a recompute
would have left them), so the door under test is the one thing that can move the goal:

- the link doors ``POST /api/events/link-goal`` and ``POST /api/tasks/link-goal``;
- the task update's goal list (a full replace; ``[]`` clears);
- ``TasksService.unlink_task_from_goal`` and ``EventsService.unlink_event_from_goal``;
- the CRUD delete routes ``/api/tasks/delete`` and ``/api/events/delete``, which also
  publish ``TaskDeleted`` / ``CalendarEventDeleted``;
- the DSL (a task line linking two goals, an event line linking one);
- the goal task generator and the habit event scheduler;
- the PathStep engagement's spawn (a task template's ``contributes_to_goal_template_uid``)
  and the discard of a spawned task;
- the vault: ``connections.contributes_to_goal`` added and dropped, a deleted file, a
  changed ``completion_updates_goal``, and an Edge YAML of type ``CONTRIBUTES_TO_GOAL``
  written and deleted.

Status writes are in ``test_goal_contributions.py``. The app runs bootstrapped over its
own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.events import CalendarEventDeleted, TaskDeleted
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.goal_enums import MeasurementType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.models.task.task_update_intent import TaskUpdateIntent
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.task_template import TaskTemplate
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry import UserEntry
from core.services.dsl.activity_extractor import ActivityExtractorService
from core.services.user.unified_user_context import UserContext
from tests.integration._activity_link_rig import (
    create,
    goal_contributors,
    goal_tally,
    goals_contributed_to,
    published,
    signed_in_client,
    store_goal_tally,
    sync_vault,
    write_edge,
    write_edge_file,
    write_vault_file,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    import httpx
    from neo4j import AsyncDriver

    from core.models.goal.goal import Goal

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzgoaldoor"
CALLER = f"user_{MARK}"

CONTRIBUTES_TO_GOAL = RelationshipName.CONTRIBUTES_TO_GOAL.value


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


async def _goal(env: Env, title: str, **fields: Any) -> str:  # boundary: JSON body fields
    """A TASK_BASED goal — the one measurement a contribution tally is written for."""
    return await create(
        env.client, "goals", f"{MARK} {title}", measurement_type="task_based", **fields
    )


async def _task(env: Env, title: str, *goal_uids: str) -> str:
    return await create(
        env.client, "tasks", f"{MARK} {title}", contributes_to_goal_uids=list(goal_uids)
    )


async def _event(env: Env, title: str, *goal_uids: str) -> str:
    return await create(
        env.client,
        "events",
        f"{MARK} {title}",
        event_date=(date.today() + timedelta(days=1)).isoformat(),
        start_time="09:00",
        end_time="10:00",
        contributes_to_goal_uids=list(goal_uids),
    )


async def _complete_task(env: Env, task_uid: str) -> None:
    result = await env.services.tasks.update_task(
        task_uid, TaskUpdateIntent(status=EntityStatus.COMPLETED.value)
    )
    assert result.is_ok, result


async def _stored(env: Env, goal_uid: str) -> Goal:
    result = await env.services.goals.backend.get(goal_uid)
    assert result.is_ok and result.value is not None, result
    return result.value


async def _tally(env: Env, goal_uid: str) -> tuple[float | None, float | None]:
    return await goal_tally(env.driver, goal_uid)


async def _link(env: Env, goal_uid: str, *contributor_uids: str) -> None:
    """Write each contributor's edge straight into the graph — no door, no announcement."""
    for uid in contributor_uids:
        await write_edge(env.driver, uid, CONTRIBUTES_TO_GOAL, goal_uid)


async def _settle(env: Env, goal_uid: str, done: int, total: int) -> None:
    await store_goal_tally(env.driver, goal_uid, done, total)


async def _post(env: Env, path: str, **body: Any) -> None:  # boundary: JSON body
    response = await env.client.post(path, json=body)
    assert response.status_code == 200, (path, response.text[:500])


# ---------------------------------------------------------------------------
# Link doors
# ---------------------------------------------------------------------------


async def test_linking_a_scheduled_event_to_a_goal_at_one_of_one_makes_it_one_of_two(
    env: Env,
) -> None:
    goal = await _goal(env, "link event")
    done = await _task(env, "link event done")
    await _complete_task(env, done)
    await _link(env, goal, done)
    await _settle(env, goal, 1, 1)
    event = await _event(env, "link event")

    await _post(env, "/api/events/link-goal", event_uid=event, goal_uid=goal)

    assert await goals_contributed_to(env.driver, event) == {goal}
    assert await _tally(env, goal) == (1, 2)


async def test_linking_a_task_at_the_link_door_adds_it_to_the_count(env: Env) -> None:
    goal = await _goal(env, "link task")
    done = await _task(env, "link task done")
    await _complete_task(env, done)
    await _link(env, goal, done)
    await _settle(env, goal, 1, 1)
    task = await _task(env, "link task")

    await _post(env, "/api/tasks/link-goal", task_uid=task, goal_uid=goal)

    assert await goals_contributed_to(env.driver, task) == {goal}
    assert await _tally(env, goal) == (1, 2)


# ---------------------------------------------------------------------------
# The task update's goal list
# ---------------------------------------------------------------------------


async def test_the_task_updates_goal_list_moves_the_task_between_goals(env: Env) -> None:
    """A replace takes the task from the old goal to the new; ``[]`` takes it from both."""
    old = await _goal(env, "update old")
    new = await _goal(env, "update new")
    task = await _task(env, "update")
    await _complete_task(env, task)
    await _link(env, old, task)
    await _settle(env, old, 1, 1)

    await _post(env, f"/api/tasks/update?uid={task}", contributes_to_goal_uids=[new])

    assert await goals_contributed_to(env.driver, task) == {new}
    assert await _tally(env, old) == (0, 0)
    assert await _tally(env, new) == (1, 1)

    await _post(env, f"/api/tasks/update?uid={task}", contributes_to_goal_uids=[])

    assert await goals_contributed_to(env.driver, task) == set()
    assert await _tally(env, new) == (0, 0)


# ---------------------------------------------------------------------------
# Unlink
# ---------------------------------------------------------------------------


async def test_unlinking_an_event_and_then_a_task_each_leave_the_count(env: Env) -> None:
    goal = await _goal(env, "unlink")
    task = await _task(env, "unlink task")
    event = await _event(env, "unlink event")
    await _complete_task(env, task)
    await _link(env, goal, task, event)
    await _settle(env, goal, 1, 2)

    unlinked_event = await env.services.events.unlink_event_from_goal(event, goal)

    assert unlinked_event.is_ok, unlinked_event
    assert await goal_contributors(env.driver, goal) == {task}
    assert await _tally(env, goal) == (1, 1)

    unlinked_task = await env.services.tasks.unlink_task_from_goal(task, goal)

    assert unlinked_task.is_ok, unlinked_task
    assert await goal_contributors(env.driver, goal) == set()
    assert await _tally(env, goal) == (0, 0)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def test_deleting_a_task_and_an_event_at_the_crud_routes_recounts_their_goal(
    env: Env,
) -> None:
    goal = await _goal(env, "delete")
    done = await _task(env, "delete done")
    await _complete_task(env, done)
    task = await _task(env, "delete task")
    event = await _event(env, "delete event")
    await _link(env, goal, done, task, event)
    await _settle(env, goal, 1, 3)

    with published(env.services.event_bus, TaskDeleted, CalendarEventDeleted) as deleted:
        await _post(env, f"/api/tasks/delete?uid={task}")
        assert await _tally(env, goal) == (1, 2)
        await _post(env, f"/api/events/delete?uid={event}")
        assert await _tally(env, goal) == (1, 1)

    assert [
        (type(e).__name__, getattr(e, "task_uid", None) or getattr(e, "event_uid", None))
        for e in deleted
    ] == [("TaskDeleted", task), ("CalendarEventDeleted", event)]


# ---------------------------------------------------------------------------
# The DSL
# ---------------------------------------------------------------------------


async def test_dsl_lines_link_a_task_to_every_goal_and_an_event_to_its_goal(env: Env) -> None:
    first = await _goal(env, "dsl first")
    second = await _goal(env, "dsl second")
    events_goal = await _goal(env, "dsl event")
    when = (date.today() + timedelta(days=2)).isoformat()
    entry = UserEntry(
        uid=f"ue_{MARK}_dsl",
        title=f"{MARK} dsl",
        user_uid=CALLER,
        entity_type=EntityType.USER_ENTRY,
        status=EntityStatus.COMPLETED,
        pipeline=Pipeline.EXTRACT_ACTIVITIES,
        content=(
            f"- [ ] {MARK} drills @context(task) @link(goal:{first}, goal:{second})\n"
            f"- [ ] {MARK} club @context(event) @when({when}T07:00) @link(goal:{events_goal})\n"
        ),
    )
    extractor = ActivityExtractorService(
        tasks_service=env.services.tasks, events_service=env.services.events
    )

    extracted = await extractor.extract_and_create(entry, UserUID(CALLER))

    assert extracted.is_ok, extracted
    [task] = extracted.value.created_task_uids
    [event] = extracted.value.created_event_uids
    assert await goals_contributed_to(env.driver, task) == {first, second}
    assert await goals_contributed_to(env.driver, event) == {events_goal}
    for goal_uid in (first, second, events_goal):
        assert await _tally(env, goal_uid) == (0, 1)


# ---------------------------------------------------------------------------
# The generators
# ---------------------------------------------------------------------------


async def test_the_goal_task_generators_tasks_contribute_to_the_goal(env: Env) -> None:
    goal = await _goal(
        env, "generator", target_date=(date.today() + timedelta(days=15)).isoformat()
    )

    generated = await env.services.goal_task_generator.generate_tasks_for_goal(
        goal, UserContext(user_uid=CALLER), auto_create=True
    )

    assert generated.is_ok, generated
    created = {dto.uid for dto in generated.value}
    assert created
    assert await goal_contributors(env.driver, goal) == created
    assert await _tally(env, goal) == (0, len(created))


async def test_the_habit_schedulers_events_contribute_to_the_habits_goal(env: Env) -> None:
    goal = await _goal(env, "scheduler")
    habit = await create(env.client, "habits", f"{MARK} scheduler habit")
    linked = await env.services.goals.link_goal_to_habit(goal, habit)
    assert linked.is_ok, linked

    scheduled = await env.services.habit_event_scheduler.schedule_events_for_habit(
        habit, UserContext(user_uid=CALLER), auto_create=True, days_ahead=3
    )

    assert scheduled.is_ok, scheduled
    created = {dto.uid for dto in scheduled.value}
    assert created
    assert await goal_contributors(env.driver, goal) == created
    # A scheduled event is not done: each counts in the denominator.
    assert await _tally(env, goal) == (0, len(created))


# ---------------------------------------------------------------------------
# The PathStep engagement
# ---------------------------------------------------------------------------


async def _seed_path_step(driver: AsyncDriver) -> tuple[str, str, str]:
    """A PathStep with a TASK_BASED goal template and a task template contributing to it."""
    ps_uid, task_tpl, goal_tpl = f"ps_{MARK}", f"ttpl_{MARK}", f"gtpl_{MARK}"
    step = UniversalNeo4jBackend[PathStep](
        driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY
    )
    tasks = UniversalNeo4jBackend[TaskTemplate](
        driver, NeoLabel.TASK_TEMPLATE, TaskTemplate, base_label=NeoLabel.ENTITY
    )
    goals = UniversalNeo4jBackend[GoalTemplate](
        driver, NeoLabel.GOAL_TEMPLATE, GoalTemplate, base_label=NeoLabel.ENTITY
    )
    assert (await step.create(PathStep(uid=ps_uid, title=f"{MARK} step"))).is_ok
    assert (
        await goals.create(
            GoalTemplate(
                uid=goal_tpl,
                title=f"{MARK} spawned goal",
                status=EntityStatus.ACTIVE,
                target_offset=RelativeOffset(days=30),
                measurement_type=MeasurementType.TASK_BASED,
            )
        )
    ).is_ok
    assert (
        await tasks.create(
            TaskTemplate(
                uid=task_tpl,
                title=f"{MARK} spawned task",
                status=EntityStatus.ACTIVE,
                due_offset=RelativeOffset(days=7),
            )
        )
    ).is_ok
    # The task template's goal reference, stored as the template's own property.
    async with driver.session() as session:
        await session.run(
            """
            MATCH (ps {uid: $ps}), (tt {uid: $tt}), (gt {uid: $gt})
            SET tt.contributes_to_goal_template_uid = gt.uid
            MERGE (ps)-[:HAS_TASK_TEMPLATE]->(tt)
            MERGE (ps)-[:HAS_GOAL_TEMPLATE]->(gt)
            """,
            ps=ps_uid,
            tt=task_tpl,
            gt=goal_tpl,
        )
    return ps_uid, task_tpl, goal_tpl


async def _spawned_from(driver: AsyncDriver, template_uid: str) -> str | None:
    async with driver.session() as session:
        record = await (
            await session.run(
                "MATCH (n {user_uid: $user})-[:SPAWNED_FROM]->({uid: $tpl}) RETURN n.uid AS uid",
                user=CALLER,
                tpl=template_uid,
            )
        ).single()
    return None if record is None else str(record["uid"])


async def test_a_spawned_task_counts_toward_its_spawned_goal_until_it_is_discarded(
    env: Env,
) -> None:
    ps_uid, task_tpl, goal_tpl = await _seed_path_step(env.driver)
    engagement = env.services.ps_engagement

    engaged = await engagement.engage_pathstep(CALLER, ps_uid)

    assert engaged.is_ok, engaged
    task, goal = (
        await _spawned_from(env.driver, task_tpl),
        await _spawned_from(env.driver, goal_tpl),
    )
    assert task is not None and goal is not None
    assert await goals_contributed_to(env.driver, task) == {goal}
    assert await _tally(env, goal) == (0, 1)

    completed = await engagement.complete_pathstep(CALLER, ps_uid, {task_tpl: "discard"})

    assert completed.is_ok, completed
    assert await _spawned_from(env.driver, task_tpl) is None
    assert await _tally(env, goal) == (0, 0)


# ---------------------------------------------------------------------------
# The vault
# ---------------------------------------------------------------------------


def _task_file(
    vault: Path,
    name: str,
    goals: list[str],
    *,
    status: str = "completed",
    extra: tuple[str, ...] = (),
) -> Path:
    return write_vault_file(
        vault,
        name,
        entity_type="task",
        uid=f"task.{MARK}.{name}",
        owner=CALLER,
        connections={"contributes_to_goal": goals} if goals else None,
        extra=(f"status: {status}", *extra),
    )


async def test_a_vault_target_added_and_then_dropped_moves_each_goals_count(
    env: Env, tmp_path: Path
) -> None:
    first = await _goal(env, "vault field first")
    second = await _goal(env, "vault field second")
    bus = env.services.event_bus

    _task_file(tmp_path, "field", [first])
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _tally(env, first) == (1, 1)

    _task_file(tmp_path, "field", [first, second])
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _tally(env, second) == (1, 1)

    _task_file(tmp_path, "field", [second])
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await goals_contributed_to(env.driver, f"task.{MARK}.field") == {second}
    dropped = await _stored(env, first)
    assert (dropped.current_value, dropped.target_value) == (0, 0)
    assert dropped.status == EntityStatus.ACTIVE  # it was achieved at 1/1
    assert await _tally(env, second) == (1, 1)


async def test_a_vault_files_completion_updates_goal_moves_its_goals_count(
    env: Env, tmp_path: Path
) -> None:
    """The file authors no goal link; the edge is in place before the first change."""
    goal = await _goal(env, "vault opt out")
    bus = env.services.event_bus

    _task_file(tmp_path, "opt-out", [])
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    await _link(env, goal, f"task.{MARK}.opt-out")
    await _settle(env, goal, 1, 1)

    _task_file(tmp_path, "opt-out", [], extra=("completion_updates_goal: false",))
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _tally(env, goal) == (0, 0)

    _task_file(tmp_path, "opt-out", [], extra=("completion_updates_goal: true",))
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _tally(env, goal) == (1, 1)


async def test_deleting_a_vault_file_takes_its_contribution_from_the_count(
    env: Env, tmp_path: Path
) -> None:
    """The files author no goal link; their edges are in place before the deletions."""
    goal = await _goal(env, "vault deletion")
    bus = env.services.event_bus
    done = _task_file(tmp_path, "deleted-done", [])
    event = write_vault_file(
        tmp_path,
        "deleted-event",
        entity_type="event",
        uid=f"event.{MARK}.deleted-event",
        owner=CALLER,
        extra=("status: scheduled",),
    )
    _task_file(tmp_path, "deleted-bystander", [], status="scheduled")
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    await _link(env, goal, f"task.{MARK}.deleted-done", f"event.{MARK}.deleted-event")
    await _settle(env, goal, 1, 2)

    done.unlink()
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _tally(env, goal) == (0, 1)

    event.unlink()
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _tally(env, goal) == (0, 0)


async def test_an_edge_file_of_the_type_adds_and_its_deletion_removes_a_contribution(
    env: Env, tmp_path: Path
) -> None:
    goal = await _goal(env, "edge file")
    task = await _task(env, "edge file")
    bus = env.services.event_bus
    _task_file(tmp_path, "edge-bystander", [], status="scheduled")
    edge = write_edge_file(
        tmp_path, "edge-ctg", source=task, edge_type=CONTRIBUTES_TO_GOAL, target=goal
    )

    await sync_vault(env.driver, tmp_path, event_bus=bus)

    assert await goals_contributed_to(env.driver, task) == {goal}
    assert await _tally(env, goal) == (0, 1)
    await _complete_task(env, task)
    assert await _tally(env, goal) == (1, 1)

    edge.unlink()
    await sync_vault(env.driver, tmp_path, event_bus=bus)

    assert await goals_contributed_to(env.driver, task) == set()
    assert await _tally(env, goal) == (0, 0)
