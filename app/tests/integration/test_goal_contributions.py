"""A goal's tally counts the tasks and events that contribute to it — over the composed app.

A task or an event contributes to a goal through ``(contributor)-[:CONTRIBUTES_TO_GOAL]->
(Goal)``, a task to any number of goals. A TASK_BASED goal's stored tally
(``current_value`` / ``target_value``, ``progress_percentage``) counts its owner's
contributions in three classes: done (COMPLETED), out (CANCELLED, not counted) and not
done (everything else, FAILED included). One event, ``GoalContributionsChanged``, is
the tally's only trigger, and goal progress its one subscriber.

Each test reads the goal the recompute WROTE — never the handler being called — after a
write through a production door. A status-move test seeds its "before" with no door at
all (the edges written straight into the graph, the goal's figures stored as a recompute
would have left them), so the write under test is the one thing that can move the goal:

- a task linked to two goals counts toward both; a completed event moves its goal;
- every status write that moves a contribution between classes moves the stored tally:
  ``update_task`` (cancel, reopen, fail), ``complete_tasks_bulk``, ``update_event``
  (back to scheduled, cancelled from completed and from scheduled), ``miss_habit_event``
  (at the service: it has no door), and the vault door's status change for a task file
  and an event file;
- the last contribution leaving writes 0 / 0 and 0%, and un-achieves a goal that was at
  100%; a settled (CANCELLED) goal reaching 100% keeps its status and is not announced
  as achieved;
- the tally reads the goal's owner, whatever user an announcement names;
- the cancel guard counts open contributing TASKS (DRAFT and POSTPONED open, FAILED
  not), never events;
- the rich user context carries one row per task, with every goal it contributes to;
- ``/self-checkin``'s goal weight reads an event's ``supported_goals``;
- an event that executes a contributing task does not itself support the task's goal.

The membership doors — link, unlink, delete, the vault field, the DSL, the generators,
the PathStep spawn — are in ``test_goal_contribution_doors.py``.

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.events import GoalAchieved
from core.models.enums.entity_enums import EntityStatus
from core.models.event.event_request import EventCreateRequest
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent
from core.models.type_hints import UserUID
from core.models.user.user import User
from core.services.user.unified_user_context import UserContext
from core.services.user.user_context_builder import UserContextBuilder
from tests.integration._activity_link_rig import (
    create,
    goal_tally,
    goals_contributed_to,
    published,
    signed_in_client,
    store_goal_tally,
    sync_vault,
    wipe,
    write_edge,
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

MARK = "zzzgoalctg"
CALLER = f"user_{MARK}"
OTHER = f"user_{MARK}_other"

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
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        yield Env(client=client, services=skuel_app.state.services, driver=driver)
    await wipe(driver, OTHER, MARK)


# ---------------------------------------------------------------------------
# Seeds and reads
# ---------------------------------------------------------------------------


async def _goal(env: Env, title: str) -> str:
    """A TASK_BASED goal — the one measurement a contribution tally is written for."""
    return await create(env.client, "goals", f"{MARK} {title}", measurement_type="task_based")


async def _task(env: Env, title: str, *goal_uids: str) -> str:
    """A task at the create door, contributing to ``goal_uids``."""
    return await create(
        env.client, "tasks", f"{MARK} {title}", contributes_to_goal_uids=list(goal_uids)
    )


async def _event(env: Env, title: str, *goal_uids: str, **fields: Any) -> str:  # boundary: JSON
    """A scheduled event at the create door, contributing to ``goal_uids``."""
    body: dict[str, Any] = {  # boundary: JSON body
        "event_date": (date.today() + timedelta(days=1)).isoformat(),
        "start_time": "09:00",
        "end_time": "10:00",
        "contributes_to_goal_uids": list(goal_uids),
        **fields,
    }
    return await create(env.client, "events", f"{MARK} {title}", **body)


async def _stored(env: Env, goal_uid: str) -> Goal:
    result = await env.services.goals.backend.get(goal_uid)
    assert result.is_ok and result.value is not None, result
    return result.value


async def _tally(env: Env, goal_uid: str) -> tuple[float | None, float | None]:
    return await goal_tally(env.driver, goal_uid)


async def _set_task(env: Env, task_uid: str, status: EntityStatus) -> None:
    result = await env.services.tasks.update_task(task_uid, TaskUpdateIntent(status=status.value))
    assert result.is_ok, result


async def _set_event(env: Env, event_uid: str, status: EntityStatus) -> None:
    result = await env.services.events.update_event(
        event_uid, EventUpdateIntent(status=status.value)
    )
    assert result.is_ok, result


async def _link(env: Env, goal_uid: str, *contributor_uids: str) -> None:
    """Write each contributor's edge straight into the graph — no door, no announcement."""
    for uid in contributor_uids:
        await write_edge(env.driver, uid, CONTRIBUTES_TO_GOAL, goal_uid)


