"""Smoke tests for calendar_ui HTMX/UI route handlers.

We capture handlers through a fake `rt` decorator and exercise the HTMX content
fragments (month/week/day grids, where the service interaction happens) and the
item-details modal (the "read" code path).

Authentication is satisfied by attaching a fake `session` dict to requests.
We deliberately do not exercise the page-shell routes (`/cal/month/...`)
because they pull in the full sidebar-page template stack.
"""

from datetime import date, datetime
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


def _make_request(*, user_uid: str = "user_smoke", form_data=None):
    request = SimpleNamespace()
    request.session = {"user_uid": user_uid}
    request.url = SimpleNamespace(path="/test")
    request.method = "POST"  # the @csrf_protected POST handlers read request.method
    request.cookies = {}
    if form_data is not None:
        request.form = AsyncMock(return_value=form_data)
    return request


@pytest.fixture(autouse=True)
def _disable_csrf_enforcement(monkeypatch) -> None:
    """The @csrf_protected calendar handlers read enforcement state at call time;
    disable it so these handler-logic tests pass through (CSRF behaviour itself is
    covered by the csrf module's own tests)."""
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")


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
    create_calendar_ui_routes(
        _app=None, rt=registry, calendar_service=service, habits_service=AsyncMock()
    )
    return registry, service


@pytest.fixture
def routes_and_habits_service():
    registry = _RouteRegistry()
    habits_service = AsyncMock()
    create_calendar_ui_routes(
        _app=None, rt=registry, calendar_service=AsyncMock(), habits_service=habits_service
    )
    return registry, habits_service


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
        ("/cal/day/{date_str}", "GET"),
        ("/cal/day/{date_str}/content", "GET"),
        ("/cal/item-details/{item_id}", "GET"),
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
        service.get_calendar_view.assert_awaited_once()
        kwargs = service.get_calendar_view.await_args.kwargs
        assert kwargs["start_date"] == date(2026, 5, 1)
        assert kwargs["end_date"] == date(2026, 5, 31)
        assert kwargs["view_type"] == CalendarView.MONTH
        assert kwargs["user_uid"] == "user_smoke"

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
        assert "calendar-week-content" in _render(response)
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


class TestDayContentFragment:
    @pytest.mark.asyncio
    async def test_success(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_calendar_view = AsyncMock(return_value=Result.ok(_make_calendar_data()))
        handler = registry.get("/cal/day/{date_str}/content")
        response = await handler(_make_request(), date_str="2026-05-20")
        kwargs = service.get_calendar_view.await_args.kwargs
        assert kwargs["start_date"] == date(2026, 5, 20)
        assert kwargs["end_date"] == date(2026, 5, 20)
        assert kwargs["view_type"] == CalendarView.DAY
        assert "calendar-day-content" in _render(response)


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

    @pytest.mark.asyncio
    async def test_missing_returns_error_modal(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_item = AsyncMock(return_value=Result.ok(None))
        handler = registry.get("/cal/item-details/{item_id}")
        response = await handler(_make_request(), item_id="missing")
        assert "Calendar item not found" in _render(response)


# ============================================================================
# POST /cal/habit/{habit_uid}/complete — modal "Mark Complete" action
# ============================================================================


class TestHabitComplete:
    @pytest.mark.asyncio
    async def test_records_completion_and_swaps_button(self, routes_and_habits_service) -> None:
        registry, habits_service = routes_and_habits_service
        habits_service.core.verify_ownership = AsyncMock(return_value=Result.ok(object()))
        habits_service.completions.record_completion = AsyncMock(
            return_value=Result.ok(SimpleNamespace())
        )
        handler = registry.get("/cal/habit/{habit_uid}/complete", "POST")
        response = await handler(_make_request(), habit_uid="habit_1")

        assert "Completed" in _render(response)
        habits_service.completions.record_completion.assert_awaited_once_with(
            "habit_1", "user_smoke"
        )

    @pytest.mark.asyncio
    async def test_unowned_habit_returns_not_found(self, routes_and_habits_service) -> None:
        registry, habits_service = routes_and_habits_service
        habits_service.core.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Habit", identifier="habit_x"))
        )
        handler = registry.get("/cal/habit/{habit_uid}/complete", "POST")
        response = await handler(_make_request(), habit_uid="habit_x")

        assert response.status_code == 404
        habits_service.completions.record_completion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_completion_keeps_retry_button(self, routes_and_habits_service) -> None:
        registry, habits_service = routes_and_habits_service
        habits_service.core.verify_ownership = AsyncMock(return_value=Result.ok(object()))
        habits_service.completions.record_completion = AsyncMock(
            return_value=Result.fail(Errors.database("habits.complete", "boom"))
        )
        handler = registry.get("/cal/habit/{habit_uid}/complete", "POST")
        response = await handler(_make_request(), habit_uid="habit_1")

        rendered = _render(response)
        assert "try again" in rendered
        assert "/cal/habit/habit_1/complete" in rendered
