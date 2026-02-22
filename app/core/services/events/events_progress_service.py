"""
Events Progress Service - Progress Tracking and Completion
==========================================================

Handles event completion, attendance tracking, and quality metrics.

**Responsibilities:**
- Track event attendance/completion rates
- Event quality score tracking for habit events
- Event-to-goal contribution metrics
- Weekly/monthly trend analysis

**Pattern:**
Similar to TasksProgressService but focused on event-specific metrics.
Events are calendar-based (not goal-based like tasks), so progress tracking
focuses on attendance and quality rather than goal contribution.
"""

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.events import CalendarEventCompleted, publish_event
from core.models.enums import EntityStatus
from core.models.ku.event import Event
from core.models.ku.ku_dto import KuDTO
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import BackendOperations


class EventsProgressService(BaseService["BackendOperations[Event]", Event]):
    """
    Progress tracking and completion for events.

    Tracks:
    - Attendance rates (completed vs. scheduled events)
    - Quality scores for habit-reinforcing events
    - Goal contribution metrics
    - Weekly/monthly trend analysis

    Source Tag: "events_progress_service_explicit"

    SKUEL Architecture:
    - Uses CypherGenerator for graph queries
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=KuDTO,
        model_class=Event,
        entity_label="Ku",
        domain_name="events",
        date_field="event_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    # Configure BaseService
    _date_field = "event_date"
    _completed_statuses = (EntityStatus.COMPLETED.value, EntityStatus.CANCELLED.value)

    def __init__(self, backend: "BackendOperations[Event]", event_bus=None) -> None:
        """
        Initialize progress service.

        Args:
            backend: Protocol-based backend for event operations
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation happens via event-driven architecture.
            CalendarEventCompleted events trigger context updates.
        """
        super().__init__(backend, "events.progress")
        self.event_bus = event_bus

    @property
    def entity_label(self) -> str:
        """Return the graph label for Ku entities."""
        return "Ku"

    # ========================================================================
    # CONTEXT-FIRST HELPERS
    # ========================================================================

    def _get_event_from_rich_context(
        self, event_uid: str, user_context: UserContext
    ) -> Event | None:
        """Try to get Ku from UserContext.active_events_rich."""
        if not user_context.active_events_rich:
            return None

        for event_data in user_context.active_events_rich:
            event_dict = event_data.get("event", {})
            if event_dict.get("uid") == event_uid:
                return self._dict_to_event(event_dict)
        return None

    def _dict_to_event(self, event_dict: dict[str, Any]) -> Event | None:
        """Convert raw Neo4j dict to Event domain model."""
        if not event_dict or not event_dict.get("uid"):
            return None
        dto = KuDTO.from_dict(event_dict)
        return Event.from_dto(dto)

    # ========================================================================
    # EVENT COMPLETION
    # ========================================================================

    @with_error_handling(
        "complete_event_with_cascade", error_type="database", uid_param="event_uid"
    )
    async def complete_event_with_cascade(
        self,
        event_uid: str,
        user_context: UserContext,
        quality_score: int | None = None,
        notes: str | None = None,
    ) -> Result[Event]:
        """
        Complete an event and cascade updates through the system.

        This method:
        1. Marks event as complete
        2. Updates quality score if provided (for habit events)
        3. Publishes CalendarEventCompleted event for cascade effects

        Context-First: Tries rich context before Neo4j query.

        Args:
            event_uid: Event UID
            user_context: User context for cascade effects
            quality_score: Optional quality rating (1-5) for habit events
            notes: Optional completion notes

        Returns:
            Result containing completed event
        """
        # CONTEXT-FIRST: Try rich context
        event = self._get_event_from_rich_context(event_uid, user_context)

        if event is None:
            event_result = await self.backend.get(event_uid)
            if event_result.is_error:
                return Result.fail(event_result.expect_error())
            if not event_result.value:
                return Result.fail(Errors.not_found(resource="Event", identifier=event_uid))
            event = self._to_domain_model(event_result.value, KuDTO, Event)
            self.logger.debug(f"Event {event_uid} fetched from Neo4j")
        else:
            self.logger.debug(f"Event {event_uid} found in rich context")

        # Build updates
        updates: dict[str, Any] = {
            "status": EntityStatus.COMPLETED.value,
            "completed_at": datetime.now().isoformat(),
        }
        if quality_score is not None:
            updates["habit_completion_quality"] = quality_score
        if notes:
            updates["notes"] = notes

        # Update event
        update_result = await self.backend.update(event_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        # Publish CalendarEventCompleted event
        domain_event = CalendarEventCompleted(
            event_uid=event_uid,
            user_uid=user_context.user_uid,
            completion_date=event.event_date,
            quality_score=quality_score,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, domain_event, self.logger)

        self.logger.info(
            f"Completed event {event_uid}: "
            f"habit={event.reinforces_habit_uid}, quality={quality_score}"
        )

        completed_event = self._to_domain_model(update_result.value, KuDTO, Event)
        return Result.ok(completed_event)

    # ========================================================================
    # ATTENDANCE TRACKING
    # ========================================================================

    @with_error_handling("get_attendance_rate", error_type="database", uid_param="user_uid")
    async def get_attendance_rate(
        self,
        user_uid: str,
        period_days: int = 30,
    ) -> Result[dict[str, Any]]:
        """
        Calculate event attendance rate for a user.

        Attendance = completed events / total scheduled events (excluding cancelled)

        Args:
            user_uid: User identifier
            period_days: Period to analyze (default 30 days)

        Returns:
            Result containing attendance metrics dict
        """
        start_date = date.today() - timedelta(days=period_days)
        today = date.today()

        # Get all events in period
        result = await self.backend.find_by(
            user_uid=user_uid,
            event_date__gte=start_date.isoformat(),
            event_date__lte=today.isoformat(),
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        events = result.value or []

        # Calculate metrics
        total_scheduled = len([e for e in events if e.status != EntityStatus.CANCELLED.value])
        completed = len([e for e in events if e.status == EntityStatus.COMPLETED.value])
        missed = len(
            [
                e
                for e in events
                if e.event_date
                and e.event_date < today
                and e.status not in (EntityStatus.COMPLETED.value, EntityStatus.CANCELLED.value)
            ]
        )

        attendance_rate = completed / total_scheduled if total_scheduled > 0 else 0.0

        self.logger.debug(
            f"Attendance rate for {user_uid}: {attendance_rate:.1%} "
            f"({completed}/{total_scheduled} completed)"
        )

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_scheduled": total_scheduled,
                "completed": completed,
                "missed": missed,
                "attendance_rate": round(attendance_rate, 3),
                "attendance_percentage": round(attendance_rate * 100, 1),
            }
        )

    @with_error_handling("get_quality_trends", error_type="database", uid_param="user_uid")
    async def get_quality_trends(
        self,
        user_uid: str,
        period_days: int = 30,
    ) -> Result[dict[str, Any]]:
        """
        Track quality score trends for habit-reinforcing events.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing quality trend metrics
        """
        start_date = date.today() - timedelta(days=period_days)

        result = await self.backend.find_by(
            user_uid=user_uid,
            event_date__gte=start_date.isoformat(),
            status=EntityStatus.COMPLETED.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        events = result.value or []

        # Filter to events with quality scores
        quality_events = [e for e in events if e.habit_completion_quality is not None]

        if not quality_events:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "period_days": period_days,
                    "events_with_quality": 0,
                    "average_quality": None,
                    "quality_trend": "insufficient_data",
                }
            )

        # Calculate average and trend
        scores = [e.habit_completion_quality for e in quality_events]
        avg_quality = sum(scores) / len(scores)

        # Simple trend: compare first half vs second half
        mid = len(scores) // 2
        if mid > 0:
            first_half_avg = sum(scores[:mid]) / mid
            second_half_avg = sum(scores[mid:]) / (len(scores) - mid)
            if second_half_avg > first_half_avg + 0.2:
                trend = "improving"
            elif second_half_avg < first_half_avg - 0.2:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "events_with_quality": len(quality_events),
                "average_quality": round(avg_quality, 2),
                "min_quality": min(scores),
                "max_quality": max(scores),
                "quality_trend": trend,
            }
        )

    @with_error_handling(
        "get_goal_contribution_metrics", error_type="database", uid_param="user_uid"
    )
    async def get_goal_contribution_metrics(
        self,
        user_uid: str,
        period_days: int = 30,
    ) -> Result[dict[str, Any]]:
        """
        Calculate how events contribute to goal progress.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing goal contribution metrics
        """
        start_date = date.today() - timedelta(days=period_days)

        result = await self.backend.find_by(
            user_uid=user_uid,
            event_date__gte=start_date.isoformat(),
            status=EntityStatus.COMPLETED.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        events = result.value or []

        # Count events with goal milestones
        milestone_events = [e for e in events if e.milestone_celebration_for_goal]

        total_completed = len(events)
        contribution_rate = len(milestone_events) / total_completed if total_completed > 0 else 0.0

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_completed_events": total_completed,
                "goal_milestone_events": len(milestone_events),
                "goal_contribution_rate": round(contribution_rate, 3),
                "goals_with_milestones": list(
                    set(
                        e.milestone_celebration_for_goal
                        for e in milestone_events
                        if e.milestone_celebration_for_goal
                    )
                ),
            }
        )

    @with_error_handling("get_weekly_summary", error_type="database", uid_param="user_uid")
    async def get_weekly_summary(
        self,
        user_uid: str,
        weeks_back: int = 4,
    ) -> Result[dict[str, Any]]:
        """
        Get weekly event summary for trend visualization.

        Args:
            user_uid: User identifier
            weeks_back: Number of weeks to analyze

        Returns:
            Result containing weekly breakdown
        """
        today = date.today()
        start_date = today - timedelta(weeks=weeks_back)

        result = await self.backend.find_by(
            user_uid=user_uid,
            event_date__gte=start_date.isoformat(),
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        events = result.value or []

        # Group by week
        weeks: dict[str, dict[str, int]] = {}
        for event in events:
            if not event.event_date:
                continue
            # Get week start (Monday)
            week_start = event.event_date - timedelta(days=event.event_date.weekday())
            week_key = week_start.isoformat()

            if week_key not in weeks:
                weeks[week_key] = {"scheduled": 0, "completed": 0, "cancelled": 0, "missed": 0}

            if event.status == EntityStatus.COMPLETED.value:
                weeks[week_key]["completed"] += 1
            elif event.status == EntityStatus.CANCELLED.value:
                weeks[week_key]["cancelled"] += 1
            elif event.event_date < today:
                weeks[week_key]["missed"] += 1
            else:
                weeks[week_key]["scheduled"] += 1

        return Result.ok(
            {
                "user_uid": user_uid,
                "weeks_analyzed": weeks_back,
                "weekly_breakdown": weeks,
                "total_events": len(events),
            }
        )

    @with_error_handling("get_habit_event_stats", error_type="database", uid_param="user_uid")
    async def get_habit_event_stats(
        self,
        user_uid: str,
        period_days: int = 30,
    ) -> Result[dict[str, Any]]:
        """
        Get statistics for habit-reinforcing events.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing habit event statistics
        """
        start_date = date.today() - timedelta(days=period_days)

        result = await self.backend.find_by(
            user_uid=user_uid,
            event_date__gte=start_date.isoformat(),
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        events = result.value or []

        # Filter habit events (exclude None habit_uid)
        habit_events = [e for e in events if e.reinforces_habit_uid is not None]

        # Group by habit
        by_habit: dict[str, dict[str, int]] = {}
        for event in habit_events:
            habit_uid = event.reinforces_habit_uid
            # Type narrowing: we already filtered for non-None above
            assert habit_uid is not None
            if habit_uid not in by_habit:
                by_habit[habit_uid] = {
                    "total": 0,
                    "completed": 0,
                    "quality_sum": 0,
                    "quality_count": 0,
                }

            by_habit[habit_uid]["total"] += 1
            if event.status == EntityStatus.COMPLETED.value:
                by_habit[habit_uid]["completed"] += 1
                if event.habit_completion_quality:
                    by_habit[habit_uid]["quality_sum"] += event.habit_completion_quality
                    by_habit[habit_uid]["quality_count"] += 1

        # Calculate averages
        habit_stats = {}
        for habit_uid, stats in by_habit.items():
            habit_stats[habit_uid] = {
                "total_events": stats["total"],
                "completed_events": stats["completed"],
                "completion_rate": round(stats["completed"] / stats["total"], 3)
                if stats["total"] > 0
                else 0.0,
                "average_quality": round(stats["quality_sum"] / stats["quality_count"], 2)
                if stats["quality_count"] > 0
                else None,
            }

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_habit_events": len(habit_events),
                "habits_tracked": len(by_habit),
                "by_habit": habit_stats,
            }
        )
