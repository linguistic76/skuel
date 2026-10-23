"""
Cross-Domain Analytics Service
================================

Per-user analytics across domains — learning velocity, task productivity and
habit consistency — each figure derived from the source facts on the read that
serves it (Analytics aggregate, they don't create).

The facts are the user's MASTERED edges and path enrollments, their tasks, and
their habit-completion records. Nothing here is stored, so nothing here can
drift from the graph: a task deleted or reopened, a completion logged through a
door that announces nothing, or a path finished by any writer reaches every
figure on the next read, with no one having to hear about it.

Backend: ``CrossDomainBackend`` (``get_learning_velocity_metrics``,
``get_productivity_analytics``, ``get_habit_analytics``).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.constants import CompletionVelocityWindow, HabitConsistencyWindow
from core.models.type_hints import UserUID
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

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


class CrossDomainAnalyticsService:
    """
    Per-user cross-domain analytics, read from the graph when asked for.

    Subscribes to no event and writes nothing: every figure is an aggregate over
    facts other services already keep, so there is no state here to keep
    current. A figure that could only be kept by hearing about every change
    would be wrong after the first change nobody announced.

    Usage:
        analytics = CrossDomainAnalyticsService(backend)
        velocity = await analytics.get_learning_velocity(user_uid, days_back=30)
    """

    def __init__(self, backend: CrossDomainBackendOperations) -> None:
        """
        Initialize cross-domain analytics service.

        Args:
            backend: CrossDomainBackend, the graph reads every figure comes from
        """
        self.backend = backend
        self.logger = get_logger("skuel.services.cross_domain_analytics")

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
        paths_completed = record["paths_completed"] if record else 0

        # "no_data" means no mastery history. The read anchors on the User and
        # OPTIONAL-matches the edges, so a valid user always yields one row —
        # `record` is falsy only for a user that does not exist. Without the
        # total_kus test a brand-new learner would fall through and be reported
        # as "steady" with all-zero figures, which reads as a real measurement
        # rather than an absence of one.
        if not record or not record["total_kus"]:
            return Result.ok(
                LearningVelocityMetrics(
                    user_uid=user_uid,
                    period_days=days_back,
                    kus_mastered_per_week=0.0,
                    paths_completed=paths_completed,
                    total_learning_hours=0.0,
                    velocity_trend="no_data",
                    compared_to_previous_period=0.0,
                )
            )

        recent_kus = record["recent_kus"]
        weeks = days_back / 7
        kus_per_week = recent_kus / weeks if weeks > 0 else 0

        # total_kus and recent_kus count the same MASTERED edges, so the
        # previous period is never negative.
        previous_kus = record["total_kus"] - recent_kus
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
            paths_completed=paths_completed,
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

        Every figure is derived from the tasks the user currently owns in
        ``completed``, on one read (``CrossDomainBackend.get_productivity_analytics``):
        the total, the window inside it, and the first and last completion day.
        A completed task deleted or reopened leaves all of them; a completed task
        that carries no ``completion_date`` is in the total and on no day.

        **``completion_velocity`` is a rate over a fixed trailing window** —
        tasks stamped ``completion_date`` within the last
        ``CompletionVelocityWindow.DAYS`` calendar days *ending today*, divided
        by that window in weeks. It answers "how fast is this user completing
        tasks *now*", and it is the only figure here that is not cumulative.
        Both ends are bounded: a trailing window ends where the present does, so
        a future-dated completion stamp — which the task update door does not
        refuse — is outside it until its date arrives rather than counted in
        every window from now until then. The divisor is a constant, so the rate
        has no degenerate case: one completion, or several on one day, is what
        the window counted, and an empty window is honestly 0.0.

        A user with **no completions in the window reports 0.0**, whatever their
        lifetime history says. That is the intended reading: velocity is a
        current rate, and someone who has completed nothing this month is
        completing nothing per week. Their cumulative figures are still right
        beside it.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing productivity metrics dict with:
            - tasks_completed: Tasks currently in COMPLETED (completing the same
              task twice after a reopen counts once, a reopened task counts zero)
            - first_completion_at: The earliest completion day (a ``date``)
            - last_completion_at: The latest completion day (a ``date``)
            - velocity_window_days: Length of the trailing window
            - tasks_completed_in_window: The velocity numerator
            - completion_velocity: Tasks per week over that window
        """
        today = today_in(current_zone())

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
        tasks_completed = record["tasks_completed"] if record else 0
        completed_in_window = record["completed_in_window"] if record else 0

        velocity = completed_in_window / CompletionVelocityWindow.WEEKS

        return Result.ok(
            {
                "user_uid": user_uid,
                "tasks_completed": tasks_completed,
                "first_completion_at": record["first_completed_on"] if record else None,
                "last_completion_at": record["last_completed_on"] if record else None,
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

        Every figure is derived from the user's ``:HabitCompletion`` records, on
        one read (``CrossDomainBackend.get_habit_analytics``): the cumulative
        total, the window inside it, and the first and last completion moment.
        Every completion door writes a record — the bulk door included — so
        every completion reaches every figure, and the window is a subset of the
        total by construction.

        ``consistency_score`` is a rate over a fixed trailing window
        (:class:`HabitConsistencyWindow`). The divisor is a constant, so the
        score cannot degenerate: one completion, or several on one day, is what
        the window counted, and a habit that stopped reads 0.0 with its
        cumulative record beside it.

        The window is bounded at both ends. A trailing window ends where the
        present does, so a future-stamped completion — reachable, since
        ``TrackHabitRequest`` accepts any ISO date and the calendar's day-scoped
        complete door bounds ``on_date`` to occurrence days but not to today —
        is outside it until its date arrives rather than inflating the score
        every day until then.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing habit consistency metrics dict with:
            - total_completions: Every completion record the user owns
            - first_completion_at: The earliest completion moment
            - last_completion_at: The latest completion moment
            - consistency_window_days: Length of the trailing window
            - completions_in_window: The consistency numerator
            - consistency_score: Completions per week over that window
        """
        today = today_in(current_zone())

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
        completions_in_window = record["completions_in_window"] if record else 0

        consistency = completions_in_window / HabitConsistencyWindow.WEEKS

        return Result.ok(
            {
                "user_uid": user_uid,
                "total_completions": record["total_completions"] if record else 0,
                "first_completion_at": record["first_completed_at"] if record else None,
                "last_completion_at": record["last_completed_at"] if record else None,
                "consistency_window_days": HabitConsistencyWindow.DAYS,
                "completions_in_window": completions_in_window,
                "consistency_score": round(consistency, 2),
            }
        )

    async def get_combined_dashboard(
        self, user_uid: UserUID, days_back: int = 30
    ) -> Result[dict[str, Any]]:
        """Build a combined analytics dashboard — today, the learning velocity.

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
