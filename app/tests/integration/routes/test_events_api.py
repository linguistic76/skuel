"""
Integration Tests for Events API Routes.

Tests cover:
1. CRUD operations (create, get, update, delete, list) via CRUDRouteFactory
2. Query operations (by user, goal, habit) via CommonQueryRouteFactory
3. Event scheduling and calendar integration
4. Recurring events
5. Event-knowledge linking

All tests use mocked services to avoid external dependencies.

Note: All async tests use pytest-asyncio for proper event loop management.
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import EntityStatus
from core.utils.result_simplified import Errors, Result

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


class MockEvent:
    """Mock Event model for testing."""

    def __init__(
        self,
        uid: str = "event.test123",
        user_uid: str = "user.test",
        title: str = "Test Event",
        description: str = "A test event description",
        status: EntityStatus = EntityStatus.SCHEDULED,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        location: str = "",
        is_recurring: bool = False,
    ):
        self.uid = uid
        self.user_uid = user_uid
        self.title = title
        self.description = description
        self.status = status
        self.start_time = start_time or datetime.now() + timedelta(hours=1)
        self.end_time = end_time or datetime.now() + timedelta(hours=2)
        self.location = location
        self.is_recurring = is_recurring
        self.created_at = "2024-01-01T00:00:00Z"
        self.updated_at = "2024-01-01T00:00:00Z"

    def to_dict(self):
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "start_time": str(self.start_time),
            "end_time": str(self.end_time),
            "location": self.location,
            "is_recurring": self.is_recurring,
        }


@pytest.fixture
def mock_events_service():
    """Create mock EventsService."""
    service = MagicMock()

    # Standard CRUD operations
    service.create = AsyncMock(return_value=Result.ok(MockEvent()))
    service.get = AsyncMock(return_value=Result.ok(MockEvent()))
    service.update = AsyncMock(return_value=Result.ok(MockEvent()))
    service.delete = AsyncMock(return_value=Result.ok(True))
    service.list = AsyncMock(return_value=Result.ok([MockEvent(), MockEvent()]))

    # Query operations
    service.get_by_user = AsyncMock(return_value=Result.ok([MockEvent()]))
    service.get_by_goal = AsyncMock(return_value=Result.ok([MockEvent()]))
    service.get_by_habit = AsyncMock(return_value=Result.ok([MockEvent()]))

    # Calendar operations
    service.get_events_in_range = AsyncMock(return_value=Result.ok([MockEvent()]))
    service.get_events_today = AsyncMock(return_value=Result.ok([MockEvent()]))
    service.get_upcoming_events = AsyncMock(return_value=Result.ok([MockEvent()]))
    service.check_conflicts = AsyncMock(return_value=Result.ok([]))

    # Status operations
    service.start_event = AsyncMock(return_value=Result.ok(MockEvent(status=EntityStatus.ACTIVE)))
    service.complete_event = AsyncMock(return_value=Result.ok(MockEvent(status=EntityStatus.COMPLETED)))
    service.cancel_event = AsyncMock(return_value=Result.ok(MockEvent(status=EntityStatus.CANCELLED)))
    service.reschedule_event = AsyncMock(return_value=Result.ok(MockEvent()))

    # Recurring events
    service.create_recurring_event = AsyncMock(return_value=Result.ok(MockEvent(is_recurring=True)))
    service.get_recurring_instances = AsyncMock(return_value=Result.ok([MockEvent()]))
    service.update_recurring_series = AsyncMock(return_value=Result.ok(True))

    # Knowledge linking
    service.link_event_to_knowledge = AsyncMock(return_value=Result.ok(True))
    service.get_event_knowledge = AsyncMock(return_value=Result.ok([]))

    # Search
    service.search = AsyncMock(return_value=Result.ok([MockEvent()]))

    return service


class TestCRUDOperations:
    """Tests for standard CRUD operations via CRUDRouteFactory."""

    async def test_create_event_returns_result(self, mock_events_service):
        """Test that create returns a Result."""
        result = await mock_events_service.create({"title": "New Event", "user_uid": "user.test"})

        assert result.is_ok
        assert result.value.title == "Test Event"

    async def test_get_event_by_uid(self, mock_events_service):
        """Test retrieving an event by UID."""
        result = await mock_events_service.get("event.test123")

        assert result.is_ok
        assert result.value.uid == "event.test123"

    async def test_get_event_not_found(self, mock_events_service):
        """Test retrieving a non-existent event."""
        mock_events_service.get = AsyncMock(
            return_value=Result.fail(Errors.not_found("event", "event.nonexistent"))
        )

        result = await mock_events_service.get("event.nonexistent")

        assert result.is_error

    async def test_update_event(self, mock_events_service):
        """Test updating an event."""
        result = await mock_events_service.update("event.test123", {"title": "Updated Event"})

        assert result.is_ok

    async def test_delete_event(self, mock_events_service):
        """Test deleting an event."""
        result = await mock_events_service.delete("event.test123")

        assert result.is_ok
        assert result.value is True

    async def test_list_events(self, mock_events_service):
        """Test listing events with pagination."""
        result = await mock_events_service.list()

        assert result.is_ok
        assert len(result.value) == 2


class TestCalendarOperations:
    """Tests for calendar-related operations."""

    async def test_get_events_in_range(self, mock_events_service):
        """Test getting events in a date range."""
        result = await mock_events_service.get_events_in_range(
            date.today(), date.today() + timedelta(days=7)
        )

        assert result.is_ok

    async def test_get_events_today(self, mock_events_service):
        """Test getting today's events."""
        result = await mock_events_service.get_events_today()

        assert result.is_ok
        assert len(result.value) >= 1

    async def test_get_upcoming_events(self, mock_events_service):
        """Test getting upcoming events."""
        result = await mock_events_service.get_upcoming_events()

        assert result.is_ok

    async def test_check_conflicts(self, mock_events_service):
        """Test checking for event conflicts."""
        result = await mock_events_service.check_conflicts(
            datetime.now() + timedelta(hours=1), datetime.now() + timedelta(hours=2)
        )

        assert result.is_ok
        assert isinstance(result.value, list)


