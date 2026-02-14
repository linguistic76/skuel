"""
Habits Completion Tracking Service
===================================

Handles habit completion tracking with quality scores, notes, and analytics.

Responsibilities:
- Record habit completions with quality tracking
- Calculate completion statistics (today, week, month)
- Track streaks based on completions
- Badge progress tracking
- Export completion history

Version: 1.0.0
Date: 2025-10-14
"""

from datetime import date, datetime, timedelta
from typing import Any

from core.constants import QueryLimit
from core.events import publish_event
from core.models.habit.completion import HabitCompletion
from core.models.habit.completion_dto import HabitCompletionDTO
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_completed_at


class HabitsCompletionService:
    """
    Completion tracking service for habits.

    Handles all completion-related operations including:
    - Recording completions with quality/notes
    - Analytics (completed today, this week, etc.)
    - Streak calculation
    - Badge progress

    Architecture Note:
        This service intentionally does NOT extend BaseService.
        HabitCompletion is a "secondary entity" - it tracks user engagement
        with a primary entity (Habit). Secondary entities:
        - Are queried via their parent entity, not directly
        - Don't need CRUD route factories
        - Handle ownership via User relationship, not verify_ownership()
        - Have simpler lifecycle (create, query - rarely update)

        See: /docs/patterns/SECONDARY_ENTITY_PATTERN.md

    Source Tag: "habits_completion_service_explicit"
    - Format: "habits_completion_service_explicit" for user-created relationships
    - Format: "habits_completion_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from habits_completion metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    def __init__(
        self,
        habits_backend,  # UniversalNeo4jBackend[Habit]
        completions_backend,  # UniversalNeo4jBackend[HabitCompletion]
        event_bus=None,
    ) -> None:
        """
        Initialize habits completion service.

        Args:
            habits_backend: Backend for habit CRUD operations,
            completions_backend: Backend for completion CRUD operations,
            event_bus: Event bus for publishing domain events (optional)
        """
        if not habits_backend:
            raise ValueError("habits_backend is required")
        if not completions_backend:
            raise ValueError("completions_backend is required")

        self.habits_backend = habits_backend
        self.completions_backend = completions_backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.habits.completion")

    # ========================================================================
    # COMPLETION TRACKING
    # ========================================================================

    async def record_completion(
        self,
        habit_uid: str,
        user_uid: str,
        completed_at: datetime | None = None,
        quality: int | None = None,
        duration_actual: int | None = None,
        notes: str | None = None,
    ) -> Result[HabitCompletion]:
        """
        Record a habit completion.

        Args:
            habit_uid: UID of habit completed,
            user_uid: User who completed the habit,
            completed_at: When habit was completed (default: now),
            quality: Quality rating 1-5 (optional),
            duration_actual: Actual duration in minutes (optional),
            notes: Completion notes (optional)

        Returns:
            Result[HabitCompletion] with the created completion record
        """
        self.logger.info(f"Recording completion for habit {habit_uid}")

        # Validate habit exists
        habit_result = await self.habits_backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        # Create completion record
        now = datetime.now()
        completion_uid = f"hc.{user_uid}.{habit_uid}.{int(now.timestamp())}"

        completion_dto = HabitCompletionDTO(
            uid=completion_uid,
            habit_uid=habit_uid,
            completed_at=completed_at or now,
            quality=quality,
            duration_actual=duration_actual,
            notes=notes,
            created_at=now,
            updated_at=now,
        )

        # Store completion
        create_result = await self.completions_backend.create(completion_dto)
        if create_result.is_error:
            return create_result

        # Convert to domain model
        completion = HabitCompletion.from_dto(completion_dto)

        # Update habit statistics (fail-fast: stats must succeed)
        stats_result = await self._update_habit_stats(habit_uid, completion)
        if stats_result.is_error:
            return Result.fail(stats_result.expect_error())

        self.logger.info(f"✅ Recorded completion {completion_uid}")
        return Result.ok(completion)

    async def record_completions_bulk(
        self,
        habit_uids: list[str],
        user_uid: str,
        completed_at: datetime | None = None,
    ) -> Result[list[HabitCompletion]]:
        """
        Record completions for multiple habits in a batch operation.

        More efficient than calling record_completion N times:
        - Single HabitCompletionBulk event vs N HabitCompleted events

        Args:
            habit_uids: List of habit UIDs to complete
            user_uid: User completing the habits
            completed_at: When habits were completed (default: now)

        Returns:
            Result[list[HabitCompletion]] with all created completion records
        """
        if not habit_uids:
            return Result.ok([])

        self.logger.info(f"Recording bulk completions for {len(habit_uids)} habits")

        completions: list[HabitCompletion] = []
        new_streak_records: list[str] = []
        milestones_reached: list[tuple[str, int]] = []
        now = completed_at or datetime.now()

        for habit_uid in habit_uids:
            # Record each completion (without individual events)
            result = await self._record_completion_no_event(habit_uid, user_uid, now)
            if result.is_ok:
                completion, is_new_record, milestone = result.value
                completions.append(completion)
                if is_new_record:
                    new_streak_records.append(habit_uid)
                if milestone:
                    milestones_reached.append(milestone)

        # Publish single bulk event for all completions
        if completions:
            from core.events.habit_events import HabitCompletionBulk

            event = HabitCompletionBulk(
                habit_uids=tuple(c.habit_uid for c in completions),
                user_uid=user_uid,
                occurred_at=now,
                new_streak_records=tuple(new_streak_records),
                milestones_reached=tuple(milestones_reached),
            )
            await publish_event(self.event_bus, event, self.logger)
            self.logger.info(
                f"✅ Bulk completed {len(completions)} habits "
                f"({len(new_streak_records)} new records, {len(milestones_reached)} milestones)"
            )

        return Result.ok(completions)

    async def _record_completion_no_event(
        self,
        habit_uid: str,
        user_uid: str,
        completed_at: datetime,
    ) -> Result[tuple[HabitCompletion, bool, tuple[str, int] | None]]:
        """
        Record a completion without publishing individual events.

        Used by record_completions_bulk for batch processing.

        Returns:
            Result containing (completion, is_new_streak_record, milestone_or_none)
        """
        # Validate habit exists
        habit_result = await self.habits_backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        habit = habit_result.value

        # Create completion record
        completion_uid = f"hc.{user_uid}.{habit_uid}.{int(completed_at.timestamp())}"
        now = datetime.now()

        completion_dto = HabitCompletionDTO(
            uid=completion_uid,
            habit_uid=habit_uid,
            completed_at=completed_at,
            quality=None,
            duration_actual=None,
            notes=None,
            created_at=now,
            updated_at=now,
        )

        # Store completion
        create_result = await self.completions_backend.create(completion_dto)
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        completion = HabitCompletion.from_dto(completion_dto)

        # Calculate new streak
        new_streak = self._calculate_new_streak(habit, completed_at)
        is_new_record = new_streak > habit.best_streak

        # Check for milestone (names used by _publish_milestone_event_if_reached)
        milestone: tuple[str, int] | None = None
        milestone_values = {7, 30, 100, 365}  # one_week, one_month, one_hundred, one_year
        if new_streak in milestone_values and habit.current_streak < new_streak:
            milestone = (habit_uid, new_streak)

        # Update habit statistics
        updates = {
            "current_streak": new_streak,
            "best_streak": max(new_streak, habit.best_streak),
            "total_completions": habit.total_completions + 1,
            "last_completed": completed_at,
            "updated_at": now,
        }
        if habit.is_identity_based():
            updates["identity_votes_cast"] = habit.identity_votes_cast + 1

        await self.habits_backend.update(habit_uid, updates)

        return Result.ok((completion, is_new_record, milestone))

    @with_error_handling("update_habit_stats", error_type="database", uid_param="habit_uid")
    async def _update_habit_stats(
        self, habit_uid: str, completion: HabitCompletion
    ) -> Result[None]:
        """Update habit statistics after completion."""
        # Get current habit
        habit_result = await self.habits_backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        # Backend returns Result[Habit | None] - trust the type system
        habit = habit_result.value

        # Calculate new streak
        new_streak = self._calculate_new_streak(habit, completion.completed_at)

        # Check for streak milestones and publish events
        await self._check_streak_milestones(habit, new_streak, habit.user_uid)

        # Update habit
        updates = {
            "current_streak": new_streak,
            "best_streak": max(new_streak, habit.best_streak),
            "total_completions": habit.total_completions + 1,
            "last_completed": completion.completed_at,
            "updated_at": datetime.now(),
        }

        # Update identity votes if applicable
        if habit.is_identity_based():
            updates["identity_votes_cast"] = habit.identity_votes_cast + 1

        update_result = await self.habits_backend.update(habit_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        self.logger.debug(f"Updated habit {habit_uid} stats: streak={new_streak}")
        return Result.ok(None)

    def _calculate_new_streak(self, habit: Ku, completion_date: datetime) -> int:
        """Calculate new streak based on last completion."""
        if not habit.last_completed:
            return 1  # First completion

        days_since = (completion_date.date() - habit.last_completed.date()).days

        if days_since == 0:
            # Same day completion
            return habit.current_streak
        elif days_since == 1:
            # Consecutive day
            return habit.current_streak + 1
        else:
            # Streak broken
            return 1

    async def _check_streak_milestones(self, habit: Ku, new_streak: int, user_uid: str) -> None:
        """
        Check if new streak reaches a milestone and publish event.

        Milestones: 7 (one week), 30 (one month), 100 (one hundred), 365 (one year)
        """
        # Define milestones with their names
        milestones = {
            7: "one_week",
            30: "one_month",
            100: "one_hundred",
            365: "one_year",
        }

        old_streak = habit.current_streak

        # Check if new streak exactly matches a milestone (and we just reached it)
        for milestone_value, milestone_name in milestones.items():
            if new_streak == milestone_value and old_streak < milestone_value:
                # Milestone reached! Publish event
                from core.events.habit_events import HabitStreakMilestone

                event = HabitStreakMilestone(
                    habit_uid=habit.uid,
                    user_uid=user_uid,
                    streak_length=new_streak,
                    milestone_name=milestone_name,
                    occurred_at=datetime.now(),
                )
                await publish_event(self.event_bus, event, self.logger)

    # ========================================================================
    # COMPLETION QUERIES
    # ========================================================================

    async def get_completions_for_habit(
        self,
        habit_uid: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> Result[list[HabitCompletion]]:
        """Get all completions for a habit within date range."""
        self.logger.debug(f"Getting completions for habit {habit_uid}")

        # Build filters
        filters = {"habit_uid": habit_uid}
        if start_date:
            filters["completed_at__gte"] = datetime.combine(start_date, datetime.min.time())
        if end_date:
            filters["completed_at__lte"] = datetime.combine(end_date, datetime.max.time())

        # Query completions
        result = await self.completions_backend.find_by(**filters, limit=limit)
        if result.is_error:
            return result

        # Convert to domain models
        completions = []
        for item in result.value:
            if isinstance(item, dict):
                dto = HabitCompletionDTO.from_dict(item)
                completions.append(HabitCompletion.from_dto(dto))
            elif isinstance(item, HabitCompletionDTO):
                completions.append(HabitCompletion.from_dto(item))
            else:
                completions.append(item)

        # Sort by completion date (most recent first)
        completions.sort(key=get_completed_at, reverse=True)

        return Result.ok(completions)

    async def get_today_completions(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get all habit completions for today for a user.

        Args:
            user_uid: User identifier

        Returns list of dicts with habit details + completion info.
        """
        today = date.today()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())

        # Get user's completions for today
        completions_result = await self.completions_backend.find_by(
            user_uid=user_uid,
            completed_at__gte=start_of_day,
            completed_at__lte=end_of_day,
            limit=QueryLimit.COMPREHENSIVE,
        )

        if completions_result.is_error:
            return completions_result

        # Group completions by habit
        habit_completions = {}
        for item in completions_result.value:
            if isinstance(item, dict):
                dto = HabitCompletionDTO.from_dict(item)
                completion = HabitCompletion.from_dto(dto)
            elif isinstance(item, HabitCompletionDTO):
                completion = HabitCompletion.from_dto(item)
            else:
                completion = item

            habit_uid = completion.habit_uid
            if habit_uid not in habit_completions:
                habit_completions[habit_uid] = []
            habit_completions[habit_uid].append(completion)

        # Get habit details and create response
        result = []
        for habit_uid, completions in habit_completions.items():
            habit_result = await self.habits_backend.get(habit_uid)
            if habit_result.is_ok:
                # Backend returns Result[Habit | None] - trust the type system
                habit = habit_result.value

                result.append(
                    {
                        "habit": habit,
                        "completions_today": len(completions),
                        "latest_completion": completions[0],  # Most recent
                        "total_quality_today": sum(c.quality or 0 for c in completions),
                        "completed": True,
                    }
                )

        return Result.ok(result)

    async def calculate_completed_today_count(self, user_uid: str) -> Result[int]:
        """Calculate how many habits user completed today.

        Args:
            user_uid: User identifier
        """
        today_result = await self.get_today_completions(user_uid)
        if today_result.is_error:
            return Result.fail(today_result.expect_error())

        return Result.ok(len(today_result.value))

    # ========================================================================
    # ANALYTICS
    # ========================================================================

    async def get_completion_stats(self, habit_uid: str, days: int = 30) -> Result[dict[str, Any]]:
        """Get completion statistics for a habit over a period."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        completions_result = await self.get_completions_for_habit(
            habit_uid, start_date=start_date, end_date=end_date
        )

        if completions_result.is_error:
            return Result.fail(completions_result.expect_error())

        completions = completions_result.value

        # Calculate statistics
        stats = {
            "habit_uid": habit_uid,
            "period_days": days,
            "total_completions": len(completions),
            "completion_rate": len(completions) / days if days > 0 else 0,
            "average_quality": sum(c.quality or 0 for c in completions) / len(completions)
            if completions and any(c.quality for c in completions)
            else None,
            "high_quality_count": sum(1 for c in completions if c.is_high_quality()),
            "excellent_quality_count": sum(1 for c in completions if c.is_excellent_quality()),
            "completion_dates": [c.completed_at.date().isoformat() for c in completions],
            "notes_count": sum(1 for c in completions if c.has_meaningful_notes()),
        }

        return Result.ok(stats)

    async def get_badge_progress(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Calculate badge progress based on completion data.

        Args:
            user_uid: User identifier

        Badges include:
        - Streak badges (7, 30, 100, 365 days)
        - Completion badges (10, 50, 100, 500 habits)
        - Quality badges (100 high-quality completions)
        - Identity badges (50 identity votes cast)
        """
        # Get user's habits
        habits_result = await self.habits_backend.find_by(
            user_uid=user_uid, limit=QueryLimit.COMPREHENSIVE
        )
        if habits_result.is_error:
            return habits_result

        # Calculate badge progress
        max_streak = 0
        total_completions = 0
        total_identity_votes = 0
        high_quality_completions = 0

        for item in habits_result.value:
            if isinstance(item, dict):
                habit_dto = KuDTO.from_dict(item)
                habit = Ku.from_dto(habit_dto)
            else:
                habit = item

            max_streak = max(max_streak, habit.current_streak)
            total_completions += habit.total_completions

            if habit.is_identity_based():
                total_identity_votes += habit.identity_votes_cast

        # Get user's high-quality completions (last 1000)
        all_completions_result = await self.completions_backend.find_by(
            user_uid=user_uid, limit=QueryLimit.COMPREHENSIVE
        )
        if all_completions_result.is_ok:
            for item in all_completions_result.value:
                if isinstance(item, dict):
                    dto = HabitCompletionDTO.from_dict(item)
                    completion = HabitCompletion.from_dto(dto)
                else:
                    completion = item

                if completion.is_high_quality():
                    high_quality_completions += 1

        badge_progress = {
            "streaks": {
                "current_max_streak": max_streak,
                "week_warrior": {"unlocked": max_streak >= 7, "progress": min(max_streak / 7, 1.0)},
                "month_master": {
                    "unlocked": max_streak >= 30,
                    "progress": min(max_streak / 30, 1.0),
                },
                "century_champion": {
                    "unlocked": max_streak >= 100,
                    "progress": min(max_streak / 100, 1.0),
                },
                "year_legend": {
                    "unlocked": max_streak >= 365,
                    "progress": min(max_streak / 365, 1.0),
                },
            },
            "completions": {
                "total_completions": total_completions,
                "getting_started": {
                    "unlocked": total_completions >= 10,
                    "progress": min(total_completions / 10, 1.0),
                },
                "habit_builder": {
                    "unlocked": total_completions >= 50,
                    "progress": min(total_completions / 50, 1.0),
                },
                "century_club": {
                    "unlocked": total_completions >= 100,
                    "progress": min(total_completions / 100, 1.0),
                },
                "habit_master": {
                    "unlocked": total_completions >= 500,
                    "progress": min(total_completions / 500, 1.0),
                },
            },
            "quality": {
                "high_quality_count": high_quality_completions,
                "quality_focused": {
                    "unlocked": high_quality_completions >= 100,
                    "progress": min(high_quality_completions / 100, 1.0),
                },
            },
            "identity": {
                "total_identity_votes": total_identity_votes,
                "identity_seeker": {
                    "unlocked": total_identity_votes >= 50,
                    "progress": min(total_identity_votes / 50, 1.0),
                },
            },
        }

        return Result.ok(badge_progress)

    # ========================================================================
    # EXPORT
    # ========================================================================

    async def export_completion_history(
        self,
        user_uid: str,
        start_date: date | None = None,
        end_date: date | None = None,
        format: str = "csv",
    ) -> Result[str]:
        """
        Export completion history for a user.

        Args:
            user_uid: User to export for
            start_date: Start date filter (optional)
            end_date: End date filter (optional)
            format: Export format ("csv" or "json")

        Returns:
            Result[str] with exported data as string
        """
        # Build filters with user_uid
        filters = {"user_uid": user_uid}
        if start_date:
            filters["completed_at__gte"] = datetime.combine(start_date, datetime.min.time())
        if end_date:
            filters["completed_at__lte"] = datetime.combine(end_date, datetime.max.time())

        # Get user's completions
        completions_result = await self.completions_backend.find_by(
            **filters, limit=QueryLimit.BULK
        )
        if completions_result.is_error:
            return completions_result

        completions = []
        for item in completions_result.value:
            if isinstance(item, dict):
                dto = HabitCompletionDTO.from_dict(item)
                completions.append(HabitCompletion.from_dto(dto))
            else:
                completions.append(item)

        # Sort by date
        completions.sort(key=get_completed_at)

        if format == "csv":
            return self._export_csv(completions)
        elif format == "json":
            return self._export_json(completions)
        else:
            return Result.fail(
                Errors.validation(
                    message=f"Unsupported export format: {format}", field="format", value=format
                )
            )

    def _export_csv(self, completions: list[HabitCompletion]) -> Result[str]:
        """Export completions as CSV."""
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "Completion ID",
                "Habit ID",
                "Completed At",
                "Quality",
                "Duration (min)",
                "Notes",
                "Created At",
            ]
        )

        # Write rows
        for c in completions:
            writer.writerow(
                [
                    c.uid,
                    c.habit_uid,
                    c.completed_at.isoformat(),
                    c.quality or "",
                    c.duration_actual or "",
                    c.notes or "",
                    c.created_at.isoformat(),
                ]
            )

        return Result.ok(output.getvalue())

    def _export_json(self, completions: list[HabitCompletion]) -> Result[str]:
        """Export completions as JSON."""
        import json

        data = [
            {
                "uid": c.uid,
                "habit_uid": c.habit_uid,
                "completed_at": c.completed_at.isoformat(),
                "quality": c.quality,
                "duration_actual": c.duration_actual,
                "notes": c.notes,
                "created_at": c.created_at.isoformat(),
            }
            for c in completions
        ]

        return Result.ok(json.dumps(data, indent=2))
