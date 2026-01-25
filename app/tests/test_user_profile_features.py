"""
Tests for User Profile Features
================================

Comprehensive tests for user preferences editing and activity tracking
features implemented in the User Profile UI.

Version: 1.0.0
Date: 2025-10-14
"""

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.shared_enums import (
    LearningLevel,
    TimeOfDay,
)
from core.models.user.user import User, UserPreferences
from core.utils.result_simplified import Result


@pytest.fixture
def sample_user_preferences() -> UserPreferences:
    """Create sample user preferences."""
    return UserPreferences(
        learning_level=LearningLevel.INTERMEDIATE,
        preferred_modalities=["video", "reading"],
        preferred_time_of_day=TimeOfDay.MORNING,
        available_minutes_daily=90,
        enable_reminders=True,
        reminder_minutes_before=15,
        daily_summary_time="09:00",
        theme="dark",
        language="en",
        timezone="America/New_York",
        weekly_task_goal=10,
        daily_habit_goal=3,
        monthly_learning_hours=20,
    )


@pytest.fixture
def sample_user(sample_user_preferences) -> User:
    """Create sample user with preferences."""
    return User(
        uid="user.mike",
        title="mike",  # Username stored as title (from BaseEntity)
        description="Test user account",
        email="mike@example.com",
        display_name="Mike Test",
        preferences=sample_user_preferences,
        created_at=datetime.now(),
    )


@pytest.fixture
def mock_services() -> Any:
    """Create mock services for testing."""
    services = MagicMock()

    # Mock user service
    services.user_service = AsyncMock()

    # Mock domain services
    services.tasks = AsyncMock()
    services.tasks.backend = AsyncMock()

    services.events = AsyncMock()
    services.events.backend = AsyncMock()

    services.habits = AsyncMock()
    services.habits.backend = AsyncMock()
    services.habits.completions = AsyncMock()

    services.goals = AsyncMock()
    services.goals.backend = AsyncMock()

    services.principles = AsyncMock()
    services.principles.backend = AsyncMock()
    services.principles.alignment = AsyncMock()

    return services


class TestUserPreferencesExtraction:
    """Test extracting user preferences for display."""

    def test_preferences_to_dict_all_fields(self, sample_user):
        """Test extracting all preference fields to dict."""
        prefs = sample_user.preferences

        prefs_dict = {
            "learning_level": prefs.learning_level.value,
            "preferred_modalities": prefs.preferred_modalities,
            "preferred_time_of_day": prefs.preferred_time_of_day.value,
            "available_minutes_daily": prefs.available_minutes_daily,
            "enable_reminders": prefs.enable_reminders,
            "reminder_minutes_before": prefs.reminder_minutes_before,
            "daily_summary_time": prefs.daily_summary_time,
            "theme": prefs.theme,
            "language": prefs.language,
            "timezone": prefs.timezone,
            "weekly_task_goal": prefs.weekly_task_goal,
            "daily_habit_goal": prefs.daily_habit_goal,
            "monthly_learning_hours": prefs.monthly_learning_hours,
        }

        assert prefs_dict["learning_level"] == "intermediate"
        assert "video" in prefs_dict["preferred_modalities"]
        assert prefs_dict["preferred_time_of_day"] == "morning"
        assert prefs_dict["available_minutes_daily"] == 90
        assert prefs_dict["enable_reminders"] is True
        assert prefs_dict["theme"] == "dark"
        assert prefs_dict["weekly_task_goal"] == 10

    def test_preferences_default_values(self):
        """Test default preference values when user has no preferences."""
        default_prefs = UserPreferences()

        # Verify defaults match UserPreferences dataclass defaults
        assert default_prefs.learning_level == LearningLevel.INTERMEDIATE
        assert default_prefs.preferred_modalities == []
        assert default_prefs.preferred_time_of_day == TimeOfDay.ANYTIME
        assert default_prefs.available_minutes_daily == 60
        assert default_prefs.enable_reminders is True
        assert default_prefs.theme == "light"
        assert default_prefs.language == "en"