async def _settle(env: Env, goal_uid: str, done: int, total: int) -> None:
    await store_goal_tally(env.driver, goal_uid, done, total)


# ---------------------------------------------------------------------------
# A. Several goals; B. events count
# ---------------------------------------------------------------------------


async def test_a_task_linked_to_two_goals_counts_toward_both(env: Env) -> None:
    first = await _goal(env, "A first")
    second = await _goal(env, "A second")
    task = await _task(env, "A shared", first, second)

    assert await goals_contributed_to(env.driver, task) == {first, second}
    assert await _tally(env, first) == (0, 1)
    assert await _tally(env, second) == (0, 1)

    await _set_task(env, task, EntityStatus.COMPLETED)

    for goal_uid in (first, second):
        stored = await _stored(env, goal_uid)
        assert (stored.current_value, stored.target_value) == (1, 1)
        assert stored.progress_percentage == pytest.approx(100.0)
        assert stored.status == EntityStatus.COMPLETED


async def test_a_completed_contributing_event_moves_its_goal(env: Env) -> None:
    goal = await _goal(env, "B")
    event = await _event(env, "B event", goal)
    await _settle(env, goal, 0, 1)

    await _set_event(env, event, EntityStatus.COMPLETED)

    stored = await _stored(env, goal)
    assert (stored.current_value, stored.target_value) == (1, 1)
    assert stored.progress_percentage == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# C. Status writes that move a contribution between classes
# ---------------------------------------------------------------------------


async def test_cancelling_an_open_task_takes_it_out_of_the_count(env: Env) -> None:
    goal = await _goal(env, "C cancel")
    done = await _task(env, "C cancel done")
    leaving = await _task(env, "C cancel leaving")
    await _set_task(env, done, EntityStatus.COMPLETED)
    await _link(env, goal, done, leaving)
    await _settle(env, goal, 1, 2)

    await _set_task(env, leaving, EntityStatus.CANCELLED)

    assert await _tally(env, goal) == (1, 1)
    assert (await _stored(env, goal)).progress_percentage == pytest.approx(100.0)


async def test_reopening_a_completed_task_lowers_the_count(env: Env) -> None:
    goal = await _goal(env, "C reopen")
    reopened = await _task(env, "C reopen task")
    other = await _task(env, "C reopen other")
    await _set_task(env, reopened, EntityStatus.COMPLETED)
    await _link(env, goal, reopened, other)
    await _settle(env, goal, 1, 2)

    await _set_task(env, reopened, EntityStatus.ACTIVE)

    assert await _tally(env, goal) == (0, 2)
    assert (await _stored(env, goal)).progress_percentage == pytest.approx(0.0)


async def test_a_failed_task_stays_in_the_denominator_as_not_done(env: Env) -> None:
    """Completed → FAILED moves done → not done: 2/2 becomes 1/2, not 1/1."""
    goal = await _goal(env, "C fail")
    kept = await _task(env, "C fail kept")
    failed = await _task(env, "C fail failed")
    await _set_task(env, kept, EntityStatus.COMPLETED)
    await _set_task(env, failed, EntityStatus.COMPLETED)
    await _link(env, goal, kept, failed)
    await _settle(env, goal, 2, 2)

    await _set_task(env, failed, EntityStatus.FAILED)

    stored = await _stored(env, goal)
    assert (stored.current_value, stored.target_value) == (1, 2)
    assert stored.progress_percentage == pytest.approx(50.0)
    assert stored.status == EntityStatus.ACTIVE  # un-achieved: below 100 again


