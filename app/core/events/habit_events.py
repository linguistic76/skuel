"""
Habit Domain Events
===================

Events published by HabitsService for habit tracking operations.

Event Catalog:
- habit.created - Habit created
- habit.completed - Habit completion logged
- habit.streak_broken - Habit streak broken
- habit.missed - Scheduled habit not completed

Subscribers:
- UserService (context invalidation)
- StreakTrackingService (streak management)
- NotificationService (reminders, encouragement)
- AnalyticsEngine (habit adherence patterns)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID

# ============================================================================
# HABIT LIFECYCLE EVENTS
# ============================================================================


@dataclass(frozen=True)
class HabitCreated(BaseEvent):
    """
    Published when a habit is created.

    Subscribers:
    - Analytics (track habit creation patterns)
    - UserService (invalidate context)
    - SchedulerService (schedule habit events)
    """

    habit_uid: str
    user_uid: UserUID
    title: str
    frequency: str  # "daily", "weekly", etc.
    domain: str | None

    # Habit type context
    is_goal_related: bool = False
    related_goal_uid: str | None = None

    event_type: ClassVar[str] = "habit.created"


@dataclass(frozen=True)
class HabitUpdated(BaseEvent):
    """
    Published when habit node properties change (ADR-066 typed update path).

    Fired on every ``update_habit`` so user-context caches invalidate even for plain
    property edits (title, description, schedule, cue/routine/reward) that have no more
    specific event. Streak / completion changes additionally fire ``HabitCompleted`` /
    ``HabitStreakBroken`` / ``HabitStreakMilestone`` from ``HabitsProgressService``.

    Subscribers:
    - UserService (invalidate context)
    - Analytics (track update patterns)
    """

    habit_uid: str
    user_uid: UserUID
    updated_fields: list[str]

    event_type: ClassVar[str] = "habit.updated"


@dataclass(frozen=True)
class HabitCompleted(BaseEvent):
    """
    Published when a habit completion is logged.

    This is a HIGH-VOLUME event (daily habits create one per day).

    Subscribers:
    - UserService (invalidate context)
    - StreakTrackingService (update streak)
    - GoalProgressService (update related goal progress)
    - AnalyticsEngine (completion patterns)
    """

    habit_uid: str
    user_uid: UserUID

    # Streak context
    current_streak: int = 0
    is_new_streak_record: bool = False

    # Timing context
    completed_on_time: bool = True
    completed_late: bool = False

    event_type: ClassVar[str] = "habit.completed"


@dataclass(frozen=True)
class HabitStreakBroken(BaseEvent):
    """
    Published when a habit streak is broken.

    This is an IMPORTANT event for user engagement and recovery.

    Subscribers:
    - NotificationService (encouragement message)
    - AnalyticsEngine (understand failure patterns)
    - UserService (invalidate context)
    """

    habit_uid: str
    user_uid: UserUID

    # Streak information
    streak_length: int  # How long the streak was
    last_completion_date: datetime | None

    # Context for recovery
    days_since_last_completion: int = 0

    event_type: ClassVar[str] = "habit.streak_broken"


@dataclass(frozen=True)
class HabitMissed(BaseEvent):
    """
    Published when a scheduled habit is not completed.

    Different from streak_broken - this fires for each missed occurrence,
    while streak_broken only fires once when the streak breaks.

    Subscribers:
    - NotificationService (reminder/nudge)
    - AnalyticsEngine (adherence tracking)
    - RecommendationEngine (suggest easier alternatives)
    """

    habit_uid: str
    user_uid: UserUID

    # Scheduled vs actual
    scheduled_date: datetime
    days_overdue: int = 0

    # Pattern context
    consecutive_misses: int = 0

    event_type: ClassVar[str] = "habit.missed"


# ============================================================================
# HABIT MILESTONE EVENTS
# ============================================================================


@dataclass(frozen=True)
class HabitStreakMilestone(BaseEvent):
    """
    Published when a habit reaches a streak milestone.

    Milestones: 7 days (1 week), 30 days (1 month), 100 days, 365 days (1 year)

    Subscribers:
    - AchievementService (award badges)
    - NotificationService (celebration)
    """

    habit_uid: str
    user_uid: UserUID
    streak_length: int

    # Milestone type
    milestone_name: str  # "one_week", "one_month", "one_hundred", "one_year"

    event_type: ClassVar[str] = "habit.streak_milestone"


@dataclass(frozen=True)
class AchievementEarned(BaseEvent):
    """
    Published when a user earns an achievement badge.

    Subscribers:
    - NotificationService (show achievement notification)
    - Analytics (track achievement patterns)
    - UIService (display badge animation)
    """

    user_uid: UserUID
    badge_id: str
    badge_name: str
    badge_tier: str  # "bronze", "silver", "gold", "platinum"
    badge_category: str = "streak"  # streak, completion, quality, identity

    # Context — optional depending on badge category
    habit_uid: str = ""  # Per-habit badges; empty for cross-habit badges
    streak_length: int = 0  # Streak badges only
    threshold_value: int = 0  # The threshold that was crossed (e.g. 50 completions)

    event_type: ClassVar[str] = "habit.achievement_earned"


# ============================================================================
# BATCH HABIT EVENTS (Performance Optimization)
# ============================================================================


@dataclass(frozen=True)
class HabitCompletionBulk(BaseEvent):
    """
    Published when multiple habits are completed in a batch operation.

    More efficient than publishing N individual HabitCompleted events.
    O(1) event publication overhead vs O(n).

    Use cases:
    - Daily habit check-in (complete all daily habits at once)
    - Bulk habit completion UI
    - Batch processing of habit completions

    Subscribers:
    - UserService (single context invalidation vs N)
    - AnalyticsEngine (batch completion patterns)
    - GoalProgressService (batch goal updates)

    Published by:
    - HabitsService (when completing multiple habits)
    """

    habit_uids: tuple[str, ...]
    user_uid: UserUID

    # Aggregate streak information
    new_streak_records: tuple[str, ...] = ()  # UIDs of habits with new records
    milestones_reached: tuple[tuple[str, int], ...] = ()  # (habit_uid, streak_length)

    event_type: ClassVar[str] = "habits.bulk_completed"

    @property
    def count(self) -> int:
        return len(self.habit_uids)


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
Publishing Habit Events:
========================

# In HabitsService.create()
async def create_habit(self, habit: Habit) -> Result[Habit]:
    result = await self.backend.create(habit)

    if result.is_ok and self.event_bus:
        event = HabitCreated(
            habit_uid=habit.uid,
            user_uid=habit.user_uid,
            title=habit.title,
            frequency=habit.frequency.value,
            domain=habit.domain.value if habit.domain else None,
        )
        await self.event_bus.publish_async(event)

    return result


# In HabitsService.log_completion()
async def log_completion(self, habit_uid: str) -> Result[HabitCompletion]:
    # Get current streak
    habit_result = await self.backend.get(habit_uid)
    if habit_result.is_error:
        return habit_result

    habit = habit_result.value
    current_streak = habit.current_streak or 0
    best_streak = habit.best_streak or 0

    # Log completion
    result = await self.completions_backend.create_completion(habit_uid)

    if result.is_ok and self.event_bus:
        new_streak = current_streak + 1
        is_new_record = new_streak > best_streak

        event = HabitCompleted(
            habit_uid=habit_uid,
            user_uid=habit.user_uid,
            current_streak=new_streak,
            is_new_streak_record=is_new_record
        )
        await self.event_bus.publish_async(event)

        # Check for milestone
        if new_streak in [7, 30, 100, 365]:
            milestone_names = {7: "one_week", 30: "one_month", 100: "one_hundred", 365: "one_year"}
            milestone_event = HabitStreakMilestone(
                habit_uid=habit_uid,
                user_uid=habit.user_uid,
                streak_length=new_streak,
                milestone_name=milestone_names[new_streak]
            )
            await self.event_bus.publish_async(milestone_event)

    return result


# In HabitsService.check_missed_habits()
async def check_missed_habits(self, user_uid: UserUID) -> Result[list[str]]:
    '''Check for habits that were scheduled but not completed.'''
    missed_habits = await self._find_missed_habits(user_uid)

    for habit in missed_habits:
        if self.event_bus:
            event = HabitMissed(
                habit_uid=habit.uid,
                user_uid=habit.user_uid,
                scheduled_date=habit.last_scheduled_date,
                days_overdue=(datetime.now() - habit.last_scheduled_date).days
            )
            await self.event_bus.publish_async(event)

    return Result.ok([h.uid for h in missed_habits])


# In HabitsService.break_streak()
async def break_streak(self, habit_uid: str) -> Result[None]:
    '''Internal method to break a habit streak.'''
    habit_result = await self.backend.get(habit_uid)
    if habit_result.is_error:
        return habit_result

    habit = habit_result.value
    streak_length = habit.current_streak or 0

    # Break the streak
    await self.backend.update(habit_uid, {"current_streak": 0})

    # Publish event
    if self.event_bus and streak_length > 0:
        event = HabitStreakBroken(
            habit_uid=habit_uid,
            user_uid=habit.user_uid,
            streak_length=streak_length,
            last_completion_date=habit.last_completion_date
        )
        await self.event_bus.publish_async(event)

    return Result.ok(None)


Subscribing to Habit Events:
============================

# In UserService
async def handle_habit_completed(self, event: HabitCompleted) -> None:
    '''Invalidate user context when habit completed.'''
    await self.invalidate_context(event.user_uid)
    self.logger.info(f"Context invalidated for user {event.user_uid} (habit completed)")


# In StreakTrackingService
async def handle_habit_completed(self, event: HabitCompleted) -> None:
    '''Update streak tracking when habit completed.'''
    if event.is_new_streak_record:
        await self.update_best_streak(event.habit_uid, event.current_streak)
        self.logger.info(f"New streak record for habit {event.habit_uid}: {event.current_streak}")


# In NotificationService
async def handle_habit_streak_broken(self, event: HabitStreakBroken) -> None:
    '''Send encouragement when streak broken.'''
    await self.send_notification(
        user_uid=event.user_uid,
        title="Don't give up!",
        message=f"Your {event.streak_length}-day streak ended. Start a new one today!"
    )


async def handle_habit_missed(self, event: HabitMissed) -> None:
    '''Send reminder when habit missed.'''
    if event.consecutive_misses >= 2:
        await self.send_notification(
            user_uid=event.user_uid,
            title="Habit reminder",
            message="You've missed this habit twice in a row. Get back on track!"
        )


# In AchievementService
async def handle_habit_streak_milestone(self, event: HabitStreakMilestone) -> None:
    '''Award achievement when milestone reached.'''
    milestone_badges = {
        "one_week": "week_warrior",
        "one_month": "monthly_master",
        "one_hundred": "centurion",
        "one_year": "year_champion"
    }

    badge = milestone_badges.get(event.milestone_name)
    if badge:
        await self.award_badge(event.user_uid, badge)


# In Bootstrap
event_bus.subscribe(HabitCompleted, user_service.handle_habit_completed)
event_bus.subscribe(HabitCompleted, streak_tracking.handle_habit_completed)
event_bus.subscribe(HabitStreakBroken, notification_service.handle_habit_streak_broken)
event_bus.subscribe(HabitMissed, notification_service.handle_habit_missed)
event_bus.subscribe(HabitStreakMilestone, achievement_service.handle_habit_streak_milestone)
"""