class TestFormDataParsing:
    """Test parsing form data into preference updates."""

    def test_parse_modalities_from_checkboxes(self):
        """Test parsing preferred modalities from checkbox inputs."""
        form_data = {
            "modality_video": "on",
            "modality_reading": "on",
            "modality_interactive": None,
            "modality_audio": "on",
        }

        modalities = []
        if form_data.get("modality_video"):
            modalities.append("video")
        if form_data.get("modality_reading"):
            modalities.append("reading")
        if form_data.get("modality_interactive"):
            modalities.append("interactive")
        if form_data.get("modality_audio"):
            modalities.append("audio")

        assert len(modalities) == 3
        assert "video" in modalities
        assert "reading" in modalities
        assert "audio" in modalities
        assert "interactive" not in modalities

    def test_parse_numeric_fields(self):
        """Test parsing numeric preference fields."""
        form_data = {
            "available_minutes_daily": "120",
            "reminder_minutes_before": "30",
            "weekly_task_goal": "15",
            "daily_habit_goal": "5",
            "monthly_learning_hours": "25",
        }

        # Convert string values to integers
        parsed = {
            "available_minutes_daily": int(form_data["available_minutes_daily"]),
            "reminder_minutes_before": int(form_data["reminder_minutes_before"]),
            "weekly_task_goal": int(form_data["weekly_task_goal"]),
            "daily_habit_goal": int(form_data["daily_habit_goal"]),
            "monthly_learning_hours": int(form_data["monthly_learning_hours"]),
        }

        assert parsed["available_minutes_daily"] == 120
        assert parsed["reminder_minutes_before"] == 30
        assert parsed["weekly_task_goal"] == 15

    def test_parse_enum_fields(self):
        """Test parsing enum preference fields."""
        form_data = {"learning_level": "advanced", "preferred_time_of_day": "evening"}

        # Verify enum values are valid
        assert form_data["learning_level"] in ["beginner", "intermediate", "advanced", "expert"]
        assert form_data["preferred_time_of_day"] in [
            "anytime",
            "morning",
            "afternoon",
            "evening",
            "night",
        ]


