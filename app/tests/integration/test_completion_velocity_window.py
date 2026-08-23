"""``completion_velocity``'s trailing window, against a real graph.

The window is a Cypher predicate over ``Task.completion_date``, so everything
load-bearing about it — which rows fall inside, what the edges do, and how the
stamp's storage type is compared — is proven against the container rather than a
fake. The arithmetic that consumes the count, and the meaning of an empty
window, are pinned DB-free in ``tests/unit/test_completion_velocity_window.py``
so they run on every CI job; this file is path-filtered.

What has to hold here:

1. **The boundary.** ``CompletionVelocityWindow.start_date`` is the first day
   *inside*. A completion on that exact day counts; one a single day older does
   not. An off-by-one is invisible in the reported number and silently skews
   every velocity in the app.
2. **Membership is the canonical stamp, and only it.** A completed task with no
   ``completion_date`` is excluded rather than assumed recent; a *stamped* task
   that is no longer completed is excluded too.
3. **Ownership.** Scoped by the universal ``:OWNS`` edge (ADR-086), so another
   user's completions cannot leak into the rate.
4. **The stamp's storage type.** It is an ISO date **string** on every row of
   the live graph, and zero-padded ISO dates order correctly as strings — but
   the writer decides the storage type, not this reader. ``toString()`` is what
   keeps a temporal-typed stamp comparing correctly instead of silently
   matching nothing, which would read as "this user completed less", never as
   an error.
5. **No analytics node required.** The count is derived, so the vault ``- [x]``
   door — which writes no ``ProductivityAnalytics`` node at all — still yields a
   real velocity instead of a confident 0.0.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio

from core.constants import CompletionVelocityWindow
from core.models.enums.entity_enums import EntityStatus

WINDOW = "user_velocity_window"
STALE = "user_velocity_stale"
VAULT = "user_velocity_vault"

TODAY = date.today()
FIRST_DAY_IN = CompletionVelocityWindow.start_date(TODAY)
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
    """Own a Task off the user — the shape the window counts (ADR-086).

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


async def _seed_analytics(neo4j_driver, user_uid: str, tasks_completed: int) -> None:
    """A node carrying lifetime figures — the numbers the rate no longer reads."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MERGE (a:ProductivityAnalytics {user_uid: $user_uid})
            SET a.tasks_completed = $tasks_completed,
                a.first_completion_at = datetime('2026-01-05T09:00:00'),
                a.last_completion_at = datetime('2026-06-11T17:30:00')
            """,
            user_uid=user_uid,
            tasks_completed=tasks_completed,
        )
        await result.consume()


