"""
Unit tests for EventsEventHandlerService.

Tests cover:
- handle_event_completed: attendance tracking, goal alignment
- handle_event_rescheduled: rescheduling pattern detection
- handle_event_created: scheduling density monitoring
- Fire-and-forget contract: exceptions logged, never propagated
- Module-level helpers: _classify_rescheduling_pattern, _assess_scheduling_density
"""

from datetime import date, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.events.calendar_event_events import (
    CalendarEventCompleted,
    CalendarEventCreated,
    CalendarEventRescheduled,
)
from core.models.event.event import Event
from core.services.events.events_event_handler_service import (
    EventsEventHandlerService,
    _assess_scheduling_density,
    _classify_rescheduling_pattern,
)
from core.utils.result_simplified import Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_backend() -> Mock:
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.update = AsyncMock(return_value=Result.ok({}))
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.execute_query = AsyncMock(return_value=Result.ok([{"reschedule_count": 0}]))
    return backend


@pytest.fixture
def mock_relationships() -> AsyncMock:
    rels = AsyncMock()
    rels.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return rels


@pytest.fixture
def service(mock_backend: Mock) -> EventsEventHandlerService:
    return EventsEventHandlerService(backend=mock_backend)


@pytest.fixture
def service_with_rels(
    mock_backend: Mock, mock_relationships: AsyncMock
) -> EventsEventHandlerService:
    return EventsEventHandlerService(
        backend=mock_backend, relationship_service=mock_relationships
    )


def _make_event(
    uid: str = "event_test_abc",
    title: str = "Test Event",
    event_date: date | None = None,
) -> Mock:
    """Create a mock event with given attributes."""
    event = Mock(spec=Event)
    event.uid = uid
    event.title = title
    event.event_date = event_date or date(2026, 3, 20)
    return event


# ---------------------------------------------------------------------------
# Module-level helper tests
# ---------------------------------------------------------------------------


class TestClassifyReschedulingPattern:
    def test_rare_zero(self):
        assert _classify_rescheduling_pattern(0) == "rare"

    def test_rare_one(self):
        assert _classify_rescheduling_pattern(1) == "rare"

    def test_occasional_two(self):
        assert _classify_rescheduling_pattern(2) == "occasional"

    def test_occasional_three(self):
        assert _classify_rescheduling_pattern(3) == "occasional"

    def test_chronic_four(self):
        assert _classify_rescheduling_pattern(4) == "chronic"

    def test_chronic_high(self):
        assert _classify_rescheduling_pattern(10) == "chronic"


class TestAssessSchedulingDensity:
    def test_light(self):
        assert _assess_scheduling_density(2) == "light"

    def test_light_boundary(self):
        assert _assess_scheduling_density(3) == "light"

    def test_moderate(self):
        assert _assess_scheduling_density(5) == "moderate"

    def test_moderate_boundary(self):
        assert _assess_scheduling_density(7) == "moderate"

    def test_heavy(self):
        assert _assess_scheduling_density(10) == "heavy"

    def test_heavy_boundary(self):
        assert _assess_scheduling_density(12) == "heavy"

    def test_overcommitted(self):
        assert _assess_scheduling_density(13) == "overcommitted"

    def test_overcommitted_high(self):
        assert _assess_scheduling_density(20) == "overcommitted"


# ---------------------------------------------------------------------------
# handle_event_completed tests
# ---------------------------------------------------------------------------