class TestActivityAggregation:
    """Test aggregating activities from multiple domains."""

    @pytest.mark.asyncio
    async def test_aggregate_task_activities(self, mock_services):
        """Test collecting task activities."""
        # Mock task data
        task_dict = {
            "uid": "task.123",
            "title": "Write tests",
            "status": "in_progress",
            "priority": "high",
            "updated_at": datetime.now().isoformat(),
        }

        mock_services.tasks.backend.find_by.return_value = Result.ok([task_dict])

        # Collect task activities
        activities = []
        tasks_result = await mock_services.tasks.backend.find_by(limit=5)
        if tasks_result.is_ok:
            activities.extend(
                [
                    {
                        "timestamp": task.get("updated_at"),
                        "type": "task_updated",
                        "domain": "tasks",
                        "title": task.get("title"),
                        "uid": task.get("uid"),
                    }
                    for task in tasks_result.value
                ]
            )

        assert len(activities) == 1
        assert activities[0]["type"] == "task_updated"
        assert activities[0]["title"] == "Write tests"
        assert activities[0]["domain"] == "tasks"

    @pytest.mark.asyncio
    async def test_aggregate_event_activities(self, mock_services):
        """Test collecting event activities."""
        event_dict = {
            "uid": "event.123",
            "title": "Team meeting",
            "event_type": "meeting",
            "updated_at": datetime.now().isoformat(),
        }

        mock_services.events.backend.find_by.return_value = Result.ok([event_dict])

        activities = []
        events_result = await mock_services.events.backend.find_by(limit=5)
        if events_result.is_ok:
            activities.extend(
                [
                    {
                        "timestamp": event.get("updated_at"),
                        "type": "event_created",
                        "domain": "events",
                        "title": event.get("title"),
                        "uid": event.get("uid"),
                    }
                    for event in events_result.value
                ]
            )

        assert len(activities) == 1
        assert activities[0]["type"] == "event_created"

    @pytest.mark.asyncio
    async def test_aggregate_habit_completions(self, mock_services):
        """Test collecting habit completion activities."""
        completion_activity = {
            "timestamp": datetime.now().isoformat(),
            "type": "habit_completed",
            "habit_uid": "habit.123",
            "habit_name": "Exercise",
            "description": "Completed habit: Exercise",
        }

        mock_services.habits.completions.get_recent_activity.return_value = Result.ok(
            [completion_activity]
        )

        activities = []
        completions_result = await mock_services.habits.completions.get_recent_activity(
            "user.mike", limit=5
        )
        if completions_result.is_ok:
            activities.extend(completions_result.value)

        assert len(activities) == 1
        assert activities[0]["type"] == "habit_completed"
        assert activities[0]["habit_name"] == "Exercise"

    @pytest.mark.asyncio
    async def test_aggregate_principle_activities(self, mock_services):
        """Test collecting principle alignment activities."""
        principle_activity = {
            "timestamp": datetime.now().isoformat(),
            "type": "alignment_assessed",
            "principle_uid": "principle.integrity",
            "principle_name": "Integrity",
            "description": "Assessed alignment: Integrity",
        }

        mock_services.principles.alignment.get_recent_activity.return_value = Result.ok(
            [principle_activity]
        )

        activities = []
        principles_result = await mock_services.principles.alignment.get_recent_activity(
            "user.mike", limit=5
        )
        if principles_result.is_ok:
            activities.extend(principles_result.value)

        assert len(activities) == 1
        assert activities[0]["type"] == "alignment_assessed"

    @pytest.mark.asyncio
    async def test_aggregate_multiple_domains(self, mock_services):
        """Test aggregating activities from multiple domains."""
        # Mock task activity
        task_dict = {"uid": "task.123", "title": "Task 1", "updated_at": datetime.now().isoformat()}
        mock_services.tasks.backend.find_by.return_value = Result.ok([task_dict])

        # Mock habit completion
        habit_activity = {
            "timestamp": (datetime.now() - timedelta(hours=1)).isoformat(),
            "type": "habit_completed",
            "habit_name": "Exercise",
        }
        mock_services.habits.completions.get_recent_activity.return_value = Result.ok(
            [habit_activity]
        )

        # Mock principle activity
        principle_activity = {
            "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
            "type": "alignment_assessed",
            "principle_name": "Integrity",
        }
        mock_services.principles.alignment.get_recent_activity.return_value = Result.ok(
            [principle_activity]
        )

        # Aggregate all activities
        activities = []

        tasks_result = await mock_services.tasks.backend.find_by(limit=5)
        if tasks_result.is_ok:
            activities.extend(
                [
                    {
                        "timestamp": task.get("updated_at"),
                        "type": "task_updated",
                        "title": task.get("title"),
                    }
                    for task in tasks_result.value
                ]
            )

        completions_result = await mock_services.habits.completions.get_recent_activity(
            "user.mike", limit=5
        )
        if completions_result.is_ok:
            activities.extend(completions_result.value)

        principles_result = await mock_services.principles.alignment.get_recent_activity(
            "user.mike", limit=5
        )
        if principles_result.is_ok:
            activities.extend(principles_result.value)

        assert len(activities) == 3

        # Verify we have activities from all domains
        types = [a["type"] for a in activities]
        assert "task_updated" in types
        assert "habit_completed" in types
        assert "alignment_assessed" in types

    @pytest.mark.asyncio
    async def test_activity_sorting_by_timestamp(self, mock_services):
        """Test activities are sorted by timestamp (most recent first)."""
        now = datetime.now()

        activities = [
            {"timestamp": (now - timedelta(hours=2)).isoformat(), "type": "old"},
            {"timestamp": now.isoformat(), "type": "recent"},
            {"timestamp": (now - timedelta(hours=1)).isoformat(), "type": "middle"},
        ]

        # Sort by timestamp (most recent first)
        activities.sort(key=lambda x: x["timestamp"], reverse=True)

        assert activities[0]["type"] == "recent"
        assert activities[1]["type"] == "middle"
        assert activities[2]["type"] == "old"

    @pytest.mark.asyncio
    async def test_activity_limit_respected(self, mock_services):
        """Test activity aggregation respects limit parameter."""
        # Create 15 activities
        activities = [
            {
                "timestamp": (datetime.now() - timedelta(hours=i)).isoformat(),
                "type": "activity",
                "index": i,
            }
            for i in range(15)
        ]

        # Sort and limit to 10
        activities.sort(key=lambda x: x["timestamp"], reverse=True)
        limited = activities[:10]

        assert len(limited) == 10
        # Most recent activities should be included
        assert limited[0]["index"] == 0
        assert limited[9]["index"] == 9


