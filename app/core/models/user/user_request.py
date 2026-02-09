"""
User Boundary Schemas (Pydantic)
=================================

Pydantic DTOs for the simplified User service boundary. These schemas support
the UserPure model that delegates to unified systems.

This follows the architectural principle: Pydantic at the edges, pure domain inside.
"""

from __future__ import annotations

__version__ = "1.0"


from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from core.infrastructure.utils.factory_functions import create_default_user_energy_pattern

# Import enums directly for use in Pydantic models
from core.models.enums import (
    EnergyLevel,
    LearningLevel,
    TimeOfDay,
)

# ============================================================================
# USER PREFERENCES SCHEMAS
# ============================================================================


class UserPreferencesSchema(BaseModel):
    """Schema for user preferences"""

    # Learning preferences
    learning_level: LearningLevel = Field(
        default=LearningLevel.INTERMEDIATE, description="Current learning proficiency"
    )
    preferred_modalities: list[str] = Field(
        default_factory=list,
        description="Preferred learning modalities (video, reading, interactive)",
    )
    preferred_subjects: list[str] = Field(default_factory=list, description="Subjects of interest")

    # Scheduling preferences
    preferred_time_of_day: TimeOfDay = Field(
        default=TimeOfDay.ANYTIME, description="Preferred time for activities"
    )
    available_minutes_daily: int = Field(
        default=60, ge=0, le=1440, description="Available minutes per day"
    )
    energy_pattern: dict[TimeOfDay, EnergyLevel] = Field(
        default_factory=create_default_user_energy_pattern,
        description="Energy levels throughout the day",
    )

    # Notification preferences
    enable_reminders: bool = Field(default=True)
    reminder_minutes_before: int = Field(
        default=15, ge=0, le=1440, description="Minutes before event to remind"
    )
    daily_summary_time: str | None = Field(
        default="09:00",
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="Daily summary time (HH:MM)",
    )

    # Display preferences
    theme: str = Field(default="light", description="UI theme (light, dark, auto)")
    language: str = Field(default="en", description="Language code")
    timezone: str = Field(default="UTC", description="User timezone")

    # Goal preferences
    weekly_task_goal: int = Field(default=10, ge=0, le=100, description="Target tasks per week")
    daily_habit_goal: int = Field(default=3, ge=0, le=20, description="Target habits per day")
    monthly_learning_hours: int = Field(
        default=20, ge=0, le=500, description="Target learning hours per month"
    )


# ============================================================================
# USER SCHEMAS
# ============================================================================


class UserCreateSchema(BaseModel):
    """Schema for creating a new user"""

    username: str = Field(
        min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$", description="Unique username"
    )
    email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$", description="User email address")
    display_name: str = Field(default="", max_length=100, description="Display name")

    # Initial preferences
    preferences: UserPreferencesSchema | None = None

    # Initial interests and goals
    interests: list[str] = Field(default_factory=list, max_length=20, description="User interests")
    current_goals: list[str] = Field(
        default_factory=list, max_length=10, description="Current goals"
    )


class UserUpdateSchema(BaseModel):
    """Schema for updating a user"""

    display_name: str | None = Field(None, max_length=100)

    # Preferences update
    preferences: UserPreferencesSchema | None = None

    # Entity management
    active_entity_uids: set[str] | None = None
    pinned_entity_uids: list[str] | None = None
    archived_entity_uids: set[str] | None = None

    # Interests and goals
    interests: list[str] | None = Field(None, max_length=20)
    current_goals: list[str] | None = Field(None, max_length=10)
    achievements: list[str] | None = Field(None, max_length=50)

    # Settings
    settings: dict[str, Any] | None = None


class UserView(BaseModel):
    """View model for presenting user data"""

    # Core identity
    uid: str
    username: str
    email: str
    display_name: str

    # User preferences
    preferences: UserPreferencesSchema

    # Active entities
    active_entity_uids: set[str]
    pinned_entity_uids: list[str]
    archived_entity_uids: set[str]
    active_entity_count: int
    has_capacity: bool

    # Interests and goals
    interests: list[str]
    current_goals: list[str]
    achievements: list[str]

    # Social connections
    following_uids: set[str]
    follower_uids: set[str]
    team_uids: set[str]
    following_count: int
    follower_count: int

    # Account metadata
    created_at: datetime
    last_active_at: datetime | None
    last_login_at: datetime | None

    # Account status
    is_active: bool
    is_verified: bool
    is_premium: bool

    # Settings
    settings: dict[str, Any]

    # Computed fields
    days_since_joined: int
    current_streak_days: int | None
    completion_rate: float | None
    learning_level_numeric: int