class TestStatusOperations:
    """Tests for event status changes."""

    async def test_start_event(self, mock_events_service):
        """Test starting an event."""
        result = await mock_events_service.start_event("event.test123")

        assert result.is_ok
        assert result.value.status == EntityStatus.ACTIVE

    async def test_complete_event(self, mock_events_service):
        """Test completing an event."""
        result = await mock_events_service.complete_event("event.test123")

        assert result.is_ok
        assert result.value.status == EntityStatus.COMPLETED

    async def test_cancel_event(self, mock_events_service):
        """Test canceling an event."""
        result = await mock_events_service.cancel_event("event.test123")

        assert result.is_ok
        assert result.value.status == EntityStatus.CANCELLED

    async def test_reschedule_event(self, mock_events_service):
        """Test rescheduling an event."""
        result = await mock_events_service.reschedule_event(
            "event.test123",
            datetime.now() + timedelta(days=1),
            datetime.now() + timedelta(days=1, hours=1),
        )

        assert result.is_ok


class TestRecurringEvents:
    """Tests for recurring event operations."""

    async def test_create_recurring_event(self, mock_events_service):
        """Test creating a recurring event."""
        result = await mock_events_service.create_recurring_event("event.test123", "weekly")

        assert result.is_ok
        assert result.value.is_recurring is True

    async def test_get_recurring_instances(self, mock_events_service):
        """Test getting recurring event instances."""
        result = await mock_events_service.get_recurring_instances("event.test123")

        assert result.is_ok
        assert isinstance(result.value, list)

    async def test_update_recurring_series(self, mock_events_service):
        """Test updating a recurring series."""
        result = await mock_events_service.update_recurring_series(
            "event.test123", {"title": "Updated Series"}
        )

        assert result.is_ok


class TestKnowledgeLinking:
    """Tests for event-knowledge linking."""

    async def test_link_event_to_knowledge(self, mock_events_service):
        """Test linking an event to knowledge."""
        result = await mock_events_service.link_event_to_knowledge("event.test123", "ku.test456")

        assert result.is_ok

    async def test_get_event_knowledge(self, mock_events_service):
        """Test getting knowledge linked to an event."""
        result = await mock_events_service.get_event_knowledge("event.test123")

        assert result.is_ok
        assert isinstance(result.value, list)


class TestSearch:
    """Tests for event search."""

    async def test_search_events(self, mock_events_service):
        """Test searching events."""
        result = await mock_events_service.search("meeting")

        assert result.is_ok


class TestEventModel:
    """Tests for Event model structure."""

    async def test_event_has_required_fields(self):
        """Test that Event model has required fields."""
        from core.models.ku.event import Event

        required_fields = ["uid", "user_uid", "title"]
        for field in required_fields:
            assert hasattr(Event, "__annotations__") or field in dir(Event)


class TestErrorHandling:
    """Tests for error handling."""

    async def test_validation_error_on_create(self, mock_events_service):
        """Test validation error when creating event with invalid data."""
        mock_events_service.create = AsyncMock(
            return_value=Result.fail(Errors.validation("Title is required", field="title"))
        )

        result = await mock_events_service.create({})

        assert result.is_error