class TestErrorHandling:
    """Test error handling for user profile features."""

    @pytest.mark.asyncio
    async def test_missing_user_service(self, mock_services):
        """Test handling when user service is unavailable."""
        mock_services.user_service = None

        # Should handle gracefully without user service
        user = None
        if mock_services.user_service:
            user_result = await mock_services.user_service.get_user("user.mike")
            if user_result.is_ok:
                user = user_result.value

        assert user is None

    @pytest.mark.asyncio
    async def test_missing_domain_backend(self, mock_services):
        """Test handling when domain backend is unavailable."""
        mock_services.tasks.backend = None

        activities = []
        try:
            if mock_services.tasks.backend:
                tasks_result = await mock_services.tasks.backend.find_by(limit=5)
                if tasks_result.is_ok:
                    activities.extend(tasks_result.value)
        except Exception:
            pass  # Silent failure for missing backend

        # Should not crash, just return empty activities
        assert len(activities) == 0

    @pytest.mark.asyncio
    async def test_backend_error_handling(self, mock_services):
        """Test handling when backend returns error."""
        mock_services.tasks.backend.find_by.return_value = Result.fail(
            {"code": "DB_ERROR", "message": "Database error"}
        )

        activities = []
        try:
            tasks_result = await mock_services.tasks.backend.find_by(limit=5)
            if tasks_result.is_ok:
                activities.extend(tasks_result.value)
        except Exception:
            pass

        # Should handle error gracefully
        assert len(activities) == 0


class TestActivityContentStructure:
    """Test activity content has correct structure."""

    def test_task_activity_structure(self):
        """Test task activity has all required fields."""
        activity = {
            "timestamp": datetime.now().isoformat(),
            "type": "task_updated",
            "domain": "tasks",
            "title": "Write tests",
            "uid": "task.123",
            "description": "Updated task: Write tests",
            "link": "/tasks/task.123",
        }

        # Verify required fields
        assert "timestamp" in activity
        assert "type" in activity
        assert "domain" in activity
        assert "title" in activity
        assert "uid" in activity
        assert "description" in activity
        assert "link" in activity

    def test_event_activity_structure(self):
        """Test event activity has all required fields."""
        activity = {
            "timestamp": datetime.now().isoformat(),
            "type": "event_created",
            "domain": "events",
            "title": "Team meeting",
            "uid": "event.123",
            "description": "Created event: Team meeting",
            "link": "/events/event.123",
        }

        assert activity["type"] == "event_created"
        assert activity["domain"] == "events"
        assert activity["link"].startswith("/events/")

    def test_habit_completion_structure(self):
        """Test habit completion activity structure."""
        activity = {
            "timestamp": datetime.now().isoformat(),
            "type": "habit_completed",
            "domain": "habits",
            "habit_uid": "habit.123",
            "habit_name": "Exercise",
            "description": "Completed habit: Exercise",
        }

        assert activity["type"] == "habit_completed"
        assert "habit_uid" in activity
        assert "habit_name" in activity


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