async def test_completing_tasks_in_bulk_moves_the_count(env: Env) -> None:
    goal = await _goal(env, "C bulk")
    tasks = [await _task(env, f"C bulk {n}") for n in (1, 2)]
    await _link(env, goal, *tasks, await _task(env, "C bulk open"))
    await _settle(env, goal, 0, 3)

    done = await env.services.tasks.core.complete_tasks_bulk(tasks, UserUID(CALLER))

    assert done.is_ok and done.value == 2, done
    assert await _tally(env, goal) == (2, 3)


async def test_a_completed_event_set_back_to_scheduled_lowers_the_count(env: Env) -> None:
    goal = await _goal(env, "C event reopen")
    event = await _event(env, "C event reopen")
    await _set_event(env, event, EntityStatus.COMPLETED)
    await _link(env, goal, event)
    await _settle(env, goal, 1, 1)

    await _set_event(env, event, EntityStatus.SCHEDULED)

    stored = await _stored(env, goal)
    assert (stored.current_value, stored.target_value) == (0, 1)
    assert stored.status == EntityStatus.ACTIVE


async def test_a_completed_event_cancelled_leaves_the_count(env: Env) -> None:
    goal = await _goal(env, "C event done cancel")
    event = await _event(env, "C event done cancel")
    await _set_event(env, event, EntityStatus.COMPLETED)
    await _link(env, goal, event, await _task(env, "C event done cancel task"))
    await _settle(env, goal, 1, 2)

    await _set_event(env, event, EntityStatus.CANCELLED)

    assert await _tally(env, goal) == (0, 1)


async def test_a_scheduled_event_cancelled_leaves_the_count(env: Env) -> None:
    goal = await _goal(env, "C event open cancel")
    done = await _event(env, "C event open cancel done")
    leaving = await _event(env, "C event open cancel leaving")
    await _set_event(env, done, EntityStatus.COMPLETED)
    await _link(env, goal, done, leaving)
    await _settle(env, goal, 1, 2)

    await _set_event(env, leaving, EntityStatus.CANCELLED)

    assert await _tally(env, goal) == (1, 1)


async def test_a_habit_event_marked_missed_leaves_the_count(env: Env) -> None:
    """``miss_habit_event`` cancels the event — at the service, which no door reaches."""
    goal = await _goal(env, "C missed")
    done = await _event(env, "C missed done")
    missed = await _event(env, "C missed missed")
    await _set_event(env, done, EntityStatus.COMPLETED)
    await _link(env, goal, done, missed)
    await _settle(env, goal, 1, 2)

    result = await env.services.events.miss_habit_event(
        missed, UserContext(user_uid=CALLER), reason="overslept"
    )

    assert result.is_ok, result
    assert result.value.status == EntityStatus.CANCELLED
    assert await _tally(env, goal) == (1, 1)


async def test_the_vault_door_moves_the_count_when_a_file_changes_status(
    env: Env, tmp_path: Path
) -> None:
    """A task file open → cancelled, then an event file completed → scheduled.

    The files author no goal link, so the sync's own status classes are all that can
    move the goal (the vault's goal field is held by test_goal_contribution_doors.py).
    """
    goal = await _goal(env, "C vault")
    bus = env.services.event_bus
    task_uid, event_uid = f"task.{MARK}.c-vault", f"event.{MARK}.c-vault"

    def files(task_status: str, event_status: str) -> None:
        for name, entity_type, uid, status in (
            ("c-vault-task", "task", task_uid, task_status),
            ("c-vault-event", "event", event_uid, event_status),
        ):
            write_vault_file(
                tmp_path,
                name,
                entity_type=entity_type,
                uid=uid,
                owner=CALLER,
                extra=(f"status: {status}",),
            )

    files("scheduled", "completed")
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    await _link(env, goal, task_uid, event_uid)
    await _settle(env, goal, 1, 2)

    files("cancelled", "completed")
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _tally(env, goal) == (1, 1)

    files("cancelled", "scheduled")
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    stored = await _stored(env, goal)
    assert (stored.current_value, stored.target_value) == (0, 1)
    assert stored.status == EntityStatus.ACTIVE  # it was achieved at 1/1


