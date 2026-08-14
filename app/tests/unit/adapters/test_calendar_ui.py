"""Smoke tests for calendar_ui HTMX/UI route handlers.

We capture handlers through a fake `rt` decorator and exercise the HTMX content
fragments (month/week/day grids, where the service interaction happens) and the
item-details modal (the "read" code path).

Authentication is satisfied by attaching a fake `session` dict to requests.
We deliberately do not exercise the page-shell routes (`/cal/month/...`)
because they pull in the full sidebar-page template stack.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastcore.xml import to_xml  # type: ignore[import-untyped]

from adapters.inbound.calendar_ui import create_calendar_ui_routes
from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
    CalendarView,
)
from core.utils.result_simplified import Errors, Result
from tests.fixtures.csrf import attach_csrf


def _render(response) -> str:
    """Render a FastHTML FT to HTML — `str()` returns just the id if one is set."""
    try:
        return to_xml(response)
    except Exception:
        return _render(response)


# ============================================================================
# Test infrastructure
# ============================================================================


class _RouteRegistry:
    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], object] = {}

    def __call__(self, path: str, methods: list[str] | None = None):
        method = (methods[0] if methods else "GET").upper()

        def decorator(func):
            self.handlers[(path, method)] = func
            return func

        return decorator

    def get(self, path: str, method: str = "GET"):
        return self.handlers[(path, method.upper())]


def _make_request(*, user_uid: str = "user_smoke", form_data=None, query_params=None):
    request = SimpleNamespace()
    request.session = {"user_uid": user_uid}
    request.url = SimpleNamespace(path="/test")
    request.method = "POST"  # the @csrf_protected POST handlers read request.method
    request.cookies = {}
    request.query_params = query_params or {}
    request.form = AsyncMock(return_value=form_data if form_data is not None else {})
    return attach_csrf(request)


def _make_calendar_data(items=None) -> CalendarData:
    return CalendarData(
        items=items or [],
        occurrences={},
        view=CalendarView.MONTH,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        metadata={},
    )


def _make_calendar_item() -> CalendarItem:
    return CalendarItem(
        uid="cal_event_1",
        source_uid="event_1",
        item_type=CalendarItemType.EVENT,
        title="Smoke item",
        start_time=datetime(2026, 5, 20, 10, 0),
        end_time=datetime(2026, 5, 20, 11, 0),
    )


@pytest.fixture
def routes_and_service():
    registry = _RouteRegistry()
    service = AsyncMock()
    create_calendar_ui_routes(_app=None, rt=registry, calendar_service=service)
    return registry, service


# ============================================================================
# Route registration sanity
# ============================================================================


def test_expected_routes_are_registered(routes_and_service) -> None:
    registry, _ = routes_and_service
    expected = [
        ("/cal/month/{year}/{month}", "GET"),
        ("/cal/month/{year}/{month}/content", "GET"),
        ("/cal/week/{date_str}", "GET"),
        ("/cal/week/{date_str}/content", "GET"),
        ("/cal/item-details/{item_id}", "GET"),
        ("/cal/item/{item_id}/reschedule", "POST"),
        ("/cal/habit/{habit_uid}/complete", "POST"),
    ]
    for key in expected:
        assert key in registry.handlers, f"missing handler: {key}"


# ============================================================================
# HTMX content fragments — these read calendar data (the "list" code path)
# ============================================================================


class TestMonthContentFragment:
    @pytest.mark.asyncio
    async def test_success_renders_grid(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_calendar_view = AsyncMock(
            return_value=Result.ok(_make_calendar_data(items=[_make_calendar_item()]))
        )
        handler = registry.get("/cal/month/{year}/{month}/content")
        response = await handler(_make_request(), year=2026, month=5)

        rendered = _render(response)
        assert "calendar-month-content" in rendered
        # The fragment listens for the habit-complete POST's HX-Trigger event
        # so a recorded completion re-renders the grid.
        assert 'hx-trigger="calendar-refresh from:body"' in rendered
        service.get_calendar_view.assert_awaited_once()
        kwargs = service.get_calendar_view.await_args.kwargs
        # Full visible grid range: Monday on/before May 1 (Fri) through the
        # Sunday closing the last week (May 31 IS a Sunday in 2026).
        assert kwargs["start_date"] == date(2026, 4, 27)
        assert kwargs["end_date"] == date(2026, 5, 31)
        assert kwargs["view_type"] == CalendarView.MONTH
        assert kwargs["user_uid"] == "user_smoke"

    @pytest.mark.asyncio
    async def test_lead_in_day_items_render(self, routes_and_service) -> None:
        """Items on lead-in cells (previous month) render in the grid — the
        month view's edge cells must agree with the week view of those days."""
        registry, service = routes_and_service
        lead_in_item = CalendarItem(
            uid="cal_event_lead_in",
            source_uid="event_lead_in",
            item_type=CalendarItemType.EVENT,
            title="Lead-in item",
            start_time=datetime(2026, 4, 28, 10, 0),
            end_time=datetime(2026, 4, 28, 11, 0),
        )
        service.get_calendar_view = AsyncMock(
            return_value=Result.ok(
                CalendarData(
                    items=[lead_in_item],
                    occurrences={},
                    view=CalendarView.MONTH,
                    start_date=date(2026, 4, 27),
                    end_date=date(2026, 5, 31),
                    metadata={},
                )
            )
        )
        handler = registry.get("/cal/month/{year}/{month}/content")
        response = await handler(_make_request(), year=2026, month=5)
        assert "Lead-in item" in _render(response)

    @pytest.mark.asyncio
    async def test_failure_renders_error_response(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_calendar_view = AsyncMock(
            return_value=Result.fail(Errors.database("calendar.view", "boom"))
        )
        handler = registry.get("/cal/month/{year}/{month}/content")
        response = await handler(_make_request(), year=2026, month=5)
        # Wraps the error_response inside a Div with id="calendar-month-content"
        rendered = _render(response)
        assert "calendar-month-content" in rendered


class TestWeekContentFragment:
    @pytest.mark.asyncio
    async def test_success(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_calendar_view = AsyncMock(return_value=Result.ok(_make_calendar_data()))
        handler = registry.get("/cal/week/{date_str}/content")
        response = await handler(_make_request(), date_str="2026-05-20")
        rendered = _render(response)
        assert "calendar-week-content" in rendered
        assert 'hx-trigger="calendar-refresh from:body"' in rendered
        kwargs = service.get_calendar_view.await_args.kwargs
        assert kwargs["view_type"] == CalendarView.WEEK

    @pytest.mark.asyncio
    async def test_invalid_date_falls_back_to_today(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_calendar_view = AsyncMock(return_value=Result.ok(_make_calendar_data()))
        handler = registry.get("/cal/week/{date_str}/content")
        response = await handler(_make_request(), date_str="not-a-date")
        # Did not crash; service was still called.
        assert service.get_calendar_view.await_count == 1
        assert "calendar-week-content" in _render(response)


# ============================================================================
# /cal/item-details/{item_id} — the "read" code path
# ============================================================================


class TestItemDetailsModal:
    @pytest.mark.asyncio
    async def test_found_returns_modal(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_item = AsyncMock(return_value=Result.ok(_make_calendar_item()))
        handler = registry.get("/cal/item-details/{item_id}")
        response = await handler(_make_request(), item_id="cal_event_1")
        # Returns a modal containing the item title.
        assert "Smoke item" in _render(response)
        # No ?date= query param → the service receives no occurrence day.
        assert service.get_item.await_args.kwargs["on_date"] is None

    @pytest.mark.asyncio
    async def test_date_query_param_scopes_habit_to_that_day(self, routes_and_service) -> None:
        """?date=YYYY-MM-DD is parsed and handed to the service — the modal
        shows THAT day, never a server-side reconstruction from today."""
        registry, service = routes_and_service
        service.get_item = AsyncMock(return_value=Result.ok(_make_calendar_item()))
        handler = registry.get("/cal/item-details/{item_id}")
        await handler(_make_request(query_params={"date": "2026-05-19"}), item_id="habit-habit_1")
        service.get_item.assert_awaited_once_with(
            "user_smoke", "habit-habit_1", on_date=date(2026, 5, 19)
        )

    @pytest.mark.asyncio
    async def test_invalid_date_query_param_falls_back_to_none(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_item = AsyncMock(return_value=Result.ok(_make_calendar_item()))
        handler = registry.get("/cal/item-details/{item_id}")
        await handler(_make_request(query_params={"date": "not-a-date"}), item_id="habit-habit_1")
        assert service.get_item.await_args.kwargs["on_date"] is None

    @pytest.mark.asyncio
    async def test_missing_returns_error_modal(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_item = AsyncMock(return_value=Result.ok(None))
        handler = registry.get("/cal/item-details/{item_id}")
        response = await handler(_make_request(), item_id="missing")
        assert "Calendar item not found" in _render(response)


# ============================================================================
# POST /cal/item/{item_id}/reschedule — modal reschedule action (tasks/events)
# ============================================================================


def _rescheduled_task_item() -> CalendarItem:
    return CalendarItem(
        uid="task-task_1",
        source_uid="task_1",
        item_type=CalendarItemType.TASK,
        title="Rescheduled task",
        start_time=datetime(2026, 8, 14, 9, 0),
        end_time=datetime(2026, 8, 14, 10, 0),
    )


class TestItemReschedule:
    @pytest.mark.asyncio
    async def test_task_reschedule_moves_to_posted_date(self, routes_and_service) -> None:
        """The posted ``new_date`` is what gets rescheduled — tasks are
        date-only, so the service receives midnight of that day."""
        registry, service = routes_and_service
        service.reschedule_item = AsyncMock(return_value=Result.ok(_rescheduled_task_item()))
        handler = registry.get("/cal/item/{item_id}/reschedule", "POST")
        response = await handler(
            _make_request(form_data={"new_date": "2026-08-14"}), item_id="task-task_1"
        )

        service.reschedule_item.assert_awaited_once_with(
            "user_smoke", "task-task_1", datetime(2026, 8, 14, 0, 0)
        )
        body = response.body.decode()
        assert "Rescheduled ✓" in body
        # OOB schedule-line swap keeps the open modal truthful...
        assert 'id="item-schedule-text"' in body
        assert 'hx-swap-oob="true"' in body
        # ...and the HX-Trigger event re-renders the grid (the chip moves).
        assert response.headers["HX-Trigger"] == "calendar-refresh"

    @pytest.mark.asyncio
    async def test_event_reschedule_combines_date_and_time(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.reschedule_item = AsyncMock(return_value=Result.ok(_make_calendar_item()))
        handler = registry.get("/cal/item/{item_id}/reschedule", "POST")
        response = await handler(
            _make_request(form_data={"new_date": "2026-08-14", "new_time": "10:30"}),
            item_id="event-event_1",
        )

        service.reschedule_item.assert_awaited_once_with(
            "user_smoke", "event-event_1", datetime(2026, 8, 14, 10, 30)
        )
        assert response.headers["HX-Trigger"] == "calendar-refresh"

    @pytest.mark.asyncio
    async def test_event_missing_time_rejected(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.reschedule_item = AsyncMock(return_value=Result.ok(_make_calendar_item()))
        handler = registry.get("/cal/item/{item_id}/reschedule", "POST")
        response = await handler(
            _make_request(form_data={"new_date": "2026-08-14"}), item_id="event-event_1"
        )

        assert response.status_code == 400
        service.reschedule_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_date_rejected(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.reschedule_item = AsyncMock(return_value=Result.ok(_rescheduled_task_item()))
        handler = registry.get("/cal/item/{item_id}/reschedule", "POST")
        response = await handler(
            _make_request(form_data={"new_date": "not-a-date"}), item_id="task-task_1"
        )

        assert response.status_code == 400
        service.reschedule_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unowned_item_returns_not_found(self, routes_and_service) -> None:
        """Ownership is enforced in-service (not-found on non-owner, no UID
        oracle) — the route surfaces it as 404."""
        registry, service = routes_and_service
        service.reschedule_item = AsyncMock(
            return_value=Result.fail(Errors.not_found("Item not found: task-task_x"))
        )
        handler = registry.get("/cal/item/{item_id}/reschedule", "POST")
        response = await handler(
            _make_request(form_data={"new_date": "2026-08-14"}), item_id="task-task_x"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_habit_item_rejected(self, routes_and_service) -> None:
        """Habits recur — they don't reschedule. Rejected before the service."""
        registry, service = routes_and_service
        service.reschedule_item = AsyncMock(return_value=Result.ok(_rescheduled_task_item()))
        handler = registry.get("/cal/item/{item_id}/reschedule", "POST")
        response = await handler(
            _make_request(form_data={"new_date": "2026-08-14"}), item_id="habit-habit_1"
        )

        assert response.status_code == 400
        service.reschedule_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_validation_failure_renders_its_reason_in_the_form(
        self, routes_and_service
    ) -> None:
        """A service validation refusal (e.g. cross-midnight) must be SEEN:
        HTMX swaps 200 bodies, not bare 4xx, so the form re-renders with the
        actionable message."""
        registry, service = routes_and_service
        service.reschedule_item = AsyncMock(
            return_value=Result.fail(
                Errors.validation(
                    message="Event duration crosses midnight — choose an earlier start time",
                    field="new_start",
                )
            )
        )
        handler = registry.get("/cal/item/{item_id}/reschedule", "POST")
        response = await handler(
            _make_request(form_data={"new_date": "2026-08-12", "new_time": "23:30"}),
            item_id="event-event_1",
        )

        rendered = _render(response)
        assert "crosses midnight" in rendered
        assert "/cal/item/event-event_1/reschedule" in rendered
        # Posted values survive so the user adjusts rather than retypes.
        assert "2026-08-12" in rendered and "23:30" in rendered

    @pytest.mark.asyncio
    async def test_failed_reschedule_keeps_retry_form(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.reschedule_item = AsyncMock(
            return_value=Result.fail(Errors.database("calendar.reschedule", "boom"))
        )
        handler = registry.get("/cal/item/{item_id}/reschedule", "POST")
        response = await handler(
            _make_request(form_data={"new_date": "2026-08-14"}), item_id="task-task_1"
        )

        rendered = _render(response)
        assert "try again" in rendered
        # The re-rendered form re-posts to the same endpoint with the posted date.
        assert "/cal/item/task-task_1/reschedule" in rendered
        assert "2026-08-14" in rendered


# ============================================================================
# POST /cal/habit/{habit_uid}/complete — modal "Mark Complete" action
# ============================================================================


class TestHabitComplete:
    @pytest.mark.asyncio
    async def test_records_completion_for_posted_day(self, routes_and_service) -> None:
        """The posted ``on_date`` form field is what gets recorded — the loop
        closes on the day the user acted on, not on a server-side 'today'."""
        registry, service = routes_and_service
        service.record_habit_occurrence = AsyncMock(return_value=Result.ok(SimpleNamespace()))
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        handler = registry.get("/cal/habit/{habit_uid}/complete", "POST")
        response = await handler(
            _make_request(form_data={"on_date": yesterday}), habit_uid="habit_1"
        )

        body = response.body.decode()
        assert "Completed" in body
        # OOB day-state swap keeps the open modal truthful...
        assert 'hx-swap-oob="true"' in body
        assert 'id="habit-day-state"' in body
        # ...and the HX-Trigger event re-renders the grid (chip turns completed).
        assert response.headers["HX-Trigger"] == "calendar-refresh"
        service.record_habit_occurrence.assert_awaited_once_with("user_smoke", "habit_1", yesterday)

    @pytest.mark.asyncio
    async def test_unowned_habit_returns_not_found(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.record_habit_occurrence = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Habit", identifier="habit_x"))
        )
        handler = registry.get("/cal/habit/{habit_uid}/complete", "POST")
        response = await handler(
            _make_request(form_data={"on_date": date.today().isoformat()}), habit_uid="habit_x"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_future_date_rejected(self, routes_and_service) -> None:
        """Future-day completions are rejected server-side (the modal hides the
        button on future chips; this is the backstop)."""
        registry, service = routes_and_service
        service.record_habit_occurrence = AsyncMock(return_value=Result.ok(SimpleNamespace()))
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        handler = registry.get("/cal/habit/{habit_uid}/complete", "POST")
        response = await handler(
            _make_request(form_data={"on_date": tomorrow}), habit_uid="habit_1"
        )

        assert response.status_code == 400
        service.record_habit_occurrence.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_on_date_rejected(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.record_habit_occurrence = AsyncMock(return_value=Result.ok(SimpleNamespace()))
        handler = registry.get("/cal/habit/{habit_uid}/complete", "POST")
        response = await handler(_make_request(form_data={}), habit_uid="habit_1")

        assert response.status_code == 400
        service.record_habit_occurrence.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_completion_keeps_retry_button(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.record_habit_occurrence = AsyncMock(
            return_value=Result.fail(Errors.database("habits.complete", "boom"))
        )
        today_iso = date.today().isoformat()
        handler = registry.get("/cal/habit/{habit_uid}/complete", "POST")
        response = await handler(
            _make_request(form_data={"on_date": today_iso}), habit_uid="habit_1"
        )

        rendered = _render(response)
        assert "try again" in rendered
        assert "/cal/habit/habit_1/complete" in rendered
        # The retry button re-posts the same day.
        assert today_iso in rendered
