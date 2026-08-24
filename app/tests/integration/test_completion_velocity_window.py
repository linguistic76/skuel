"""``completion_velocity``'s trailing window and the derived total, against a real graph.

The window is a Cypher predicate over ``Task.completion_date`` and the total is
a Cypher count over the same traversal, so everything load-bearing about them —
which rows fall inside, what the edges do, how the stamp's storage type is
compared, and what the total includes — is proven against the container rather
than a fake. The arithmetic that consumes the counts, and the meaning of an empty
window, are pinned DB-free in ``tests/unit/test_completion_velocity_window.py``
so they run on every CI job; this file is path-filtered.

What has to hold here:

1. **The boundary.** ``CompletionVelocityWindow.start_date`` is the first day
   *inside*. A completion on that exact day counts; one a single day older does
   not. An off-by-one is invisible in the reported number and silently skews
   every velocity in the app.
2. **Window membership is the canonical stamp, and only it.** A completed task
   with no ``completion_date`` is excluded from the window rather than assumed
   recent; a *stamped* task that is no longer completed is excluded too.
3. **The total is every task currently in COMPLETED** — stamped or not,
   windowed or not, future-dated or not — and never a property read off the
   analytics node. A reopened task is not in it. Both counts come from one
   traversal, so the window is a subset of the total by construction.
4. **Ownership.** Scoped by the universal ``:OWNS`` edge (ADR-086), so another
   user's completions cannot leak into either count.
5. **The upper bound.** A trailing window ends where the present does.
   ``TaskCreateRequest`` refuses a future ``completion_date``;
   ``TaskUpdateRequest`` does not, so the stamp is reachable — and a
   lower-bound-only predicate counted such a task in every window between now
   and its date, inflating the velocity permanently and silently.
6. **The stamp's storage type.** It is an ISO date **string** on every row of
   the live graph — but the writer decides the storage type, not this reader,
   so the reader truncates to the calendar day on both sides. A bare
   ``toString()`` survives that for the lower bound and quietly fails for the
   upper one: a datetime-typed stamp stringifies with a time component, which
   sorts *after* the bare end date and drops a row that belongs inside. Either
   failure would read as "this user completed less", never as an error.
7. **No analytics node required.** Both counts are derived, so the vault
   ``- [x]`` door — which writes no ``ProductivityAnalytics`` node at all —
   still yields real counts instead of a confident 0.0, with honestly absent
   stamps.
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
    """Own a Task off the user — the shape both counts traverse (ADR-086).

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


async def _seed_analytics(neo4j_driver, user_uid: str, *, legacy_count: int | None = None) -> None:
    """A node carrying the two stamps — and, for ``legacy_count``, the retired
    ``tasks_completed`` property a pre-derivation node still holds until the
    backfill drops it. The reader must never consult it."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MERGE (a:ProductivityAnalytics {user_uid: $user_uid})
            SET a.first_completion_at = datetime('2026-01-05T09:00:00'),
                a.last_completion_at = datetime('2026-06-11T17:30:00')
            WITH a
            WHERE $legacy_count IS NOT NULL
            SET a.tasks_completed = $legacy_count
            """,
            user_uid=user_uid,
            legacy_count=legacy_count,
        )
        await result.consume()