# ---------------------------------------------------------------------------
# E. The last contribution leaving; a settled goal
# ---------------------------------------------------------------------------


async def test_the_last_contribution_leaving_writes_zero_of_zero_and_unachieves(
    env: Env,
) -> None:
    goal = await _goal(env, "E last")
    task = await _task(env, "E last task")
    await _set_task(env, task, EntityStatus.COMPLETED)
    await _link(env, goal, task)
    await _settle(env, goal, 1, 1)
    achieved = await _stored(env, goal)
    assert achieved.status == EntityStatus.COMPLETED
    assert achieved.achieved_date is not None

    await _set_task(env, task, EntityStatus.CANCELLED)

    stored = await _stored(env, goal)
    assert (stored.current_value, stored.target_value) == (0, 0)
    assert stored.progress_percentage == pytest.approx(0.0)
    assert stored.status == EntityStatus.ACTIVE
    assert stored.achieved_date is None


async def test_a_cancelled_goal_reaching_100_stays_cancelled_and_is_not_announced(
    env: Env,
) -> None:
    """One task, two goals that differ only in status: the active one is achieved,
    the cancelled one takes the figure and keeps its status."""
    active = await _goal(env, "E settled control")
    cancelled = await _goal(env, "E settled")
    task = await _task(env, "E settled task")
    for goal in (active, cancelled):
        await _link(env, goal, task)
        await _settle(env, goal, 0, 1)
    settled = await env.services.goals.update_goal(
        cancelled, GoalUpdateIntent(status=EntityStatus.CANCELLED.value)
    )
    assert settled.is_ok, settled

    with published(env.services.event_bus, GoalAchieved) as achieved:
        await _set_task(env, task, EntityStatus.COMPLETED)

    stored = await _stored(env, cancelled)
    assert (stored.current_value, stored.target_value) == (1, 1)
    assert stored.progress_percentage == pytest.approx(100.0)
    assert stored.status == EntityStatus.CANCELLED
    assert (await _stored(env, active)).status == EntityStatus.COMPLETED
    assert [event.goal_uid for event in achieved] == [active]


# ---------------------------------------------------------------------------
# F. The tally reads the goal's owner
# ---------------------------------------------------------------------------


async def test_the_tally_counts_only_the_goal_owners_contributions_whoever_is_named(
    env: Env,
) -> None:
    """Another user's completed task holds an edge into the goal, and an announcement
    names the goal under that user: the tally still counts only the owner's tasks."""
    from core.events import GoalContributionsChanged

    goal = await _goal(env, "F")
    await _task(env, "F open", goal)
    mine = await _task(env, "F mine")
    async with env.driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=OTHER)
    theirs = await env.services.tasks.create(
        Task(
            uid=f"task_{MARK}_theirs",
            user_uid=OTHER,
            title=f"{MARK} F theirs",
            status=EntityStatus.COMPLETED,
        )
    )
    assert theirs.is_ok, theirs
    await _set_task(env, mine, EntityStatus.COMPLETED)
    # The two edges differ only in the task's owner.
    await write_edge(env.driver, mine, CONTRIBUTES_TO_GOAL, goal)
    await write_edge(env.driver, theirs.value.uid, CONTRIBUTES_TO_GOAL, goal)

    await env.services.event_bus.publish_async(
        GoalContributionsChanged(
            user_uid=UserUID(OTHER), goal_uids=(goal,), contributor_uids=(theirs.value.uid,)
        )
    )

    assert await _tally(env, goal) == (1, 2)


# ---------------------------------------------------------------------------
# G. The cancel guard
# ---------------------------------------------------------------------------


async def test_an_open_contributing_task_blocks_a_cancel_and_nothing_else_does(
    env: Env,
) -> None:
    """A DRAFT task blocks; a FAILED task and a scheduled event do not — the refusal
    names one task. Once the draft is cancelled the goal cancels."""
    goal = await _goal(env, "G")
    draft = await _task(env, "G draft")
    failed = await _task(env, "G failed")
    await _set_task(env, failed, EntityStatus.FAILED)
    await _link(env, goal, draft, failed, await _event(env, "G event"))

    refused = await env.services.goals.cancel_goal(goal)

    assert refused.is_error
    assert "1 active task" in refused.expect_error().message
    assert (await _stored(env, goal)).status != EntityStatus.CANCELLED

    await _set_task(env, draft, EntityStatus.CANCELLED)
    cancelled = await env.services.goals.cancel_goal(goal)

    assert cancelled.is_ok, cancelled
    assert (await _stored(env, goal)).status == EntityStatus.CANCELLED


