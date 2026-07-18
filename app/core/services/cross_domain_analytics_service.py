"""
Cross-Domain Analytics Service
================================

Subscribes to domain events to build cross-domain analytics and insights.

Features:
- Financial goal tracking (link expenses to goals)
- Journal mood analysis (track sentiment over time)
- Learning velocity tracking
- Spending patterns by domain
- Cross-domain correlation analysis

All analytics are built by subscribing to existing events - no service changes needed!
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.events import (
    GoalCreated,
    # NOTE: JournalCreated REMOVED (February 2026) - Journal merged into Reports
    # Journal mood tracking now handled via report events
    # NOTE: Finance (ExpenseCreated/ExpensePaid) REMOVED (ADR-052 Phase 5) -
    # native expense module demolished; only the invoice module survives.
    KnowledgeMastered,
    LearningPathCompleted,
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


@dataclass
class JournalMoodAnalysis:
    """Mood analysis from journal entries."""

    user_uid: UserUID
    period_days: int

    # Mood tracking
    average_mood: float  # 0.0 to 1.0
    mood_trend: str  # "improving", "stable", "declining"
    most_common_themes: list[str]

    # Frequency
    entries_per_week: float
    longest_streak: int


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
        mood = await analytics.get_mood_analysis(user_uid, days_back=30)

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

    async def handle_task_completed(self, event: Any) -> Result[None]:
        """
        Track task completions for productivity analytics.

        Builds:
        - Task completion velocity (tasks per week)
        - Priority distribution patterns
        - Completion time trends
        """
        try:
            result = await self.backend.upsert_productivity_analytics(
                user_uid=event.user_uid,
                occurred_at=event.occurred_at.isoformat(),
            )
            if result.is_error:
                self.logger.error(f"Error tracking task completion: {result.error}")

            self.logger.debug(f"Tracked task completion for analytics: {event.task_uid}")
            return Result.ok(None)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Database error tracking task completion: {e}")
            return Result.fail(
                Errors.database(
                    message=f"Failed to track task completion: {e!s}",
                    operation="handle_task_completed",
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Unexpected error tracking task completion: {type(e).__name__}: {e}")
            return Result.fail(
                Errors.system(
                    message=f"Failed to track task completion: {e!s}",
                    operation="handle_task_completed",
                )
            )

    async def handle_habit_completed(self, event: Any) -> Result[None]:
        """
        Track habit completions for consistency analytics.

        Builds:
        - Habit consistency scores
        - Streak patterns across habits
        - Category-based habit tracking
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

        if not record:
            return Result.ok(
                LearningVelocityMetrics(
                    user_uid=user_uid,
                    period_days=days_back,
                    kus_mastered_per_week=0.0,
                    paths_completed=0,
                    total_learning_hours=0.0,
                    velocity_trend="no_data",
                    compared_to_previous_period=0.0,
                )
            )

        # Calculate metrics
        recent_kus = record["recent_kus"] or 0
        weeks = days_back / 7
        kus_per_week = recent_kus / weeks if weeks > 0 else 0

        # Compare to previous period
        velocity_data = record["velocity"]
        total_kus = velocity_data.get("kus_mastered", 0)
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

    @with_error_handling(error_type="system", operation="get_mood_analysis", uid_param="user_uid")
    async def get_mood_analysis(
        self, user_uid: UserUID, days_back: int = 30
    ) -> Result[JournalMoodAnalysis]:
        """
        Analyze journal mood and sentiment.

        Args:
            user_uid: UID of the user,
            days_back: Number of days to analyze

        Returns:
            Result containing mood analysis
        """
        result = await self.backend.get_journal_analytics(user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.ok(
                JournalMoodAnalysis(
                    user_uid=user_uid,
                    period_days=days_back,
                    average_mood=0.5,
                    mood_trend="no_data",
                    most_common_themes=[],
                    entries_per_week=0.0,
                    longest_streak=0,
                )
            )

        analytics = record["analytics"]
        total_entries = analytics.get("total_entries", 0)

        weeks = days_back / 7
        entries_per_week = total_entries / weeks if weeks > 0 else 0.0

        # Simplified mood analysis (would integrate with sentiment analysis in production)
        analysis = JournalMoodAnalysis(
            user_uid=user_uid,
            period_days=days_back,
            average_mood=0.65,  # Placeholder - would calculate from sentiment
            mood_trend="stable",  # Placeholder - would analyze trend
            most_common_themes=["reflection", "goals", "learning"],  # Placeholder
            entries_per_week=entries_per_week,
            longest_streak=7,  # Placeholder - would calculate from dates
        )

        return Result.ok(analysis)

    @with_error_handling(
        error_type="system", operation="get_productivity_metrics", uid_param="user_uid"
    )
    async def get_productivity_metrics(self, user_uid: UserUID) -> Result[dict]:
        """
        Get productivity analytics from task completions.

        Queries ProductivityAnalytics nodes created by handle_task_completed event handler.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing productivity metrics dict with:
            - tasks_completed: Total count
            - first_completion_at: First completion timestamp
            - last_completion_at: Last completion timestamp
            - completion_velocity: Tasks per week
        """
        result = await self.backend.get_productivity_analytics(user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "tasks_completed": 0,
                    "first_completion_at": None,
                    "last_completion_at": None,
                    "completion_velocity": 0.0,
                }
            )

        analytics = record["analytics"]
        tasks_completed = analytics.get("tasks_completed", 0)

        # Calculate velocity (tasks per week)
        first_at = analytics.get("first_completion_at")
        last_at = analytics.get("last_completion_at")

        velocity = 0.0
        if first_at and last_at:
            days_active = (last_at - first_at).days or 1
            weeks_active = days_active / 7
            velocity = tasks_completed / weeks_active if weeks_active > 0 else 0.0

        return Result.ok(
            {
                "user_uid": user_uid,
                "tasks_completed": tasks_completed,
                "first_completion_at": first_at,
                "last_completion_at": last_at,
                "completion_velocity": round(velocity, 2),
            }
        )

    @with_error_handling(
        error_type="system", operation="get_habit_consistency", uid_param="user_uid"
    )
    async def get_habit_consistency(self, user_uid: UserUID) -> Result[dict]:
        """
        Get habit consistency analytics.

        Queries HabitAnalytics nodes created by handle_habit_completed event handler.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing habit consistency metrics dict with:
            - total_completions: Total habit completions
            - first_completion_at: First completion timestamp
            - last_completion_at: Last completion timestamp
            - consistency_score: Completions per week
        """
        result = await self.backend.get_habit_analytics(user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "total_completions": 0,
                    "first_completion_at": None,
                    "last_completion_at": None,
                    "consistency_score": 0.0,
                }
            )

        analytics = record["analytics"]
        total_completions = analytics.get("total_completions", 0)

        # Calculate consistency score (completions per week)
        first_at = analytics.get("first_completion_at")
        last_at = analytics.get("last_completion_at")

        consistency = 0.0
        if first_at and last_at:
            days_active = (last_at - first_at).days or 1
            weeks_active = days_active / 7
            consistency = total_completions / weeks_active if weeks_active > 0 else 0.0

        return Result.ok(
            {
                "user_uid": user_uid,
                "total_completions": total_completions,
                "first_completion_at": first_at,
                "last_completion_at": last_at,
                "consistency_score": round(consistency, 2),
            }
        )

    async def get_combined_dashboard(
        self, user_uid: UserUID, days_back: int = 30
    ) -> Result[dict[str, Any]]:
        """Build a combined analytics dashboard from multiple sub-queries.

        Gathers learning velocity and mood analysis into a single response dict.
        (Spending patterns removed in ADR-052 Phase 5 — native expense module
        demolished.)

        Args:
            user_uid: User identifier
            days_back: Number of days to analyze

        Returns:
            Result with combined dashboard containing learning_velocity and
            mood_analysis (each None if unavailable)
        """
        learning_result = await self.get_learning_velocity(user_uid, days_back)
        mood_result = await self.get_mood_analysis(user_uid, days_back)

        dashboard: dict[str, Any] = {
            "user_uid": user_uid,
            "period_days": days_back,
            "generated_at": datetime.now().isoformat(),
            "learning_velocity": None,
            "mood_analysis": None,
        }

        if learning_result.is_ok:
            v = learning_result.value
            dashboard["learning_velocity"] = {
                "kus_mastered_per_week": v.kus_mastered_per_week,
                "paths_completed": v.paths_completed,
                "velocity_trend": v.velocity_trend,
            }

        if mood_result.is_ok:
            m = mood_result.value
            dashboard["mood_analysis"] = {
                "average_mood": m.average_mood,
                "mood_trend": m.mood_trend,
                "entries_per_week": m.entries_per_week,
            }

        return Result.ok(dashboard)