@pytest.mark.asyncio
@pytest.mark.integration
class TestCompletionVelocityWindow:
    """The trailing window and the derived total, exercised against the Neo4j testcontainer."""

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
        """One user per shape the two counts have to discriminate."""
        # WINDOW: four rows inside the window, four completed rows outside it,
        # one reopened row in neither count. Total 8, window 4.
        await _seed_analytics(neo4j_driver, WINDOW)
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
        # lingered, a task that is not completed is not a completion, in either count.
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.out_reopened",
            status=EntityStatus.ACTIVE,
            completion_date=TODAY.isoformat(),
        )
        # Stamped in the future — completed, so in the total; outside a *trailing*
        # window until its day comes.
        await _seed_task(
            neo4j_driver,
            WINDOW,
            "task.out_future",
            completion_date=(TODAY + timedelta(days=1)).isoformat(),
        )
        # STALE: real history, nothing inside the window — and a legacy node still
        # carrying the retired count (85) that disagrees with the graph (3): the
        # live-graph shape the derivation replaced.
        await _seed_analytics(neo4j_driver, STALE, legacy_count=85)
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
        its own reason (too old, exactly DAYS old, unstamped, reopened, future)."""
        result = await seeded.get_productivity_analytics(
            user_uid=WINDOW,
            window_start=FIRST_DAY_IN.isoformat(),
            window_end=LAST_DAY_IN.isoformat(),
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
            user_uid=WINDOW,
            window_start=FIRST_DAY_IN.isoformat(),
            window_end=LAST_DAY_IN.isoformat(),
        )

        assert result.is_ok
        assert result.value[0]["completed_in_window"] == 1
        assert result.value[0]["tasks_completed"] == 2, "both are completed; only one is recent"

    async def test_a_future_stamped_completion_is_outside_the_trailing_window(
        self, neo4j_driver, backend
    ):
        """The upper bound, isolated so the two rows are the whole answer.

        ``TaskCreateRequest`` refuses a future ``completion_date`` — "a future
        completion is semantically impossible and would pin itself atop
        completion-date-ordered reads" — but ``TaskUpdateRequest`` carries no
        such guard, so the stamp is reachable. A lower-bound-only predicate
        counted such a task in *every* window between now and its date: a
        velocity inflated permanently, and silently, because nothing about the
        number looks wrong. Today's row is seeded beside it so this
        discriminates the bound rather than merely counting.
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

        result = await backend.get_productivity_analytics(
            user_uid=WINDOW,
            window_start=FIRST_DAY_IN.isoformat(),
            window_end=LAST_DAY_IN.isoformat(),
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
            user_uid=WINDOW,
            window_start=FIRST_DAY_IN.isoformat(),
            window_end=LAST_DAY_IN.isoformat(),
        )

        assert result.is_ok
        assert result.value[0]["completed_in_window"] == 1

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

        result = await backend.get_productivity_analytics(
            user_uid=WINDOW,
            window_start=FIRST_DAY_IN.isoformat(),
            window_end=LAST_DAY_IN.isoformat(),
        )

        assert result.is_ok
        assert result.value[0]["tasks_completed"] == 4
        assert result.value[0]["completed_in_window"] == 1

    async def test_the_total_is_derived_from_the_graph_not_read_off_the_node(self, seeded):
        """STALE's node still carries the retired ``tasks_completed = 85``; the
        graph holds three completed tasks. Serving 85 would be the drift the
        derivation exists to end, reported under the new meaning."""
        result = await seeded.get_productivity_analytics(
            user_uid=STALE,
            window_start=FIRST_DAY_IN.isoformat(),
            window_end=LAST_DAY_IN.isoformat(),
        )

        assert result.is_ok
        assert result.value[0]["tasks_completed"] == 3
        assert result.value[0]["completed_in_window"] == 0
        analytics = result.value[0]["analytics"]
        assert analytics is not None and analytics["tasks_completed"] == 85, (
            "positive control: the legacy property is on the node and was read back"
        )

    async def test_another_users_completions_do_not_leak(self, seeded):
        """Scoped by the ``:OWNS`` edge, not by label — in both counts.

        VAULT owns six completions inside the same window as WINDOW's four. Each
        user must see only their own — a label-scoped count would report ten
        in the window and fourteen in total for both.
        """
        window = await seeded.get_productivity_analytics(
            user_uid=WINDOW,
            window_start=FIRST_DAY_IN.isoformat(),
            window_end=LAST_DAY_IN.isoformat(),
        )
        vault = await seeded.get_productivity_analytics(
            user_uid=VAULT,
            window_start=FIRST_DAY_IN.isoformat(),
            window_end=LAST_DAY_IN.isoformat(),
        )

        assert window.value[0]["completed_in_window"] == 4
        assert window.value[0]["tasks_completed"] == 8
        assert vault.value[0]["completed_in_window"] == 6
        assert vault.value[0]["tasks_completed"] == 6

    # ====================================================================
    # THE RATE, END TO END
    # ====================================================================

    async def test_a_steady_rate_reports_tasks_per_week(self, service, seeded):
        """Four completions in a 30-day window ≈ 0.93 tasks/week, beside a total of 8.

        The stamps span five months. Under the first→last denominator that pair
        *was* the metric, so if either still reached the arithmetic this could
        not pass.
        """
        result = await service.get_productivity_metrics(WINDOW)

        assert result.is_ok
        assert result.value["completion_velocity"] == pytest.approx(_velocity_for(4))
        assert result.value["tasks_completed_in_window"] == 4
        assert result.value["tasks_completed"] == 8
        assert result.value["velocity_window_days"] == CompletionVelocityWindow.DAYS

    async def test_a_user_whose_completions_are_all_older_reports_zero(self, service, seeded):
        """The case the redesign is for: real history, none of it this month.

        The old arithmetic served a plausible non-zero rate for work that had
        stopped. The total is reported beside the 0.0 — derived (3), not the
        legacy 85 the node still carries — and the stamps come from the node.
        """
        result = await service.get_productivity_metrics(STALE)

        assert result.is_ok
        assert result.value["completion_velocity"] == 0.0
        assert result.value["tasks_completed_in_window"] == 0
        assert result.value["tasks_completed"] == 3, "derived — never the node's retired 85"
        assert result.value["first_completion_at"] is not None, "positive control: node read"

    async def test_completions_with_no_analytics_node_still_report_real_counts(
        self, service, seeded
    ):
        """The vault ``- [x]`` door writes no node, and neither count needs one.

        The old read required the node with a mandatory MATCH, so this user got
        a flat 0.0 and — once the window was derived but the total was not — a
        payload that contradicted itself: six inside the window against a
        "total" of zero. Both counts come from the same traversal now, so the
        window is a subset of the total by construction. Only the stamps are
        absent, and honestly: no event ever recorded a completion moment for
        this user. ``./dev backfill-productivity-stamps`` fills history once.
        """
        result = await service.get_productivity_metrics(VAULT)

        assert result.is_ok
        assert result.value["completion_velocity"] == pytest.approx(_velocity_for(6))
        assert result.value["tasks_completed"] == 6
        assert result.value["tasks_completed_in_window"] == 6
        assert result.value["first_completion_at"] is None, "no node — no stamps"
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