class UserSummaryView(BaseModel):
    """Lightweight view for user summaries"""

    uid: str
    username: str
    display_name: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_active_at: datetime | None
    active_entity_count: int
    completion_rate: float | None


class UserServiceContextSchema(BaseModel):
    """Schema for lightweight service context"""

    user_uid: str
    username: str
    learning_level: LearningLevel

    # Current focus
    active_entity_uids: set[str]
    current_goal_uids: list[str]

    # Preferences relevant to services
    preferred_time: TimeOfDay
    available_minutes: int
    interests: list[str]

    # Session info
    session_id: str | None = None
    session_start: datetime | None = None


class UserStatisticsSchema(BaseModel):
    """Schema for computed user statistics"""

    user_uid: str
    computed_at: datetime

    # Activity counts
    total_tasks: int = Field(default=0)
    completed_tasks: int = Field(default=0)
    total_habits: int = Field(default=0)
    active_habits: int = Field(default=0)
    total_learning_sessions: int = Field(default=0)
    completed_learning: int = Field(default=0)

    # Progress metrics
    overall_completion_rate: float = Field(default=0.0, description="Percentage completion rate")
    average_task_duration_minutes: float = Field(default=0.0)
    total_time_spent_hours: float = Field(default=0.0)

    # Streak metrics
    current_streak_days: int = Field(default=0)
    longest_streak_days: int = Field(default=0)
    consistency_score: float = Field(
        default=0.0, ge=0, le=100, description="Consistency score (0-100)"
    )

    # Learning metrics
    topics_mastered: int = Field(default=0)
    average_mastery_level: float = Field(default=0.0)
    learning_velocity: float = Field(default=1.0, description="Learning speed relative to average")

    # Time patterns
    most_active_time: TimeOfDay | None = None
    most_productive_day: str | None = Field(None, description="Day of week")


class UserCapacityCheckSchema(BaseModel):
    """Schema for checking user capacity"""

    user_uid: str
    new_items_count: int = Field(default=1, ge=1, description="Number of new items to add")
    check_time_availability: bool = Field(
        default=True, description="Check if user has time available"
    )


class UserCapacityView(BaseModel):
    """View for user capacity information"""

    user_uid: str
    has_capacity: bool
    current_active_items: int
    max_active_items: int
    available_minutes_daily: int
    estimated_minutes_used: int
    can_add_items: int
    capacity_percentage: float


class UserFilterSchema(BaseModel):
    """Schema for filtering users"""

    is_active: bool | None = None
    is_verified: bool | None = None
    is_premium: bool | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None  # type: ignore[assignment]
    last_active_after: datetime | None = None
    last_active_before: datetime | None = None  # type: ignore[assignment]
    has_goals: bool | None = None
    min_completion_rate: float | None = Field(None, ge=0, le=100)
    max_completion_rate: float | None = Field(None, ge=0, le=100)
    interests: list[str] | None = None
    teams: list[str] | None = None
    search_text: str | None = Field(
        None, min_length=1, description="Search in username/display_name"
    )


class UserAnalyticsView(BaseModel):
    """Analytics view for user data"""

    total_users: int
    active_users: int
    verified_users: int
    premium_users: int

    # Activity metrics
    average_completion_rate: float
    average_active_items: float
    average_daily_minutes: float

    # Growth metrics
    new_users_this_month: int
    user_growth_rate: float
    retention_rate: float

    # Engagement metrics
    daily_active_users: int
    weekly_active_users: int
    monthly_active_users: int
    average_session_duration_minutes: float

    # Learning metrics
    average_learning_level: float
    users_by_level: dict[LearningLevel, int]

    # Trends
    user_growth_trend: list[dict[str, Any]]
    activity_trend: list[dict[str, Any]]
    completion_trend: list[dict[str, Any]]
