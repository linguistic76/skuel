"""
Habit Domain Events
===================

Events published by the Habits services (``core/services/habits/``) for habit tracking.

``habit.missed`` is the one event here with no publisher: a PLANNED event
(``scripts/detect_bloat.py``) whose subscriber is already wired. The classes below are
the catalog.

Publishers and subscribers are deliberately not enumerated here - such a list drifts
silently. To find publishers, grep the event class name under ``core/services/habits/``.
For subscribers, read ``services_bootstrap/_event_wiring.py`` and ``_intelligence_hub.py``,
plus the components that subscribe themselves (e.g. the metrics handler): grepping an event's
class name misses the subscriptions registered by looping over a list of event types.
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
