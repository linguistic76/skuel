"""The user's task-completion figures, derived from the graph at read — against a real graph.

Every figure ``get_productivity_analytics`` serves is a Cypher aggregate over the
tasks the user owns, so everything load-bearing about them — which rows fall
inside the window, what the edges do, how the stamp's storage type is compared,
what the total includes, and which days are the first and last completion — is
proven against the container rather than a fake. The arithmetic that consumes the
counts, and the meaning of an empty window, are pinned DB-free in
``tests/unit/test_completion_velocity_window.py`` so they run on every CI job;
this file is path-filtered.

What has to hold here:

1. **The boundary.** ``CompletionVelocityWindow.start_date`` is the first day
   *inside*. A completion on that exact day counts; one a single day older does
   not. An off-by-one is invisible in the reported number and silently skews
   every velocity in the app.
2. **Window membership is the canonical stamp, and only it.** A completed task
   with no ``completion_date`` is excluded from the window rather than assumed
   recent; a *stamped* task that is no longer completed is excluded too.
3. **The total is every task currently in COMPLETED** — stamped or not,
   windowed or not, future-dated or not. A reopened task is not in it. Both
   counts come from one traversal, so the window is a subset of the total by
   construction.
4. **First and last are completion days the graph still holds.** The earliest
   and latest ``completion_date`` among the tasks the user currently owns in
   COMPLETED — so a task reopened or deleted through the real doors leaves both,
   an unstamped task names no day, and a future-dated stamp is not a completion
   that has happened yet.
5. **Ownership.** Scoped by the universal ``:OWNS`` edge (ADR-086), so another
   user's completions cannot leak into any figure.
6. **The upper bound.** A trailing window ends where the present does.
   ``TaskCreateRequest`` refuses a future ``completion_date``;
   ``TaskUpdateRequest`` does not, so the stamp is reachable — and a
   lower-bound-only predicate would count such a task in every window between
   now and its date, inflating the velocity permanently and silently.
7. **The stamp's storage type.** It is an ISO date **string** on every row of
   the live graph — but the writer decides the storage type, not this reader,
   so the reader truncates to the calendar day on both sides. A bare
   ``toString()`` survives that for the lower bound and quietly fails for the
   upper one: a datetime-typed stamp stringifies with a time component, which
   sorts *after* the bare end date and drops a row that belongs inside. Either
   failure would read as "this user completed less", never as an error.

Nothing here seeds an analytics node: every figure stands on the tasks alone.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio

from core.constants import CompletionVelocityWindow
from core.models.enums.entity_enums import EntityStatus
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

WINDOW = "user_velocity_window"
STALE = "user_velocity_stale"
VAULT = "user_velocity_vault"

TODAY = today_in(current_zone())
FIRST_DAY_IN = CompletionVelocityWindow.start_date(TODAY)
LAST_DAY_IN = CompletionVelocityWindow.end_date(TODAY)
LAST_DAY_OUT = TODAY - timedelta(days=CompletionVelocityWindow.DAYS)


def _velocity_for(count: int) -> float:
    return round(count / CompletionVelocityWindow.WEEKS, 2)


async def _seed_task(
    neo4j_driver,
    user_uid: str,
    task_uid: str,
    *,
    status: EntityStatus = EntityStatus.COMPLETED,
    completion_date: str | None = None,
    temporal_stamp: bool = False,
) -> None:
    """Own a Task off the user — the shape every figure traverses (ADR-086).

    ``temporal_stamp`` writes the stamp as a native Neo4j ``date()`` instead of
    the ISO string every live writer produces, to prove the reader survives a
    writer that changes its mind.
    """
    stamp_clause = ""
    if completion_date is not None:
        stamp_clause = (
            "SET t.completion_date = date($completion_date)"
            if temporal_stamp
            else "SET t.completion_date = $completion_date"
        )

    async with neo4j_driver.session() as session:
        result = await session.run(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            MERGE (t:Entity:Task {{uid: $task_uid}})
            SET t.user_uid = $user_uid,
                t.entity_type = 'task',
                t.title = $task_uid,
                t.status = $status
            {stamp_clause}
            MERGE (u)-[:OWNS]->(t)
            """,
            user_uid=user_uid,
            task_uid=task_uid,
            status=status.value,
            completion_date=completion_date,
        )
        await result.consume()