class TestHandleEventCompleted:
    @pytest.mark.asyncio
    async def test_attendance_tracking_logged(
        self, service: EventsEventHandlerService
    ):
        """Attendance time-of-day pattern is logged."""
        event = CalendarEventCompleted(
            event_uid="event_test_abc",
            user_uid="user_mike",
            completion_date=date(2026, 3, 20),
            quality_score=8,
            occurred_at=datetime(2026, 3, 20, 14, 30),
        )

        with patch.object(service.logger, "info") as mock_log:
            await service.handle_event_completed(event)
            log_calls = [c for c in mock_log.call_args_list if "afternoon" in str(c)]
            assert len(log_calls) == 1

    @pytest.mark.asyncio
    async def test_morning_time_slot(self, service: EventsEventHandlerService):
        """Morning events are classified correctly."""
        event = CalendarEventCompleted(
            event_uid="event_test_abc",
            user_uid="user_mike",
            completion_date=date(2026, 3, 20),
            quality_score=None,
            occurred_at=datetime(2026, 3, 20, 9, 0),
        )

        with patch.object(service.logger, "info") as mock_log:
            await service.handle_event_completed(event)
            log_calls = [c for c in mock_log.call_args_list if "morning" in str(c)]
            assert len(log_calls) == 1

    @pytest.mark.asyncio
    async def test_goal_alignment_with_relationships(
        self,
        service_with_rels: EventsEventHandlerService,
        mock_relationships: AsyncMock,
    ):
        """Goal alignment is checked when relationship service available."""
        mock_relationships.get_related_uids.return_value = Result.ok(["goal_test_123"])

        event = CalendarEventCompleted(
            event_uid="event_test_abc",
            user_uid="user_mike",
            completion_date=date(2026, 3, 20),
            quality_score=None,
            occurred_at=datetime(2026, 3, 20, 14, 0),
        )

        with patch.object(service_with_rels.logger, "info") as mock_log:
            await service_with_rels.handle_event_completed(event)
            log_calls = [c for c in mock_log.call_args_list if "goal" in str(c).lower()]
            assert len(log_calls) >= 1

    @pytest.mark.asyncio
    async def test_goal_alignment_without_relationships(
        self, service: EventsEventHandlerService
    ):
        """No goal check when relationship service absent."""
        event = CalendarEventCompleted(
            event_uid="event_test_abc",
            user_uid="user_mike",
            completion_date=date(2026, 3, 20),
            quality_score=None,
            occurred_at=datetime(2026, 3, 20, 14, 0),
        )

        # Should not raise
        await service.handle_event_completed(event)

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: EventsEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.execute_query.side_effect = ServiceUnavailable("connection lost")

        event = CalendarEventCompleted(
            event_uid="event_test_abc",
            user_uid="user_mike",
            completion_date=date(2026, 3, 20),
            quality_score=None,
            occurred_at=datetime(2026, 3, 20, 14, 0),
        )

        # Should NOT raise
        await service.handle_event_completed(event)


# ---------------------------------------------------------------------------
# handle_event_rescheduled tests
# ---------------------------------------------------------------------------


class TestHandleEventRescheduled:
    @pytest.mark.asyncio
    async def test_rescheduling_pattern_logged(
        self, service: EventsEventHandlerService, mock_backend: Mock
    ):
        """Rescheduling pattern is detected and logged."""
        mock_backend.execute_query.return_value = Result.ok([{"reschedule_count": 2}])

        event = CalendarEventRescheduled(
            event_uid="event_test_abc",
            user_uid="user_mike",
            old_date=date(2026, 3, 20),
            new_date=date(2026, 3, 25),
            occurred_at=datetime(2026, 3, 19, 10, 0),
        )

        with patch.object(service.logger, "info") as mock_log:
            await service.handle_event_rescheduled(event)
            log_calls = [c for c in mock_log.call_args_list if "occasional" in str(c)]
            assert len(log_calls) == 1

    @pytest.mark.asyncio
    async def test_chronic_rescheduling_warning(
        self, service: EventsEventHandlerService, mock_backend: Mock
    ):
        """Chronic rescheduling triggers a warning."""
        mock_backend.execute_query.return_value = Result.ok([{"reschedule_count": 5}])

        event = CalendarEventRescheduled(
            event_uid="event_test_abc",
            user_uid="user_mike",
            old_date=date(2026, 3, 20),
            new_date=date(2026, 3, 25),
            occurred_at=datetime(2026, 3, 19, 10, 0),
        )

        with patch.object(service.logger, "warning") as mock_warn:
            await service.handle_event_rescheduled(event)
            warn_calls = [c for c in mock_warn.call_args_list if "chronic" in str(c).lower()]
            assert len(warn_calls) >= 1

    @pytest.mark.asyncio
    async def test_rare_rescheduling_no_warning(
        self, service: EventsEventHandlerService, mock_backend: Mock
    ):
        """Rare rescheduling does not trigger a warning."""
        mock_backend.execute_query.return_value = Result.ok([{"reschedule_count": 1}])

        event = CalendarEventRescheduled(
            event_uid="event_test_abc",
            user_uid="user_mike",
            old_date=date(2026, 3, 20),
            new_date=date(2026, 3, 22),
            occurred_at=datetime(2026, 3, 19, 10, 0),
        )

        with patch.object(service.logger, "warning") as mock_warn:
            await service.handle_event_rescheduled(event)
            assert mock_warn.call_count == 0

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: EventsEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.execute_query.side_effect = ServiceUnavailable("connection lost")

        event = CalendarEventRescheduled(
            event_uid="event_test_abc",
            user_uid="user_mike",
            old_date=date(2026, 3, 20),
            new_date=date(2026, 3, 25),
            occurred_at=datetime(2026, 3, 19, 10, 0),
        )

        # Should NOT raise
        await service.handle_event_rescheduled(event)


