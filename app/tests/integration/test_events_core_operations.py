"""
Integration Test: Events Core Operations
========================================

Tests basic CRUD operations and core functionality for the Events domain.

This test suite verifies that:
1. Events can be created, retrieved, and listed
2. Events can be filtered by status, date, and type
3. Event business logic works correctly (timing, duration)
4. Event publishing works correctly

Test Coverage:
--------------
- EventsCoreService.create()
- EventsCoreService.get()
- EventsCoreService.list()
- Event business logic
- Event enum classifications
"""

from datetime import date, time, timedelta

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import KuStatus, Priority, Visibility
from core.models.ku.ku_event import EventKu
from core.services.events.events_core_service import EventsCoreService


@pytest.mark.asyncio
class TestEventsCoreOperations:
    """Integration tests for Events core CRUD operations."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def events_backend(self, neo4j_driver, clean_neo4j):
        """Create events backend with clean database."""
        return UniversalNeo4jBackend[EventKu](
            neo4j_driver, "Ku", EventKu, default_filters={"ku_type": "event"}
        )

    @pytest_asyncio.fixture
    async def events_service(self, events_backend, event_bus):
        """Create EventsCoreService with event bus."""
        return EventsCoreService(backend=events_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_events_core"

    # ==========================================================================
    # CRUD OPERATIONS TESTS (5 tests)
    # ==========================================================================

    async def test_create_event(self, events_service, test_user_uid):
        """Test creating a new event."""
        # Arrange
        today = date.today()
        event = EventKu(
            uid="event.team_meeting",
            user_uid=test_user_uid,
            title="Weekly Team Meeting",
            description="Discuss project progress and blockers",
            event_date=today + timedelta(days=1),
            start_time=time(14, 0),  # 2 PM
            end_time=time(15, 0),  # 3 PM
            event_type="WORK",
            status=KuStatus.SCHEDULED,
            priority=Priority.HIGH,
            location="Conference Room A",
        )

        # Act
        result = await events_service.create(event)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.uid == "event.team_meeting"
        assert created.title == "Weekly Team Meeting"
        assert created.event_type == "WORK"
        assert created.status == KuStatus.SCHEDULED
        assert created.priority == Priority.HIGH

    async def test_get_event_by_uid(self, events_service, test_user_uid):
        """Test retrieving an event by UID."""
        # Arrange - Create an event first
        event = EventKu(
            uid="event.get_test",
            user_uid=test_user_uid,
            title="Test Event for Retrieval",
            description="This event tests retrieval functionality",
            event_date=date.today(),
            status=KuStatus.SCHEDULED,
        )
        create_result = await events_service.create(event)
        assert create_result.is_ok

        # Act - Retrieve the event
        result = await events_service.get("event.get_test")

        # Assert
        assert result.is_ok
        retrieved = result.value
        assert retrieved.uid == "event.get_test"
        assert retrieved.title == "Test Event for Retrieval"

    async def test_get_nonexistent_event(self, events_service):
        """Test getting an event that doesn't exist."""
        # Act
        result = await events_service.get("event.nonexistent")

        # Assert
        assert result.is_error
        assert "not found" in result.error.message.lower()

    async def test_list_user_events(self, events_service, test_user_uid):
        """Test listing all events for a user."""
        # Arrange - Create multiple events
        today = date.today()
        events = [
            EventKu(
                uid=f"event.list_test_{i}",
                user_uid=test_user_uid,
                title=f"Test Event {i}",
                description=f"Description for event {i}",
                event_date=today + timedelta(days=i),
                status=KuStatus.SCHEDULED,
            )
            for i in range(3)
        ]

        for event in events:
            result = await events_service.create(event)
            assert result.is_ok

        # Act - List events
        result = await events_service.backend.find_by(user_uid=test_user_uid)

        # Assert
        assert result.is_ok
        user_events = result.value
        assert len(user_events) >= 3

    async def test_multiple_events_same_user(self, events_service, test_user_uid):
        """Test creating multiple events for the same user."""
        # Arrange & Act - Create 5 events
        today = date.today()
        for i in range(5):
            event = EventKu(
                uid=f"event.multi_{i}",
                user_uid=test_user_uid,
                title=f"Multi Event {i}",
                description=f"Multiple event {i}",
                event_date=today + timedelta(days=i),
                status=KuStatus.SCHEDULED,
            )
            result = await events_service.create(event)
            assert result.is_ok

        # Assert - Verify all were created
        list_result = await events_service.backend.find_by(user_uid=test_user_uid)
        assert list_result.is_ok
        assert len(list_result.value) >= 5

    # ==========================================================================
    # FILTERING TESTS (3 tests)
    # ==========================================================================

    async def test_filter_by_status(self, events_service, test_user_uid):
        """Test filtering events by status."""
        # Arrange - Create events with different statuses
        today = date.today()
        scheduled_event = EventKu(
            uid="event.scheduled",
            user_uid=test_user_uid,
            title="Scheduled Event",
            description="Upcoming event",
            event_date=today + timedelta(days=1),
            status=KuStatus.SCHEDULED,
        )
        completed_event = EventKu(
            uid="event.completed",
            user_uid=test_user_uid,
            title="Completed Event",
            description="Past event",
            event_date=today - timedelta(days=1),
            status=KuStatus.COMPLETED,
        )

        await events_service.create(scheduled_event)
        await events_service.create(completed_event)

        # Act - Filter by status
        scheduled_result = await events_service.backend.find_by(
            user_uid=test_user_uid, status=KuStatus.SCHEDULED.value
        )
        completed_result = await events_service.backend.find_by(
            user_uid=test_user_uid, status=KuStatus.COMPLETED.value
        )

        # Assert
        assert scheduled_result.is_ok
        assert len(scheduled_result.value) >= 1
        assert all(e.status == KuStatus.SCHEDULED for e in scheduled_result.value)

        assert completed_result.is_ok
        assert len(completed_result.value) >= 1
        assert all(e.status == KuStatus.COMPLETED for e in completed_result.value)

    async def test_filter_by_event_type(self, events_service, test_user_uid):
        """Test filtering events by type."""
        # Arrange - Create events with different types
        today = date.today()
        work_event = EventKu(
            uid="event.work_type",
            user_uid=test_user_uid,
            title="Work Event",
            description="Work-related meeting",
            event_date=today,
            event_type="WORK",
            status=KuStatus.SCHEDULED,
        )
        personal_event = EventKu(
            uid="event.personal_type",
            user_uid=test_user_uid,
            title="Personal Event",
            description="Personal appointment",
            event_date=today,
            event_type="PERSONAL",
            status=KuStatus.SCHEDULED,
        )

        await events_service.create(work_event)
        await events_service.create(personal_event)

        # Act - Filter by type
        work_result = await events_service.backend.find_by(
            user_uid=test_user_uid, event_type="WORK"
        )
        personal_result = await events_service.backend.find_by(
            user_uid=test_user_uid, event_type="PERSONAL"
        )

        # Assert
        assert work_result.is_ok
        assert len(work_result.value) >= 1
        assert all(e.event_type == "WORK" for e in work_result.value)

        assert personal_result.is_ok
        assert len(personal_result.value) >= 1
        assert all(e.event_type == "PERSONAL" for e in personal_result.value)

    async def test_filter_by_date_range(self, events_service, test_user_uid):
        """Test filtering events by date range."""
        # Arrange - Create events on different dates
        today = date.today()
        this_week_event = EventKu(
            uid="event.this_week",
            user_uid=test_user_uid,
            title="This Week Event",
            description="Event this week",
            event_date=today + timedelta(days=3),
            status=KuStatus.SCHEDULED,
        )
        next_month_event = EventKu(
            uid="event.next_month",
            user_uid=test_user_uid,
            title="Next Month Event",
            description="Event next month",
            event_date=today + timedelta(days=30),
            status=KuStatus.SCHEDULED,
        )

        await events_service.create(this_week_event)
        await events_service.create(next_month_event)

        # Act - Filter by date (events within 1 week)
        week_from_now = today + timedelta(days=7)
        result = await events_service.backend.find_by(
            user_uid=test_user_uid, event_date__lte=str(week_from_now)
        )

        # Assert
        assert result.is_ok
        assert len(result.value) >= 1
        # All returned events should have event_date <= week_from_now
        for event in result.value:
            if event.event_date:
                assert str(event.event_date) <= str(week_from_now)

    # ==========================================================================
    # BUSINESS LOGIC TESTS (4 tests)
    # ==========================================================================

    async def test_event_statuses(self, events_service, test_user_uid):
        """Test creating events with all status types."""
        # Arrange & Act - Create events with each status
        today = date.today()
        statuses = [
            KuStatus.SCHEDULED,
            KuStatus.ACTIVE,
            KuStatus.COMPLETED,
            KuStatus.CANCELLED,
        ]

        for status in statuses:
            event = EventKu(
                uid=f"event.status_{status.value}",
                user_uid=test_user_uid,
                title=f"Event with {status.value} status",
                description=f"Testing {status.value} status",
                event_date=today,
                status=status,
            )
            result = await events_service.create(event)
            assert result.is_ok
            assert result.value.status == status

    async def test_event_priorities(self, events_service, test_user_uid):
        """Test creating events with all priority types."""
        # Arrange & Act - Create events with each priority
        today = date.today()
        priorities = [
            Priority.LOW,
            Priority.MEDIUM,
            Priority.HIGH,
            Priority.CRITICAL,
        ]

        for priority in priorities:
            event = EventKu(
                uid=f"event.priority_{priority.value}",
                user_uid=test_user_uid,
                title=f"{priority.value.title()} Priority Event",
                description=f"Testing {priority.value} priority",
                event_date=today,
                priority=priority,
            )
            result = await events_service.create(event)
            assert result.is_ok
            assert result.value.priority == priority

    async def test_event_visibility_levels(self, events_service, test_user_uid):
        """Test creating events with different visibility levels."""
        # Arrange & Act - Create events with each visibility
        today = date.today()
        visibility_levels = [
            Visibility.PUBLIC,
            Visibility.PRIVATE,
            Visibility.SHARED,
        ]

        for visibility in visibility_levels:
            event = EventKu(
                uid=f"event.visibility_{visibility.value}",
                user_uid=test_user_uid,
                title=f"{visibility.value.title()} Event",
                description=f"Testing {visibility.value} visibility",
                event_date=today,
                visibility=visibility,
            )
            result = await events_service.create(event)
            assert result.is_ok
            assert result.value.visibility == visibility

    async def test_event_duration_calculation(self, events_service, test_user_uid):
        """Test event duration field is stored correctly."""
        # Arrange — duration_minutes is an explicit field, not auto-calculated
        event = EventKu(
            uid="event.with_duration",
            user_uid=test_user_uid,
            title="Event with Duration",
            description="Test duration storage",
            event_date=date.today(),
            start_time=time(14, 0),  # 2:00 PM
            end_time=time(15, 30),  # 3:30 PM
            duration_minutes=90,  # Explicitly set (1.5 hours)
            status=KuStatus.SCHEDULED,
        )

        # Act
        result = await events_service.create(event)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.duration_minutes == 90
        assert created.start_time == time(14, 0)
        assert created.end_time == time(15, 30)

    # ==========================================================================
    # EDGE CASES TESTS (3 tests)
    # ==========================================================================

    async def test_event_with_optional_fields(self, events_service, test_user_uid):
        """Test creating an event with optional fields populated."""
        # Arrange
        today = date.today()
        event = EventKu(
            uid="event.full_details",
            user_uid=test_user_uid,
            title="Fully Detailed Event",
            description="Complete event with all optional fields",
            event_date=today + timedelta(days=3),
            start_time=time(10, 0),
            end_time=time(11, 30),
            event_type="LEARNING",
            status=KuStatus.SCHEDULED,
            priority=Priority.HIGH,
            location="Main Conference Room",
            is_online=True,
            meeting_url="https://meet.example.com/abc123",
            tags=("important", "learning", "workshop"),
            attendee_emails=("alice@example.com", "bob@example.com"),
            max_attendees=20,
            reminder_minutes=30,
        )

        # Act
        result = await events_service.create(event)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.location == "Main Conference Room"
        assert created.is_online is True
        assert created.meeting_url == "https://meet.example.com/abc123"
        assert len(created.tags) == 3
        assert "important" in created.tags
        assert len(created.attendee_emails) == 2
        assert created.max_attendees == 20
        assert created.reminder_minutes == 30

    async def test_event_without_optional_fields(self, events_service, test_user_uid):
        """Test creating an event with minimal required fields."""
        # Arrange - Only required fields (EventKu forces ku_type=EVENT)
        event = EventKu(
            uid="event.minimal",
            user_uid=test_user_uid,
            title="Minimal Event",
            description=None,  # Optional
            event_date=date.today(),
        )

        # Act
        result = await events_service.create(event)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.description is None
        assert created.start_time is None
        assert created.end_time is None
        assert created.location is None
        # Check defaults are set
        assert created.event_type is None  # event_type has no default on EventKu
        assert created.status == KuStatus.SCHEDULED
        assert created.visibility == Visibility.PRIVATE

    async def test_online_event(self, events_service, test_user_uid):
        """Test creating an online event with meeting URL."""
        # Arrange
        event = EventKu(
            uid="event.online_meeting",
            user_uid=test_user_uid,
            title="Online Workshop",
            description="Virtual learning session",
            event_date=date.today() + timedelta(days=5),
            start_time=time(15, 0),
            end_time=time(16, 30),
            is_online=True,
            meeting_url="https://zoom.us/j/123456789",
            event_type="LEARNING",
            status=KuStatus.SCHEDULED,
        )

        # Act
        result = await events_service.create(event)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.is_online is True
        assert created.meeting_url == "https://zoom.us/j/123456789"
        assert created.location is None  # Online events may not have physical location