@pytest.mark.asyncio
@pytest.mark.integration
class TestCompletionVelocityWindow:
    """The trailing window, the derived total and the derived days, against the testcontainer."""

    @pytest_asyncio.fixture
    async def backend(self, neo4j_driver, clean_neo4j):
        from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
        from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

        return CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))

    @pytest_asyncio.fixture
    async def service(self, backend):
        from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService

        return CrossDomainAnalyticsService(backend)

    @pytest_asyncio.fixture
    async def tasks(self, neo4j_driver, backend):
        """The real task doors: the born-completed create, the update chokepoint, the delete."""
        from adapters.infrastructure.event_bus import InMemoryEventBus
        from adapters.persistence.neo4j.backends.activity_backends import TasksBackend
        from core.models.enums.neo_labels import NeoLabel
        from core.models.task.task import Task
        from core.services.tasks.tasks_core_service import TasksCoreService

        tasks_backend = TasksBackend(neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)
        return TasksCoreService(backend=tasks_backend, event_bus=InMemoryEventBus())

    @pytest_asyncio.fixture
    async def seeded(self, neo4j_driver, backend):
        """One user per shape the figures have to discriminate."""
        # WINDOW: four rows inside the window, four completed rows outside it,
        # one reopened row in neither count. Total 8, window 4.
        await _seed_task(neo4j_driver, WINDOW, "task.win_today", completion_date=TODAY.isoformat())
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.win_yesterday",
            completion_date=(TODAY - timedelta(days=1)).isoformat(),
        )
        # The boundary itself: the first day inside the window.
        await _seed_task(
            neo4j_driver, WINDOW, "task.win_boundary", completion_date=FIRST_DAY_IN.isoformat()
        )
        # A stamp written as a native temporal rather than an ISO string.
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.win_temporal",
            completion_date=TODAY.isoformat(),
            temporal_stamp=True,
        )
        # One day past the boundary — exactly DAYS old.
        await _seed_task(
            neo4j_driver, WINDOW, "task.out_boundary", completion_date=LAST_DAY_OUT.isoformat()
        )
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.out_ancient",
            completion_date=(TODAY - timedelta(days=200)).isoformat(),
        )
        # Completed but never stamped — in the total, excluded from the window
        # rather than assumed recent.
        await _seed_task(neo4j_driver, WINDOW, "task.out_unstamped", completion_date=None)
        # Stamped but reopened — the stamp clear is the writer's job; even if one
        # lingered, a task that is not completed is not a completion, in any figure.
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.out_reopened",
            status=EntityStatus.ACTIVE,
            completion_date=(TODAY - timedelta(days=400)).isoformat(),
        )
        # Stamped in the future — completed, so in the total; outside a *trailing*
        # window until its day comes, and not yet a completion day.
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.out_future",
            completion_date=(TODAY + timedelta(days=1)).isoformat(),
        )
        # STALE: real history, nothing inside the window.
        for offset in (31, 90, 400):
            await _seed_task(
                neo4j_driver,
                STALE,
                f"task.stale_{offset}",
                completion_date=(TODAY - timedelta(days=offset)).isoformat(),
            )

        # VAULT: completions in the window, through a door that announces nothing.
        for n in range(6):
            await _seed_task(
                neo4j_driver,
                VAULT,
                f"task.vault_{n}",
                completion_date=(TODAY - timedelta(days=n)).isoformat(),
            )

        return backend

    async def _read(self, backend, user_uid: str):
        result = await backend.get_productivity_analytics(
            user_uid=user_uid,
            window_start=FIRST_DAY_IN.isoformat(),
            window_end=LAST_DAY_IN.isoformat(),
        )
        assert result.is_ok, result
        return result.value[0]

    # ====================================================================
    # THE WINDOW PREDICATE
    # ====================================================================

    async def test_only_stamped_completed_tasks_inside_the_window_are_counted(self, seeded):
        """Four of the user's nine tasks fall inside; five are excluded, each for
        its own reason (too old, exactly DAYS old, unstamped, reopened, future)."""
        row = await self._read(seeded, WINDOW)

        assert row["completed_in_window"] == 4

    async def test_the_boundary_day_is_inside_and_one_day_older_is_outside(
        self, neo4j_driver, backend
    ):
        """Isolated from the mixed fixture so the two rows are the whole answer.

        ``start_date`` is inclusive; a completion exactly ``DAYS`` days old is
        the first one outside. Both rows are seeded, so this discriminates the
        boundary rather than merely counting.
        """
        await _seed_task(
            neo4j_driver, WINDOW, "task.edge_in", completion_date=FIRST_DAY_IN.isoformat()
        )
        await _seed_task(
            neo4j_driver, WINDOW, "task.edge_out", completion_date=LAST_DAY_OUT.isoformat()
        )

        row = await self._read(backend, WINDOW)

        assert row["completed_in_window"] == 1
        assert row["tasks_completed"] == 2, "both are completed; only one is recent"

    async def test_a_future_stamped_completion_is_outside_the_trailing_window(
        self, neo4j_driver, backend
    ):
        """The upper bound, isolated so the two rows are the whole answer.

        A lower-bound-only predicate counts a future-stamped task in *every*
        window between now and its date: a velocity inflated permanently, and
        silently, because nothing about the number looks wrong. The graph is
        seeded directly because the bound is the reader's own guarantee, owed to
        any stamp already stored and to any writer that never passes a request
        model. Today's row is seeded beside it so this discriminates the bound
        rather than merely counting.
        """
        await _seed_task(
            neo4j_driver, WINDOW, "task.bound_today", completion_date=TODAY.isoformat()
        )
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.bound_tomorrow",
            completion_date=(TODAY + timedelta(days=1)).isoformat(),
        )

        row = await self._read(backend, WINDOW)

        assert row["completed_in_window"] == 1
        assert row["last_completed_on"] == TODAY, "a future stamp is not a completion yet"

    async def test_a_temporally_typed_stamp_still_compares(self, neo4j_driver, backend):
        """``toString()`` earns its place: the writer decides the storage type.

        A stamp stored as a native ``date`` compared raw against a string bound
        yields null, which drops the row — the failure would read as "this user
        completed less", never as an error. The derived days read it too.
        """
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.temporal_only",
            completion_date=TODAY.isoformat(),
            temporal_stamp=True,
        )

        row = await self._read(backend, WINDOW)

        assert row["completed_in_window"] == 1
        assert row["first_completed_on"] == TODAY
        assert row["last_completed_on"] == TODAY

    # ====================================================================
    # THE DERIVED TOTAL
    # ====================================================================

    async def test_the_total_counts_every_currently_completed_task_stamped_or_not(
        self, neo4j_driver, backend
    ):
        """Isolated: one row per way a completed task can sit outside the window.

        The total answers "how many tasks are completed", not "how many recent
        completions carry a stamp": unstamped, ancient and future-dated rows are
        all completed and all count. The reopened row is the one that does not —
        it is not completed, whatever stamp it still carries. The window inside
        the same read is exactly one of the four.
        """
        await _seed_task(neo4j_driver, WINDOW, "task.t_recent", completion_date=TODAY.isoformat())
        await _seed_task(neo4j_driver, WINDOW, "task.t_unstamped", completion_date=None)
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.t_ancient",
            completion_date=(TODAY - timedelta(days=365)).isoformat(),
        )
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.t_future",
            completion_date=(TODAY + timedelta(days=3)).isoformat(),
        )
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.t_reopened",
            status=EntityStatus.ACTIVE,
            completion_date=TODAY.isoformat(),
        )

        row = await self._read(backend, WINDOW)

        assert row["tasks_completed"] == 4
        assert row["completed_in_window"] == 1

    async def test_another_users_completions_do_not_leak(self, seeded):
        """Scoped by the ``:OWNS`` edge, not by label — in every figure.

        VAULT owns six completions inside the same window as WINDOW's four, and
        STALE's oldest is older than any of WINDOW's. Each user must see only
        their own — a label-scoped read would report ten in the window and
        seventeen in total for all three, and one shared first day.
        """
        window = await self._read(seeded, WINDOW)
        vault = await self._read(seeded, VAULT)
        stale = await self._read(seeded, STALE)

        assert (window["completed_in_window"], window["tasks_completed"]) == (4, 8)
        assert (vault["completed_in_window"], vault["tasks_completed"]) == (6, 6)
        assert (stale["completed_in_window"], stale["tasks_completed"]) == (0, 3)
        assert window["first_completed_on"] == TODAY - timedelta(days=200)
        assert stale["first_completed_on"] == TODAY - timedelta(days=400)
        assert vault["first_completed_on"] == TODAY - timedelta(days=5)

    # ====================================================================
    # THE DERIVED FIRST AND LAST COMPLETION DAYS
    # ====================================================================

    async def test_first_and_last_are_the_earliest_and_latest_completed_days(self, seeded):
        """Among WINDOW's nine tasks the days span 200 days ago to today.

        The reopened task's older stamp (400 days) is not a completion, the
        unstamped one names no day, and tomorrow's stamp has not happened — so
        none of the three moves either end.
        """
        row = await self._read(seeded, WINDOW)

        assert row["first_completed_on"] == TODAY - timedelta(days=200)
        assert row["last_completed_on"] == TODAY

    async def test_a_reopened_task_leaves_first_and_a_deleted_task_leaves_last(
        self, backend, tasks
    ):
        """Through the real doors: the born-completed create, a reopen, a delete.

        Three tasks completed 20, 10 and 5 days ago. Reopening the oldest through
        the update chokepoint moves the first day to the middle one; deleting the
        newest through the delete door moves the last day back to it. Both days
        are what the graph still holds, so neither door has to announce anything
        for the figures to follow.
        """
        from core.models.task.task_request import TaskCreateRequest
        from core.models.task.task_update_intent import TaskUpdateIntent

        days = {"old": TODAY - timedelta(days=20), "mid": TODAY - timedelta(days=10)}
        days["new"] = TODAY - timedelta(days=5)
        uids: dict[str, str] = {}
        for name, day in days.items():
            created = await tasks.create_task(
                TaskCreateRequest(
                    title=f"Completed {name}",
                    status=EntityStatus.COMPLETED,
                    completion_date=day,
                ),
                WINDOW,
            )
            assert created.is_ok, created
            uids[name] = created.value.uid

        before = await self._read(backend, WINDOW)
        assert (before["first_completed_on"], before["last_completed_on"]) == (
            days["old"],
            days["new"],
        ), "positive control: the create door's stamps are what the read derives from"

        reopened = await tasks.update_task(
            uids["old"], TaskUpdateIntent(status=EntityStatus.ACTIVE.value)
        )
        assert reopened.is_ok, reopened
        after_reopen = await self._read(backend, WINDOW)
        assert after_reopen["first_completed_on"] == days["mid"]
        assert after_reopen["tasks_completed"] == 2

        deleted = await tasks.delete_task(uids["new"])
        assert deleted.is_ok, deleted
        after_delete = await self._read(backend, WINDOW)
        assert after_delete["last_completed_on"] == days["mid"]
        assert after_delete["tasks_completed"] == 1

    # ====================================================================
    # THE PAYLOAD, END TO END
    # ====================================================================

    async def test_a_steady_rate_reports_tasks_per_week(self, service, seeded):
        """Four completions in a 30-day window ≈ 0.93 tasks/week, beside a total of 8.

        The completion days span 200 days, so if the span between them reached
        the arithmetic this could not pass.
        """
        result = await service.get_productivity_metrics(WINDOW)

        assert result.is_ok
        assert result.value["completion_velocity"] == pytest.approx(_velocity_for(4))
        assert result.value["tasks_completed_in_window"] == 4
        assert result.value["tasks_completed"] == 8
        assert result.value["velocity_window_days"] == CompletionVelocityWindow.DAYS

    async def test_a_user_whose_completions_are_all_older_reports_zero(self, service, seeded):
        """Real history, none of it this month: the rate is 0.0 and the record stands beside it."""
        result = await service.get_productivity_metrics(STALE)

        assert result.is_ok
        assert result.value["completion_velocity"] == 0.0
        assert result.value["tasks_completed_in_window"] == 0
        assert result.value["tasks_completed"] == 3
        assert result.value["first_completion_at"] == TODAY - timedelta(days=400)
        assert result.value["last_completion_at"] == TODAY - timedelta(days=31)

    async def test_completions_through_a_silent_door_report_every_figure(self, service, seeded):
        """VAULT's completions were never announced, and no figure needs them to be.

        A figure kept by an event handler would know nothing of these six; every
        figure here is read off the tasks themselves.
        """
        result = await service.get_productivity_metrics(VAULT)

        assert result.is_ok
        assert result.value["completion_velocity"] == pytest.approx(_velocity_for(6))
        assert result.value["tasks_completed"] == 6
        assert result.value["tasks_completed_in_window"] == 6
        assert result.value["first_completion_at"] == TODAY - timedelta(days=5)
        assert result.value["last_completion_at"] == TODAY

    async def test_a_user_with_nothing_at_all_reports_zeros(self, service, seeded):
        """No tasks — not even a ``:User`` row.

        Every match in the read is OPTIONAL and it aggregates, so it yields
        exactly one row rather than an empty result the service would have to
        treat as a separate case.
        """
        result = await service.get_productivity_metrics("user_velocity_nobody")

        assert result.is_ok
        assert result.value["completion_velocity"] == 0.0
        assert result.value["tasks_completed"] == 0
        assert result.value["tasks_completed_in_window"] == 0
        assert result.value["first_completion_at"] is None
        assert result.value["last_completion_at"] is None