# ---------------------------------------------------------------------------
# handle_event_created tests
# ---------------------------------------------------------------------------


class TestHandleEventCreated:
    @pytest.mark.asyncio
    async def test_scheduling_density_logged(
        self, service: EventsEventHandlerService, mock_backend: Mock
    ):
        """Scheduling density is assessed and logged."""
        mock_backend.execute_query.return_value = Result.ok([{"event_count": 5}])

        event = CalendarEventCreated(
            event_uid="event_test_abc",
            user_uid="user_mike",
            title="Team Meeting",
            event_date=date(2026, 3, 20),
            calendar_event_type="meeting",
            occurred_at=datetime(2026, 3, 20, 9, 0),
        )

        with patch.object(service.logger, "info") as mock_log:
            await service.handle_event_created(event)
            log_calls = [c for c in mock_log.call_args_list if "moderate" in str(c)]
            assert len(log_calls) == 1

    @pytest.mark.asyncio
    async def test_overcommitment_warning(
        self, service: EventsEventHandlerService, mock_backend: Mock
    ):
        """Overcommitment triggers a warning."""
        mock_backend.execute_query.return_value = Result.ok([{"event_count": 15}])

        event = CalendarEventCreated(
            event_uid="event_test_abc",
            user_uid="user_mike",
            title="Another Meeting",
            event_date=date(2026, 3, 20),
            calendar_event_type="meeting",
            occurred_at=datetime(2026, 3, 20, 9, 0),
        )

        with patch.object(service.logger, "warning") as mock_warn:
            await service.handle_event_created(event)
            warn_calls = [
                c for c in mock_warn.call_args_list if "overcommit" in str(c).lower()
            ]
            assert len(warn_calls) >= 1

    @pytest.mark.asyncio
    async def test_light_density_no_warning(
        self, service: EventsEventHandlerService, mock_backend: Mock
    ):
        """Light scheduling does not trigger a warning."""
        mock_backend.execute_query.return_value = Result.ok([{"event_count": 2}])

        event = CalendarEventCreated(
            event_uid="event_test_abc",
            user_uid="user_mike",
            title="Quick Sync",
            event_date=date(2026, 3, 20),
            calendar_event_type="meeting",
            occurred_at=datetime(2026, 3, 20, 9, 0),
        )

        with patch.object(service.logger, "warning") as mock_warn:
            await service.handle_event_created(event)
            assert mock_warn.call_count == 0

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: EventsEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.execute_query.side_effect = ServiceUnavailable("connection lost")

        event = CalendarEventCreated(
            event_uid="event_test_abc",
            user_uid="user_mike",
            title="Meeting",
            event_date=date(2026, 3, 20),
            calendar_event_type="meeting",
            occurred_at=datetime(2026, 3, 20, 9, 0),
        )

        # Should NOT raise
        await service.handle_event_created(event)