async def test_a_postponed_contributing_task_blocks_a_cancel(env: Env) -> None:
    goal = await _goal(env, "G postponed")
    task = await _task(env, "G postponed task")
    await _set_task(env, task, EntityStatus.POSTPONED)
    await _link(env, goal, task)

    refused = await env.services.goals.cancel_goal(goal)

    assert refused.is_error
    assert "1 active task" in refused.expect_error().message


# ---------------------------------------------------------------------------
# H. The rich user context's task row
# ---------------------------------------------------------------------------


async def test_a_task_with_two_goals_is_one_context_row_carrying_both(env: Env) -> None:
    first = await _goal(env, "H first")
    second = await _goal(env, "H second")
    task = await _task(env, "H task")
    await _link(env, first, task)
    await _link(env, second, task)
    builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(env.driver)))

    built = await builder.build_rich_user_context(
        CALLER, User(uid=CALLER, title=CALLER, email=f"{CALLER}@example.test")
    )

    assert built.is_ok, built
    context = built.value
    rows = [row for row in context.entities_rich["tasks"] if row["entity"]["uid"] == task]
    assert len(rows) == 1
    [row] = rows
    assert {goal["uid"] for goal in row["graph_context"]["contributing_goals"]} == {first, second}
    assert task in context.tasks_by_goal[first]
    assert task in context.tasks_by_goal[second]
    assert set(context.task_goal_associations[task]) == {first, second}


# ---------------------------------------------------------------------------
# I. /self-checkin's goal weight
# ---------------------------------------------------------------------------


async def test_the_engagement_assessment_counts_an_event_that_supports_a_goal(
    env: Env,
) -> None:
    """Two events today, one contributing to a goal: the evidence names one."""
    from core.models.goal.goal import Goal as GoalModel

    user = f"user_{MARK}_checkin"
    async with env.driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=user)
    try:
        goal = await env.services.goals.create(
            GoalModel(uid=f"goal_{MARK}_checkin", user_uid=user, title=f"{MARK} I")
        )
        assert goal.is_ok, goal
        for title, goals in (("I linked", [goal.value.uid]), ("I unlinked", [])):
            created = await env.services.events.create_event(
                EventCreateRequest(
                    title=f"{MARK} {title}",
                    event_date=date.today(),
                    start_time="09:00",
                    end_time="10:00",
                    contributes_to_goal_uids=goals,
                ),
                UserUID(user),
            )
            assert created.is_ok, created

        intelligence = env.services.events.intelligence
        _level, _score, evidence = await intelligence._calculate_system_engagement_for_dual_track(
            UserUID(user)
        )

        assert "2 events in period" in evidence
        assert "1 events support goals" in evidence
    finally:
        await wipe(env.driver, user, f"{MARK}_checkin")


# ---------------------------------------------------------------------------
# K. A contribution is not transitive
# ---------------------------------------------------------------------------


async def test_an_event_executing_a_contributing_task_does_not_support_its_goal(
    env: Env,
) -> None:
    """The event supports only the goal it links itself; the task's goal is the task's."""
    tasks_goal = await _goal(env, "K task goal")
    events_goal = await _goal(env, "K event goal")
    task = await _task(env, "K task", tasks_goal)
    event = await _event(env, "K event", events_goal, executes_tasks=[task])
    assert await goals_contributed_to(env.driver, event) == {events_goal}

    event_context = await env.services.events.relationships.get_cross_domain_context(event)
    task_context = await env.services.tasks.relationships.get_cross_domain_context(task)

    assert event_context.is_ok and task_context.is_ok
    assert {g["uid"] for g in event_context.value["supported_goals"]} == {events_goal}
    assert {g["uid"] for g in task_context.value["contributing_goals"]} == {tasks_goal}
