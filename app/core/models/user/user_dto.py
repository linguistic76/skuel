"""
User Data Transfer Object (DTO)
================================

Mutable DTO for transferring user data between layers.
This is the middle tier of our three-tier architecture:
- External: user_request.py (Pydantic validation)
- Transfer: user_dto.py (this file, mutable dataclass)
- Core: user.py (frozen domain model)

Note: The rich context functionality has moved to user_context.py
This file now focuses solely on simple data transfer for the User entity.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.shared_enums import (
    EnergyLevel,
    LearningLevel,
    TimeOfDay,
)


@dataclass
class UserPreferencesDTO:
    """Mutable DTO for user preferences"""

    # Learning preferences
    learning_level: LearningLevel = LearningLevel.INTERMEDIATE
    preferred_modalities: list[str] = (field(default_factory=list),)
    preferred_subjects: list[str] = field(default_factory=list)

    # Scheduling preferences
    preferred_time_of_day: TimeOfDay = TimeOfDay.ANYTIME
    available_minutes_daily: int = 60
    energy_pattern: dict[TimeOfDay, EnergyLevel] = field(default_factory=dict)

    # Notification preferences
    enable_reminders: bool = True
    reminder_minutes_before: int = 15
    daily_summary_time: str | None = "09:00"

    # Display preferences
    theme: str = "light"
    language: str = "en"
    timezone: str = "UTC"

    # Goal preferences
    weekly_task_goal: int = 10
    daily_habit_goal: int = 3
    monthly_learning_hours: int = 20


@dataclass
class UserDTO:
    """
    Mutable data transfer object for User entity.

    Used for moving user data between service and repository layers.
    For rich context functionality, see user_context.py
    """

    # Identity
    uid: str
    username: str  # Unique username
    email: str
    display_name: str = ""

    # Preferences
    preferences: UserPreferencesDTO = field(default_factory=UserPreferencesDTO)

    # Entity management (just UIDs)
    active_entity_uids: set[str] = (field(default_factory=set),)
    archived_entity_uids: set[str] = field(default_factory=set)

    # Pinned entities - GRAPH-NATIVE: Query via UserRelationshipService
    # Graph relationship: (user)-[:PINNED {order}]->(entity)
    pinned_entity_uids: list[str] = field(default_factory=list)  # Populated from service layer

    # Interests and goals
    interests: list[str] = (field(default_factory=list),)
    achievements: list[str] = field(default_factory=list)

    # Current goals - GRAPH-NATIVE: Query via UserRelationshipService
    # Graph relationship: (user)-[:PURSUING_GOAL]->(goal)
    current_goals: list[str] = field(default_factory=list)  # Populated from service layer

    # Social connections - GRAPH-NATIVE: Query via UserRelationshipService
    # Graph relationship: (user)-[:FOLLOWS]->(other_user)
    # Graph relationship: (follower)-[:FOLLOWS]->(user) [inverse]
    # Graph relationship: (user)-[:MEMBER_OF]->(team)
    following_uids: set[str] = field(default_factory=set)  # Populated from service layer
    follower_uids: set[str] = field(
        default_factory=set
    )  # Populated from service layer (inverse query)
    team_uids: set[str] = field(default_factory=set)  # Populated from service layer

    # Account metadata
    created_at: datetime = (field(default_factory=datetime.now),)
    last_active_at: datetime | None = (None,)
    last_login_at: datetime | None = None

    # Account status
    is_active: bool = True

    is_verified: bool = False
    is_premium: bool = False

    # Settings
    settings: dict[str, Any] = field(default_factory=dict)

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        username: str,
        email: str,
        display_name: str | None = None,
        learning_level: LearningLevel = LearningLevel.INTERMEDIATE,
    ) -> "UserDTO":
        """Factory method to create new UserDTO with generated UID"""
        from core.utils.uid_generator import UIDGenerator

        return cls(
            uid=UIDGenerator.generate_random_uid("user"),
            username=username,
            email=email,
            display_name=display_name or username,
            preferences=UserPreferencesDTO(learning_level=learning_level),
        )

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update fields from dictionary."""
        from core.models.dto_helpers import update_from_dict

        # Note: UserDTO uses last_active_at instead of updated_at
        update_from_dict(self, updates)
        self.last_active_at = datetime.now()

    def add_active_entity(self, entity_uid: str) -> bool:
        """Add an entity to active set"""
        if entity_uid not in self.active_entity_uids:
            self.active_entity_uids.add(entity_uid)
            return True
        return False

    def remove_active_entity(self, entity_uid: str) -> bool:
        """Remove an entity from active set"""
        if entity_uid in self.active_entity_uids:
            self.active_entity_uids.remove(entity_uid)
            return True
        return False

    def archive_entity(self, entity_uid: str) -> None:
        """Archive an entity"""
        self.active_entity_uids.discard(entity_uid)
        self.archived_entity_uids.add(entity_uid)

    def unarchive_entity(self, entity_uid: str) -> None:
        """Unarchive an entity"""
        self.archived_entity_uids.discard(entity_uid)

    def pin_entity(self, entity_uid: str) -> None:
        """Pin an entity (adds to front of pinned list)"""
        if entity_uid in self.pinned_entity_uids:
            self.pinned_entity_uids.remove(entity_uid)
        self.pinned_entity_uids.insert(0, entity_uid)

    def unpin_entity(self, entity_uid: str) -> None:
        """Unpin an entity"""
        if entity_uid in self.pinned_entity_uids:
            self.pinned_entity_uids.remove(entity_uid)

    def add_goal(self, goal_uid: str) -> None:
        """Add a current goal"""
        if goal_uid not in self.current_goals:
            self.current_goals.append(goal_uid)

    def complete_goal(self, goal_uid: str) -> None:
        """Mark a goal as achieved"""
        if goal_uid in self.current_goals:
            self.current_goals.remove(goal_uid)
        if goal_uid not in self.achievements:
            self.achievements.append(goal_uid)

    def follow_user(self, user_uid: str) -> None:
        """Follow another user"""
        self.following_uids.add(user_uid)

    def unfollow_user(self, user_uid: str) -> None:
        """Unfollow a user"""
        self.following_uids.discard(user_uid)

    def add_follower(self, user_uid: str) -> None:
        """Add a follower"""
        self.follower_uids.add(user_uid)

    def remove_follower(self, user_uid: str) -> None:
        """Remove a follower"""
        self.follower_uids.discard(user_uid)

    def join_team(self, team_uid: str) -> None:
        """Join a team"""
        self.team_uids.add(team_uid)

    def leave_team(self, team_uid: str) -> None:
        """Leave a team"""
        self.team_uids.discard(team_uid)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations"""
        from core.services.protocols import get_enum_value

        def serialize_value(v) -> Any:
            if isinstance(v, datetime):
                return v.isoformat()
            elif isinstance(v, set):
                return list(v)
            elif isinstance(v, UserPreferencesDTO):
                return {
                    "learning_level": v.learning_level.value,
                    "preferred_modalities": v.preferred_modalities,
                    "preferred_subjects": v.preferred_subjects,
                    "preferred_time_of_day": v.preferred_time_of_day.value,
                    "available_minutes_daily": v.available_minutes_daily,
                    "energy_pattern": {k.value: v.value for k, v in v.energy_pattern.items()},
                    "enable_reminders": v.enable_reminders,
                    "reminder_minutes_before": v.reminder_minutes_before,
                    "daily_summary_time": v.daily_summary_time,
                    "theme": v.theme,
                    "language": v.language,
                    "timezone": v.timezone,
                    "weekly_task_goal": v.weekly_task_goal,
                    "daily_habit_goal": v.daily_habit_goal,
                    "monthly_learning_hours": v.monthly_learning_hours,
                }
            else:
                # Try enum extraction for any other type
                return get_enum_value(v)

        return {
            "uid": self.uid,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "preferences": serialize_value(self.preferences),
            "active_entity_uids": serialize_value(self.active_entity_uids),
            "pinned_entity_uids": self.pinned_entity_uids,
            "archived_entity_uids": serialize_value(self.archived_entity_uids),
            "interests": self.interests,
            "current_goals": self.current_goals,
            "achievements": self.achievements,
            "following_uids": serialize_value(self.following_uids),
            "follower_uids": serialize_value(self.follower_uids),
            "team_uids": serialize_value(self.team_uids),
            "created_at": serialize_value(self.created_at),
            "last_active_at": serialize_value(self.last_active_at),
            "last_login_at": serialize_value(self.last_login_at),
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "is_premium": self.is_premium,
            "settings": self.settings,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserDTO":
        """Create DTO from dictionary"""
        from core.models.dto_helpers import parse_datetime_fields

        # Parse datetimes
        parse_datetime_fields(data, ["created_at", "last_active_at", "last_login_at"])

        # Parse preferences if dict
        if "preferences" in data and isinstance(data["preferences"], dict):
            pref_data = data["preferences"]
            data["preferences"] = UserPreferencesDTO(
                learning_level=LearningLevel(pref_data.get("learning_level", "intermediate")),
                preferred_modalities=pref_data.get("preferred_modalities", []),
                preferred_subjects=pref_data.get("preferred_subjects", []),
                preferred_time_of_day=TimeOfDay(pref_data.get("preferred_time_of_day", "anytime")),
                available_minutes_daily=pref_data.get("available_minutes_daily", 60),
                energy_pattern={
                    TimeOfDay(k): EnergyLevel(v)
                    for k, v in pref_data.get("energy_pattern", {}).items()
                },
                enable_reminders=pref_data.get("enable_reminders", True),
                reminder_minutes_before=pref_data.get("reminder_minutes_before", 15),
                daily_summary_time=pref_data.get("daily_summary_time", "09:00"),
                theme=pref_data.get("theme", "light"),
                language=pref_data.get("language", "en"),
                timezone=pref_data.get("timezone", "UTC"),
                weekly_task_goal=pref_data.get("weekly_task_goal", 10),
                daily_habit_goal=pref_data.get("daily_habit_goal", 3),
                monthly_learning_hours=pref_data.get("monthly_learning_hours", 20),
            )

        # Convert lists to sets where needed
        for set_field in [
            "active_entity_uids",
            "archived_entity_uids",
            "following_uids",
            "follower_uids",
            "team_uids",
        ]:
            if set_field in data and isinstance(data[set_field], list):
                data[set_field] = set(data[set_field])

        return cls(**data)
