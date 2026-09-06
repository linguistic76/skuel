"""
Cross-Domain Analytics Service
================================

Subscribes to domain events to build cross-domain analytics and insights.

Features:
- Financial goal tracking (link expenses to goals)
- Learning velocity tracking
- Cross-domain correlation analysis

All analytics are built by subscribing to existing events - no service changes needed!
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.constants import CompletionVelocityWindow, HabitConsistencyWindow
from core.events import (
    GoalCreated,
    # NOTE: JournalCreated REMOVED (February 2026) - Journal merged into Reports
    # Journal mood tracking now handled via report events
    # NOTE: Finance (ExpenseCreated/ExpensePaid) REMOVED (ADR-052 Phase 5) -
    # native expense module demolished; only the invoice module survives.
    KnowledgeMastered,
    LearningPathCompleted,
    TaskCompleted,
)
from core.models.type_hints import UserUID
from core.utils.decorators import with_error_handling
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.cross_domain_protocols import CrossDomainBackendOperations


@dataclass
class LearningVelocityMetrics:
    """Learning velocity and progress metrics."""

    user_uid: UserUID
    period_days: int

    # Velocity metrics
    kus_mastered_per_week: float
    paths_completed: int
    total_learning_hours: float

    # Trend
    velocity_trend: str  # "accelerating", "steady", "slowing"
    compared_to_previous_period: float  # % change


# NOTE: JournalMoodAnalysis + get_mood_analysis removed (SKUEL030 tranche 3).
# They were fed by a JournalAnalytics node that lost its writer with ADR-054, so
# the query matched nothing and the analysis was assembled from hardcoded
# placeholders (average_mood=0.65, mood_trend="stable", fixed themes). Real
# sentiment analysis over UserEntry is semantic-layer roadmap work.


class CrossDomainAnalyticsService:
    """
    Cross-domain analytics service built entirely on event subscriptions.

    This service demonstrates the power of event-driven architecture:
    - No direct coupling to other services
    - Builds analytics by listening to events
    - Can be enabled/disabled by subscribing/unsubscribing

    Usage:
        # Wire in bootstrap
        analytics = CrossDomainAnalyticsService(backend)

        event_bus.subscribe(GoalCreated, analytics.handle_goal_created)
        # NOTE: JournalCreated subscription removed (February 2026)
        event_bus.subscribe(KnowledgeMastered, analytics.handle_knowledge_mastered)
        event_bus.subscribe(LearningPathCompleted, analytics.handle_path_completed)

        # Query analytics
        velocity = await analytics.get_learning_velocity(user_uid, days_back=30)

    Semantic Types Used:
    - This is an analytics service that does not create semantic relationships
    - Consumes events from other services that create semantic relationships
    - No semantic relationship types used (event-driven aggregation only)
    """

    def __init__(self, backend: "CrossDomainBackendOperations") -> None:
        """
        Initialize cross-domain analytics service.

        Args:
            backend: CrossDomainBackend for analytics storage
        """
        self.backend = backend
        self.logger = get_logger("skuel.services.cross_domain_analytics")

        # In-memory caches for fast analytics (could be Redis in production)
        self._learning_cache: defaultdict[str, list[dict]] = defaultdict(list)
        # NOTE: _journal_cache removed (February 2026) - Journal merged into Reports
        # NOTE: _expense_cache removed (ADR-052 Phase 5) - native expense module demolished

    # ========================================================================
    # EVENT HANDLERS - Financial Goal Tracking
    # NOTE: handle_expense_created / handle_expense_paid removed (ADR-052 Phase 5).
    # The native expense module was demolished; only the invoice module survives,
    # so there are no ExpenseCreated/ExpensePaid events to track.
    # ========================================================================

    def handle_goal_created(self, event: GoalCreated) -> Result[None]:
        """Track financial goals for expense linking."""
        # Store goal for expense correlation
        self.logger.debug(f"Tracked goal for financial analytics: {event.goal_uid}")
        return Result.ok(None)

    # ========================================================================
    # EVENT HANDLERS - Learning Velocity
    # ========================================================================

    async def handle_knowledge_mastered(self, event: KnowledgeMastered) -> Result[None]:
        """
        Track knowledge mastery for learning velocity analysis.

        Builds:
        - Learning velocity (KUs mastered per week)
        - Mastery quality trends
        - Learning path progression
        """
        try:
            learning_data = {
                "ku_uid": event.ku_uid,
                "user_uid": event.user_uid,
                "mastery_score": event.mastery_score,
                "time_to_mastery_hours": event.time_to_mastery_hours,
                "occurred_at": event.occurred_at,
            }

            # Cache for velocity calculation
            self._learning_cache[event.user_uid].append(learning_data)

            # Persist velocity metrics
            result = await self.backend.upsert_learning_velocity(
                user_uid=event.user_uid,
                mastery_score=event.mastery_score,
                occurred_at=event.occurred_at.isoformat(),
            )
            if result.is_error:
                self.logger.error(f"Error tracking learning velocity: {result.error}")

            self.logger.debug(f"Tracked knowledge mastery for velocity: {event.ku_uid}")
            return Result.ok(None)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Database error tracking learning velocity: {e}")
            return Result.fail(
                Errors.database(
                    message=f"Failed to track learning velocity: {e!s}",
                    operation="handle_knowledge_mastered",
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(
                f"Unexpected error tracking learning velocity: {type(e).__name__}: {e}"
            )
            return Result.fail(
                Errors.system(
                    message=f"Failed to track learning velocity: {e!s}",
                    operation="handle_knowledge_mastered",
                )
            )

    async def handle_path_completed(self, event: LearningPathCompleted) -> Result[None]:
        """Track learning path completion for velocity analysis."""
        try:
            result = await self.backend.increment_paths_completed(user_uid=event.user_uid)
            if result.is_error:
                self.logger.error(f"Error tracking path completion: {result.error}")

            self.logger.debug(f"Tracked path completion for velocity: {event.path_uid}")
            return Result.ok(None)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Database error tracking path completion: {e}")
            return Result.fail(
                Errors.database(
                    message=f"Failed to track path completion: {e!s}",
                    operation="handle_path_completed",
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Unexpected error tracking path completion: {type(e).__name__}: {e}")
            return Result.fail(
                Errors.system(
                    message=f"Failed to track path completion: {e!s}",
                    operation="handle_path_completed",
                )
            )

    # ========================================================================
    # EVENT HANDLERS - Journal/Report Mood Analysis
    # NOTE: handle_journal_created removed (February 2026) - Journal merged into Reports
    # JournalCreated event no longer fired. Mood analysis can be re-added
    # by subscribing to SubmissionCreated and filtering entity_type="journal".
    # ========================================================================

    # ========================================================================
    # EVENT HANDLERS - Activity Domain Tracking
    # ========================================================================

    async def handle_task_completed(self, event: TaskCompleted) -> Result[None]:
        """Record the completion moment on the user's ProductivityAnalytics node.

        The node carries exactly two figures — ``first_completion_at`` and
        ``last_completion_at`` — and this handler is their only writer.
        ``tasks_completed`` is not maintained here or anywhere: it is derived
        at read from the tasks the user currently owns in ``completed``
        (:meth:`get_productivity_metrics`), so it needs no event at all — a
        reopen or a deletion lowers it without anyone having to hear about it,
        which a stored tally maintained from completion events cannot do.

        **``is_repeat`` gates the whole handler, because the whole handler
        accumulates.** The arc's contract is that the flag gates what
        *accumulates* (an append, a stamp) and never what *derives*; with the
        count derived at read there is nothing left here that derives. A
        repeat is the explicit-complete cascade re-running on an
        already-completed task, and it carries a fresh ``occurred_at`` even
        though nothing transitioned — writing that to ``last_completion_at``
        would report a completion moment that never happened, moving "when did
        this user most recently complete something" forward on a click that
        completed nothing. A reopen never reaches this service at all
        (``TaskReopened`` has no analytics subscriber now that no count is
        stored) and would have nothing to write if it did: it is the opposite
        of a completion.

        See :class:`TaskCompleted` for the contract.
        """
        if event.is_repeat:
            self.logger.debug(f"Repeat complete records no completion moment: {event.task_uid}")
            return Result.ok(None)

        try:
            result = await self.backend.stamp_productivity_completion(
                user_uid=event.user_uid,
                occurred_at=event.occurred_at.isoformat(),
            )
            if result.is_error:
                self.logger.error(f"Error stamping productivity completion: {result.error}")
            else:
                self.logger.debug(f"Stamped productivity completion for task: {event.task_uid}")
            return Result.ok(None)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Database error stamping productivity completion: {e}")
            return Result.fail(
                Errors.database(
                    message=f"Failed to stamp productivity completion: {e!s}",
                    operation="handle_task_completed",
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(
                f"Unexpected error stamping productivity completion: {type(e).__name__}: {e}"
            )
            return Result.fail(
                Errors.system(
                    message=f"Failed to stamp productivity completion: {e!s}",
                    operation="handle_task_completed",
                )
            )

    async def handle_habit_completed(self, event: Any) -> Result[None]:
        """
        Track a habit completion on the user's cumulative HabitAnalytics node.

        Maintains exactly three figures — ``total_completions`` (a running
        tally, incremented once per event), ``first_completion_at`` and
        ``last_completion_at``. A tally is the correct shape here: a habit
        completed fifty times genuinely has fifty completions and there is no
        "currently completed" set to recount, which is precisely why habits
        stayed on the incrementing helper when tasks left it.

        It is a cumulative record, not the consistency metric.
        ``get_habit_consistency`` counts ``:HabitCompletion`` records over a
        trailing window instead, so this node's blindness to the bulk-logging
        door (``HabitCompletionBulk`` has no subscriber) costs the cumulative
        figures but not the score.
        """
        try:
            result = await self.backend.upsert_habit_analytics(
                user_uid=event.user_uid,
                occurred_at=event.occurred_at.isoformat(),
            )
            if result.is_error:
                self.logger.error(f"Error tracking habit completion: {result.error}")

            self.logger.debug(f"Tracked habit completion for analytics: {event.habit_uid}")
            return Result.ok(None)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Database error tracking habit completion: {e}")
            return Result.fail(
                Errors.database(
                    message=f"Failed to track habit completion: {e!s}",
                    operation="handle_habit_completed",
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(
                f"Unexpected error tracking habit completion: {type(e).__name__}: {e}"
            )
            return Result.fail(
                Errors.system(
                    message=f"Failed to track habit completion: {e!s}",
                    operation="handle_habit_completed",
                )
            )

    async def handle_event_completed(self, event: Any) -> Result[None]:
        """
        Track calendar event completions for engagement analytics.

        Builds:
        - Event attendance patterns
        - Category-based event tracking
        - Time allocation analysis
        """
        try:
            result = await self.backend.upsert_event_analytics(
                user_uid=event.user_uid,
                occurred_at=event.occurred_at.isoformat(),
            )
            if result.is_error:
                self.logger.error(f"Error tracking event attendance: {result.error}")

            self.logger.debug(f"Tracked event attendance for analytics: {event.event_uid}")
            return Result.ok(None)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Database error tracking event attendance: {e}")
            return Result.fail(
                Errors.database(
                    message=f"Failed to track event attendance: {e!s}",
                    operation="handle_event_completed",
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(
                f"Unexpected error tracking event attendance: {type(e).__name__}: {e}"
            )
            return Result.fail(
                Errors.system(
                    message=f"Failed to track event attendance: {e!s}",
                    operation="handle_event_completed",
                )
            )

    # ========================================================================
    # ANALYTICS QUERIES
    # ========================================================================

    @with_error_handling(
        error_type="system", operation="get_learning_velocity", uid_param="user_uid"
    )
    async def get_learning_velocity(
        self, user_uid: UserUID, days_back: int = 30
    ) -> Result[LearningVelocityMetrics]:
        """
        Calculate learning velocity metrics.

        Args:
            user_uid: UID of the user,
            days_back: Number of days to analyze

        Returns:
            Result containing learning velocity metrics
        """
        start_date = datetime.now() - timedelta(days=days_back)

        result = await self.backend.get_learning_velocity_metrics(
            user_uid=user_uid,
            start_date=start_date.isoformat(),
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        record = records[0] if records else None

        # "no_data" means no mastery history, NOT "no LearningVelocity node".
        # The query anchors on the User and OPTIONAL-matches both the node and
        # the edges, so a valid user always yields one row — `record` is now
        # falsy only for a user that does not exist. Without the total_kus test
        # a brand-new learner would fall through and be reported as "steady"
        # with all-zero figures, which reads as a real measurement rather than
        # an absence of one.
        if not record or not (record["total_kus"] or 0):
            return Result.ok(
                LearningVelocityMetrics(
                    user_uid=user_uid,
                    period_days=days_back,
                    kus_mastered_per_week=0.0,
                    paths_completed=(record["velocity"] or {}).get("paths_completed", 0)
                    if record
                    else 0,
                    total_learning_hours=0.0,
                    velocity_trend="no_data",
                    compared_to_previous_period=0.0,
                )
            )

        # Calculate metrics
        recent_kus = record["recent_kus"] or 0
        weeks = days_back / 7
        kus_per_week = recent_kus / weeks if weeks > 0 else 0

        # Compare to previous period. total_kus is counted from the same
        # MASTERED edges as recent_kus, NOT read off velocity.kus_mastered:
        # that node property is an event-driven counter, so a mastery recorded
        # through a non-event path (e.g. the pathways progress route) would
        # inflate recent_kus past it and make previous_kus negative
        # (Codex P2 on #737). The node still supplies paths_completed — but it
        # is NULLABLE: the query anchors on the User and OPTIONAL-matches the
        # node, so a user whose masteries all came through non-event writers
        # (no KnowledgeMastered event → no node upserted) still gets real
        # velocity figures instead of a bogus "no_data".
        velocity_data = record["velocity"] or {}
        total_kus = record["total_kus"] or 0
        previous_kus = total_kus - recent_kus
        previous_per_week = previous_kus / weeks if weeks > 0 else 0

        trend = "steady"
        if kus_per_week > previous_per_week * 1.2:
            trend = "accelerating"
        elif kus_per_week < previous_per_week * 0.8:
            trend = "slowing"

        change_pct = (
            ((kus_per_week - previous_per_week) / previous_per_week * 100)
            if previous_per_week > 0
            else 0.0
        )

        metrics = LearningVelocityMetrics(
            user_uid=user_uid,
            period_days=days_back,
            kus_mastered_per_week=kus_per_week,
            paths_completed=velocity_data.get("paths_completed", 0),
            total_learning_hours=record["total_hours"] or 0.0,
            velocity_trend=trend,
            compared_to_previous_period=change_pct,
        )

        return Result.ok(metrics)

    @with_error_handling(
        error_type="system", operation="get_productivity_metrics", uid_param="user_uid"
    )
    async def get_productivity_metrics(self, user_uid: UserUID) -> Result[dict]:
        """
        Get productivity analytics from task completions.

        Reads the two completion stamps off the ProductivityAnalytics node
        (written by ``handle_task_completed``) together with both counts,
        derived live from the graph in the same read.

        **``completion_velocity`` is a rate over a fixed trailing window** —
        tasks stamped ``completion_date`` within the last
        ``CompletionVelocityWindow.DAYS`` calendar days *ending today*, divided
        by that window in weeks. It answers "how fast is this user completing
        tasks *now*", and it is the only figure here that is not cumulative.
        Both ends are bounded: a trailing window ends where the present does, so
        a future-dated completion stamp — which the task update door does not
        refuse — is outside it until its date arrives rather than counted in
        every window from now until then.

        It used to be the lifetime completion count divided by the span from the
        user's first-ever completion to their most recent one. That denominator
        only ever grows, so the metric could only decay, and it degenerated at
        both edges: with a single completion the span is zero, which read as
        0.0 before the stamps were both written and as a full week's rate after.
        Neither number was wrong about the data — the denominator was wrong
        about the question. Fixed-window arithmetic has no degenerate case: the
        divisor is a constant, and an empty window is honestly 0.0.

        A user with **no completions in the window reports 0.0**, whatever their
        lifetime history says. That is the intended reading: velocity is a
        current rate, and someone who has completed nothing this month is
        completing nothing per week. Their cumulative figures are still right
        beside it, unchanged.

        **Both counts are derived from one graph read.** ``tasks_completed``
        is every task the user currently owns in ``completed`` and
        ``tasks_completed_in_window`` is the subset whose ``completion_date``
        falls inside the window, counted by the same traversal — so the window
        is a subset of the total by construction and the payload cannot
        contradict itself. The total used to be a stored figure the event
        handlers maintained, and a tally that only ever counts up cannot
        follow a graph where completions are also *removed* — a completed task
        deleted, or reopened. The stored field, its reconciliation instrument
        and the contradiction they produced together are gone
        (``CrossDomainBackend.get_productivity_analytics`` records the
        measurement). Neither count needs the analytics node to exist. A completed
        task carrying no ``completion_date`` is in the total but excluded from
        the window rather than assumed recent.

        Only the two stamps come from the node, and only the ``TaskCompleted``
        handler writes them. Every door into ``completed`` now publishes that
        event — the vault bulk upsert included — so a user's stamps are absent
        only for completions that predate the cascade reaching their door;
        ``./dev backfill-productivity-stamps`` fills that history once.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing productivity metrics dict with:
            - tasks_completed: Tasks currently in COMPLETED, derived at read
              (not a lifetime tally of completion *events*: completing the same
              task twice after a reopen counts once, a reopened task counts
              zero)
            - first_completion_at: First completion timestamp
            - last_completion_at: Most recent completion timestamp
            - velocity_window_days: Length of the trailing window
            - tasks_completed_in_window: The velocity numerator
            - completion_velocity: Tasks per week over that window
        """
        today = date.today()

        result = await self.backend.get_productivity_analytics(
            user_uid=user_uid,
            window_start=CompletionVelocityWindow.start_date(today).isoformat(),
            window_end=CompletionVelocityWindow.end_date(today).isoformat(),
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        # The query aggregates, so it yields exactly one row for any user; the
        # empty guard is for a read that came back with nothing at all.
        record = records[0] if records else None
        # `analytics` is null for a user with no node — both counts stand on
        # their own, so that is a real reading with absent stamps, not a
        # missing one.
        analytics = (record["analytics"] if record else None) or {}
        tasks_completed = record["tasks_completed"] if record else 0
        completed_in_window = record["completed_in_window"] if record else 0

        velocity = completed_in_window / CompletionVelocityWindow.WEEKS

        return Result.ok(
            {
                "user_uid": user_uid,
                "tasks_completed": tasks_completed,
                "first_completion_at": analytics.get("first_completion_at"),
                "last_completion_at": analytics.get("last_completion_at"),
                "velocity_window_days": CompletionVelocityWindow.DAYS,
                "tasks_completed_in_window": completed_in_window,
                "completion_velocity": round(velocity, 2),
            }
        )

    @with_error_handling(
        error_type="system", operation="get_habit_consistency", uid_param="user_uid"
    )
    async def get_habit_consistency(self, user_uid: UserUID) -> Result[dict]:
        """
        Get habit consistency analytics.

        ``consistency_score`` is a rate over a fixed trailing window
        (:class:`HabitConsistencyWindow`), counted from the user's
        ``:HabitCompletion`` records rather than read off the cumulative tally
        the ``HabitCompleted`` handler maintains. Two consequences, both
        deliberate:

        - The score cannot degenerate. The lifetime span it used to divide by
          was zero for a user with one completion (or several on one day) and
          only grew afterwards, so the metric read 0.0, then a fabricated
          7.0/week, then decayed for as long as the user kept going.
        - Completions logged through the bulk door — which publishes
          ``HabitCompletionBulk``, an event no analytics handler subscribes to —
          reach the score, because the records exist even where the tally does
          not.

        The window is bounded at both ends. A trailing window ends where the
        present does, so a future-stamped completion — reachable, since
        ``TrackHabitRequest`` accepts any ISO date and the calendar's day-scoped
        complete door bounds ``on_date`` to occurrence days but not to today —
        is outside it until its date arrives rather than inflating the score
        every day until then.

        ``total_completions`` and the two stamps are still served beside it,
        unchanged: they are the cumulative record, and the rate is not. They
        come from the analytics node, so they remain blind to the bulk door;
        ``completions_in_window`` exceeding ``total_completions`` is that
        blindness made visible rather than a contradiction to reconcile.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing habit consistency metrics dict with:
            - total_completions: Cumulative habit completions the tally has seen
            - first_completion_at: First completion timestamp
            - last_completion_at: Last completion timestamp
            - consistency_window_days: Length of the trailing window
            - completions_in_window: The consistency numerator
            - consistency_score: Completions per week over that window
        """
        today = date.today()

        result = await self.backend.get_habit_analytics(
            user_uid=user_uid,
            window_start=HabitConsistencyWindow.start_date(today).isoformat(),
            window_end=HabitConsistencyWindow.end_date(today).isoformat(),
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        # The query aggregates, so it yields exactly one row for any user; the
        # empty guard is for a read that came back with nothing at all.
        record = records[0] if records else None
        # `analytics` is null for a user with no node — the derived count below
        # stands on its own, so that is a real reading, not a missing one.
        analytics = (record["analytics"] if record else None) or {}
        completions_in_window = record["completions_in_window"] if record else 0

        consistency = completions_in_window / HabitConsistencyWindow.WEEKS

        return Result.ok(
            {
                "user_uid": user_uid,
                "total_completions": analytics.get("total_completions", 0),
                "first_completion_at": analytics.get("first_completion_at"),
                "last_completion_at": analytics.get("last_completion_at"),
                "consistency_window_days": HabitConsistencyWindow.DAYS,
                "completions_in_window": completions_in_window,
                "consistency_score": round(consistency, 2),
            }
        )

    async def get_combined_dashboard(
        self, user_uid: UserUID, days_back: int = 30
    ) -> Result[dict[str, Any]]:
        """Build a combined analytics dashboard from multiple sub-queries.

        Currently just learning velocity. (Spending patterns removed in ADR-052
        Phase 5 — native expense module demolished; the `mood_analysis` key
        removed in SKUEL030 tranche 3 — its JournalAnalytics source lost its
        writer with ADR-054 and it had been serving placeholder constants.)

        Args:
            user_uid: User identifier
            days_back: Number of days to analyze

        Returns:
            Result with combined dashboard containing learning_velocity
            (None if unavailable)
        """
        learning_result = await self.get_learning_velocity(user_uid, days_back)

        dashboard: dict[str, Any] = {
            "user_uid": user_uid,
            "period_days": days_back,
            "generated_at": datetime.now().isoformat(),
            "learning_velocity": None,
        }

        if learning_result.is_ok:
            v = learning_result.value
            dashboard["learning_velocity"] = {
                "kus_mastered_per_week": v.kus_mastered_per_week,
                "paths_completed": v.paths_completed,
                "velocity_trend": v.velocity_trend,
            }

        return Result.ok(dashboard)
