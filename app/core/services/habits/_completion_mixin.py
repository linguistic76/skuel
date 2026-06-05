"""
Completion Mixin — HabitsService
=================================

Completion tracking, status lifecycle, and reminder configuration.

Part of habits_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit_update_intent import HabitUpdateIntent
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.habit.habit_request import (
        ArchiveHabitRequest,
        DeleteHabitReminderRequest,
        PauseHabitRequest,
        ResumeHabitRequest,
        SetHabitReminderRequest,
        TrackHabitRequest,
        UntrackHabitRequest,
    )


class _CompletionMixin:
    """
    Completion tracking, status lifecycle, and reminder configuration for HabitsService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by HabitsService.__init__
    core: Any
    completions: Any
    logger: Any

    # ========================================================================
    # COMPLETION TRACKING - Delegate to HabitsCompletionService
    # ========================================================================

    async def track_habit(
        self,
        request: TrackHabitRequest,
    ) -> Result[HabitCompletion]:
        """
        Track/record a habit completion using typed request object.

        Args:
            request: TrackHabitRequest containing habit_uid, completion_date, value, notes

        Returns:
            Result with the completion record
        """
        # Parse date - default to now if not provided (explicit at boundary)
        if request.completion_date:
            if isinstance(request.completion_date, str):
                completed_at = datetime.fromisoformat(request.completion_date)
            elif isinstance(request.completion_date, date):
                completed_at = datetime.combine(request.completion_date, datetime.min.time())
            else:
                completed_at = datetime.now()
        else:
            # Explicit default at boundary - caller decides "now"
            completed_at = datetime.now()

        # Get habit to find user_uid
        habit_result = await self.core.get_habit(request.habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result)

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found(resource="Habit", identifier=request.habit_uid))

        return await self.completions.record_completion(
            habit_uid=request.habit_uid,
            user_uid=habit.user_uid,
            completed_at=completed_at,  # Always explicit datetime now
            quality=request.value,
            notes=request.notes or "",
        )

    async def untrack_habit(self, request: UntrackHabitRequest) -> Result[bool]:
        """
        Remove a habit tracking entry using typed request object.

        Args:
            request: UntrackHabitRequest containing habit_uid and completion_date

        Returns:
            Result[bool] indicating success
        """
        # Parse date
        target_date = date.today()
        if request.completion_date:
            if isinstance(request.completion_date, str):
                target_date = date.fromisoformat(request.completion_date)
            elif isinstance(request.completion_date, date):
                target_date = request.completion_date

        # Get completions for the date
        completions_result = await self.completions.get_completions_for_habit(
            request.habit_uid, start_date=target_date, end_date=target_date
        )
        if completions_result.is_error:
            return Result.fail(completions_result)

        completions = completions_result.value
        if not completions:
            return Result.fail(
                Errors.not_found(
                    resource="HabitCompletion", identifier=f"{request.habit_uid} on {target_date}"
                )
            )

        # Delete the completion(s) for that date
        # Note: Using backend directly as completions service may not have delete
        for completion in completions:
            await self.completions.completions_backend.delete(completion.uid)

        return Result.ok(True)

    async def get_habit_streak(self, habit_uid: str) -> Result[dict[str, Any]]:
        """
        Get current streak information for a habit.

        Args:
            habit_uid: UID of the habit

        Returns:
            Result with streak data including current_streak, longest_streak
        """
        # Get habit for streak data
        habit_result = await self.core.get_habit(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result)

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        streak_data = {
            "habit_uid": habit_uid,
            "current_streak": habit.current_streak or 0,
            "longest_streak": habit.best_streak or 0,
            "last_completed": habit.last_completed.isoformat() if habit.last_completed else None,
        }

        return Result.ok(streak_data)

    async def get_habit_progress(
        self, habit_uid: str, period: str = "month"
    ) -> Result[dict[str, Any]]:
        """
        Get progress statistics for a habit over a period.

        Args:
            habit_uid: UID of the habit
            period: Time period - "week", "month", or "year"

        Returns:
            Result with progress statistics
        """
        # Map period to days
        period_days = {"week": 7, "month": 30, "year": 365}.get(period, 30)
        return await self.completions.get_completion_stats(habit_uid, days=period_days)

    async def get_habit_history(
        self, habit_uid: str, days: int = 90
    ) -> Result[list[dict[str, Any]]]:
        """
        Get completion history for a habit.

        Args:
            habit_uid: UID of the habit
            days: Number of days of history to retrieve (default: 90)

        Returns:
            Result with list of completion records
        """
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get completions from completions service
        result = await self.completions.get_completions_for_habit(
            habit_uid, start_date=start_date, end_date=end_date
        )

        if result.is_error:
            return Result.fail(result)

        completions = result.value or []

        # Convert to simple dict format for API response
        history = [
            {
                "uid": c.uid,
                "completed_at": c.completed_at.isoformat() if c.completed_at else None,
                "quality": c.quality,
                "notes": c.notes,
            }
            for c in completions
        ]

        return Result.ok(history)

    async def get_completion_calendar(
        self, habit_uid: str, year: int | None = None, month: int | None = None
    ) -> Result[dict[str, Any]]:
        """
        Get completion data formatted for calendar visualization.

        Args:
            habit_uid: UID of the habit
            year: Year to get data for (default: current year)
            month: Month to get data for (default: current month)

        Returns:
            Result with calendar data including:
            - dates: dict mapping date strings to completion status
            - summary: completion statistics for the period
        """
        # Default to current month
        today = date.today()
        target_year = year or today.year
        target_month = month or today.month

        # Calculate date range for the month
        start_date = date(target_year, target_month, 1)
        # Get last day of month
        if target_month == 12:
            end_date = date(target_year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(target_year, target_month + 1, 1) - timedelta(days=1)

        # Get completions for the month
        result = await self.completions.get_completions_for_habit(
            habit_uid, start_date=start_date, end_date=end_date
        )

        if result.is_error:
            return Result.fail(result)

        completions = result.value or []

        # Build calendar data: map dates to completion info
        dates: dict[str, dict[str, Any]] = {}
        for c in completions:
            if c.completed_at:
                date_str = c.completed_at.date().isoformat()
                dates[date_str] = {
                    "completed": True,
                    "quality": c.quality,
                    "notes": c.notes,
                }

        # Calculate summary stats
        days_in_month = (end_date - start_date).days + 1
        completed_days = len(dates)

        calendar_data = {
            "habit_uid": habit_uid,
            "year": target_year,
            "month": target_month,
            "dates": dates,
            "summary": {
                "days_in_month": days_in_month,
                "completed_days": completed_days,
                "completion_rate": round(completed_days / days_in_month * 100, 1),
            },
        }

        return Result.ok(calendar_data)

    # ========================================================================
    # STATUS MANAGEMENT
    # ========================================================================

    async def pause_habit(self, request: PauseHabitRequest) -> Result[Any]:
        """
        Pause a habit temporarily using typed request object.

        Args:
            request: PauseHabitRequest containing habit_uid, reason, until_date

        Returns:
            Result with the updated habit
        """
        # ``reason`` / ``paused_until`` are not Habit columns (the prior funnel dropped
        # them); only the status transition is persisted.
        return await self.core.update_habit(
            request.habit_uid, HabitUpdateIntent(status=EntityStatus.PAUSED.value)
        )

    async def resume_habit(self, request: ResumeHabitRequest) -> Result[Any]:
        """
        Resume a paused habit using typed request object.

        Args:
            request: ResumeHabitRequest containing habit_uid

        Returns:
            Result with the updated habit
        """
        # ``paused_until`` is not a Habit column (the prior funnel dropped it); only the
        # status transition is persisted.
        return await self.core.update_habit(
            request.habit_uid, HabitUpdateIntent(status=EntityStatus.ACTIVE.value)
        )

    async def archive_habit(self, request: ArchiveHabitRequest) -> Result[Any]:
        """
        Archive a completed or discontinued habit using typed request object.

        Args:
            request: ArchiveHabitRequest containing habit_uid, reason

        Returns:
            Result with the updated habit
        """
        # ``reason`` is not a Habit column (the prior funnel dropped it); only the status
        # transition is persisted.
        return await self.core.update_habit(
            request.habit_uid, HabitUpdateIntent(status=EntityStatus.ARCHIVED.value)
        )

    # ========================================================================
    # REMINDERS
    # ========================================================================
    # Reminder configuration is stored directly on the Habit model.

    async def set_habit_reminder(
        self,
        request: SetHabitReminderRequest,
    ) -> Result[dict[str, Any]]:
        """
        Set a reminder for a habit using typed request object.

        Stores reminder configuration directly on the Habit model.

        Args:
            request: SetHabitReminderRequest containing habit_uid, reminder_time, days, enabled

        Returns:
            Result with reminder configuration
        """
        # Verify habit exists
        habit_result = await self.core.get(request.habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result)

        # Update habit with reminder config
        update_result = await self.core.update_habit(
            request.habit_uid,
            HabitUpdateIntent(
                reminder_time=request.reminder_time,
                reminder_days=request.days,
                reminder_enabled=request.enabled,
            ),
        )
        if update_result.is_error:
            return Result.fail(update_result)

        self.logger.info(
            f"Set reminder for habit {request.habit_uid}: {request.reminder_time} on {request.days}"
        )
        return Result.ok(
            {
                "habit_uid": request.habit_uid,
                "reminder_time": request.reminder_time,
                "days": request.days,
                "enabled": request.enabled,
                "status": "configured",
            }
        )

    async def get_habit_reminders(self, habit_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get reminders for a habit.

        Returns the reminder configuration stored on the habit.

        Args:
            habit_uid: UID of the habit

        Returns:
            Result with list of reminders (single reminder per habit)
        """
        habit_result = await self.core.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result)

        habit = habit_result.value

        # If no reminder configured, return empty list
        if not habit.reminder_time and not habit.reminder_enabled:
            return Result.ok([])

        # Return the single reminder config as a list for API consistency
        reminder = {
            "id": f"{habit_uid}_reminder",
            "habit_uid": habit_uid,
            "reminder_time": habit.reminder_time,
            "days": list(habit.reminder_days) if habit.reminder_days else [],
            "enabled": habit.reminder_enabled,
        }
        return Result.ok([reminder])

    async def delete_habit_reminder(self, request: DeleteHabitReminderRequest) -> Result[bool]:
        """
        Delete a habit reminder using typed request object.

        Clears the reminder configuration from the habit.

        Args:
            request: DeleteHabitReminderRequest containing habit_uid, reminder_id

        Returns:
            Result with success status
        """
        # Verify habit exists
        habit_result = await self.core.get(request.habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result)

        # Clear reminder config
        update_result = await self.core.update_habit(
            request.habit_uid,
            HabitUpdateIntent(reminder_time=None, reminder_days=[], reminder_enabled=False),
        )
        if update_result.is_error:
            return Result.fail(update_result)

        self.logger.info(f"Deleted reminder for habit {request.habit_uid}")
        return Result.ok(True)
