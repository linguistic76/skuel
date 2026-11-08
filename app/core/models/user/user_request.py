"""
User Boundary Schemas (Pydantic)
=================================

Pydantic models for the User boundary: the Settings editor's save
(``UserPreferencesFormRequest``), and the account shapes no door binds yet,
each registered with its reason in /docs/roadmap/request-models-no-door-reads.md.

This follows the architectural principle: Pydantic at the edges, pure domain inside.
"""

from __future__ import annotations

from core.models.type_hints import UserUID

__version__ = "1.0"


from typing import Any

from pydantic import BaseModel, Field, field_validator

# Import enums directly for use in Pydantic models
from core.models.enums import (
    LearningLevel,
    TimeOfDay,
)
from core.models.request_base import ClientDateTime
from core.models.user.user import LANGUAGES, THEMES
from core.utils.zone_context import validated_zone_name

# ============================================================================
# USER PREFERENCES SCHEMAS
# ============================================================================


class UserPreferencesFormRequest(BaseModel):
    """The Settings editor's save: every field the preferences form posts.

    Each field the form always sends is required, so a post that leaves one out
    is refused rather than storing a default the user did not choose. The four
    modality checkboxes and ``enable_reminders`` are absent when unchecked, so
    absent is ``False``. An empty time zone or summary time is no choice.

    See: /docs/patterns/ERROR_HANDLING.md § Never silently default on a write
    """

    learning_level: LearningLevel
    preferred_time_of_day: TimeOfDay
    available_minutes_daily: int = Field(ge=0, le=1440)
    enable_reminders: bool = False
    reminder_minutes_before: int = Field(ge=0, le=1440)
    daily_summary_time: str | None = Field(pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")
    theme: str
    language: str
    timezone: str | None
    weekly_task_goal: int = Field(ge=0, le=100)
    daily_habit_goal: int = Field(ge=0, le=20)
    monthly_learning_hours: int = Field(ge=0, le=500)
    modality_video: bool = False
    modality_reading: bool = False
    modality_interactive: bool = False
    modality_audio: bool = False

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, value: str) -> str:
        """One of the themes the editor offers."""
        if value not in THEMES:
            raise ValueError(f"Unknown theme {value!r}: expected one of {', '.join(THEMES)}")
        return value

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """One of the languages the editor offers."""
        if value not in LANGUAGES:
            raise ValueError(f"Unknown language {value!r}: expected one of {', '.join(LANGUAGES)}")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        """A zone zoneinfo lists, or None for no choice (a blank value included)."""
        return validated_zone_name(value)

    def to_preferences_update(self) -> dict[str, object]:
        """The ``UserPreferences`` fields this form sets, as one patch."""
        modalities = [
            name
            for name, chosen in (
                ("video", self.modality_video),
                ("reading", self.modality_reading),
                ("interactive", self.modality_interactive),
                ("audio", self.modality_audio),
            )
            if chosen
        ]
        return {
            "learning_level": self.learning_level,
            "preferred_modalities": modalities,
            "preferred_time_of_day": self.preferred_time_of_day,
            "available_minutes_daily": self.available_minutes_daily,
            "enable_reminders": self.enable_reminders,
            "reminder_minutes_before": self.reminder_minutes_before,
            "daily_summary_time": self.daily_summary_time,
            "theme": self.theme,
            "language": self.language,
            "timezone": self.timezone,
            "weekly_task_goal": self.weekly_task_goal,
            "daily_habit_goal": self.daily_habit_goal,
            "monthly_learning_hours": self.monthly_learning_hours,
        }


# ============================================================================
# USER SCHEMAS
# ============================================================================


class UserUpdateSchema(BaseModel):
    """Schema for updating a user"""

    display_name: str | None = Field(default=None, max_length=100)

    # Entity management
    active_entity_uids: set[str] | None = None
    pinned_entity_uids: list[str] | None = None
    archived_entity_uids: set[str] | None = None

    # Interests and goals
    interests: list[str] | None = Field(default=None, max_length=20)
    current_goals: list[str] | None = Field(default=None, max_length=10)
    achievements: list[str] | None = Field(default=None, max_length=50)

    # Settings
    settings: dict[str, Any] | None = None


class UserCapacityCheckSchema(BaseModel):
    """Schema for checking user capacity"""

    user_uid: UserUID
    new_items_count: int = Field(default=1, ge=1, description="Number of new items to add")
    check_time_availability: bool = Field(
        default=True, description="Check if user has time available"
    )


class UserCapacityView(BaseModel):
    """View for user capacity information"""

    user_uid: UserUID
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
    created_after: ClientDateTime | None = None
    created_before: ClientDateTime | None = None
    last_active_after: ClientDateTime | None = None
    last_active_before: ClientDateTime | None = None
    has_goals: bool | None = None
    min_completion_rate: float | None = Field(default=None, ge=0, le=100)
    max_completion_rate: float | None = Field(default=None, ge=0, le=100)
    interests: list[str] | None = None
    teams: list[str] | None = None
    search_text: str | None = Field(
        default=None, min_length=1, description="Search in username/display_name"
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