@pytest.mark.asyncio
@pytest.mark.integration
class TestCompletionVelocityWindow:
    """The trailing window, exercised against the Neo4j testcontainer."""

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
    async def seeded(self, neo4j_driver, backend):
        """One user per shape the window has to discriminate."""
        # WINDOW: four rows that count and five that must not.
        await _seed_analytics(neo4j_driver, WINDOW, 400)
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
        # Completed but never stamped — excluded, not assumed recent.
        await _seed_task(neo4j_driver, WINDOW, "task.out_unstamped", completion_date=None)
        # Stamped but reopened — the stamp clear is the writer's job; even if one
        # lingered, a task that is not completed is not a completion.
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.out_reopened",
            status=EntityStatus.ACTIVE,
            completion_date=TODAY.isoformat(),
        )
        # STALE: real lifetime history, nothing inside the window.
        await _seed_analytics(neo4j_driver, STALE, 85)
        for offset in (31, 90, 400):
            await _seed_task(
                neo4j_driver,
                STALE,
                f"task.stale_{offset}",
                completion_date=(TODAY - timedelta(days=offset)).isoformat(),
            )

        # VAULT: completions in the window, no analytics node at all.
        for n in range(6):
            await _seed_task(
                neo4j_driver,
                VAULT,
                f"task.vault_{n}",
                completion_date=(TODAY - timedelta(days=n)).isoformat(),
            )

        return backend

    # ====================================================================
    # THE WINDOW PREDICATE
    # ====================================================================

    async def test_only_stamped_completed_tasks_inside_the_window_are_counted(self, seeded):
        """Four of the user's nine tasks fall inside; five are excluded, each for
        its own reason (too old, exactly DAYS old, unstamped, reopened)."""
        result = await seeded.get_productivity_analytics(
            user_uid=WINDOW, window_start=FIRST_DAY_IN.isoformat()
        )

        assert result.is_ok
        assert result.value[0]["completed_in_window"] == 4

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

        result = await backend.get_productivity_analytics(
            user_uid=WINDOW, window_start=FIRST_DAY_IN.isoformat()
        )

        assert result.is_ok
        assert result.value[0]["completed_in_window"] == 1

    async def test_a_temporally_typed_stamp_still_compares(self, neo4j_driver, backend):
        """``toString()`` earns its place: the writer decides the storage type.

        A stamp stored as a native ``date`` compared raw against a string bound
        yields null, which drops the row — the failure would read as "this user
        completed less", never as an error.
        """
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.temporal_only",
            completion_date=TODAY.isoformat(),
            temporal_stamp=True,
        )

        result = await backend.get_productivity_analytics(
            user_uid=WINDOW, window_start=FIRST_DAY_IN.isoformat()
        )

        assert result.is_ok
        assert result.value[0]["completed_in_window"] == 1

    async def test_another_users_completions_do_not_leak(self, seeded):
        """Scoped by the ``:OWNS`` edge, not by label.

        VAULT owns six completions inside the same window as WINDOW's four. Each
        user must see only their own — a label-scoped count would report ten for
        both.
        """
        window = await seeded.get_productivity_analytics(
            user_uid=WINDOW, window_start=FIRST_DAY_IN.isoformat()
        )
        vault = await seeded.get_productivity_analytics(
            user_uid=VAULT, window_start=FIRST_DAY_IN.isoformat()
        )

        assert window.value[0]["completed_in_window"] == 4
        assert vault.value[0]["completed_in_window"] == 6

    # ====================================================================
    # THE RATE, END TO END
    # ====================================================================

    async def test_a_steady_rate_reports_tasks_per_week(self, service, seeded):
        """Four completions in a 30-day window ≈ 0.93 tasks/week.

        The stored lifetime count is 400 across a five-month span. Under the
        first→last denominator that pair *was* the metric, so if either still
        reached the arithmetic this could not pass.
        """
        result = await service.get_productivity_metrics(WINDOW)

        assert result.is_ok
        assert result.value["completion_velocity"] == pytest.approx(_velocity_for(4))
        assert result.value["tasks_completed_in_window"] == 4
        assert result.value["velocity_window_days"] == CompletionVelocityWindow.DAYS

    async def test_a_user_whose_completions_are_all_older_reports_zero(self, service, seeded):
        """The case the redesign is for: 85 lifetime completions, none this month.

        The old arithmetic served a plausible non-zero rate for work that had
        stopped. The cumulative figures are still reported beside the 0.0 — the
        history is not erased, it just is not the rate.
        """
        result = await service.get_productivity_metrics(STALE)

        assert result.is_ok
        assert result.value["completion_velocity"] == 0.0
        assert result.value["tasks_completed_in_window"] == 0
        assert result.value["tasks_completed"] == 85, "positive control: the node was read"
        assert result.value["first_completion_at"] is not None

    async def test_completions_with_no_analytics_node_still_report_a_real_velocity(
        self, service, seeded
    ):
        """The vault ``- [x]`` door writes no node, and the rate does not need one.

        The old read required the node with a mandatory MATCH, so this user got
        a flat 0.0 — the same confident zero the reconciliation instrument
        exists to correct, here on the read side.
        """
        result = await service.get_productivity_metrics(VAULT)

        assert result.is_ok
        assert result.value["completion_velocity"] == pytest.approx(_velocity_for(6))
        assert result.value["tasks_completed"] == 0, "no node — cumulative figures are absent"
        assert result.value["last_completion_at"] is None

    async def test_a_user_with_nothing_at_all_reports_zeros(self, service, seeded):
        """No node, no tasks — not even a ``:User`` row.

        Every match in the read is OPTIONAL and it aggregates, so it yields
        exactly one row of nulls rather than an empty result the service would
        have to treat as a separate case.
        """
        result = await service.get_productivity_metrics("user_velocity_nobody")

        assert result.is_ok
        assert result.value["completion_velocity"] == 0.0
        assert result.value["tasks_completed"] == 0
        assert result.value["tasks_completed_in_window"] == 0
