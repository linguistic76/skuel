"""Smoke tests for calendar_api route handlers.

We can't easily spin up the full FastHTML app in unit tests, so we capture
handlers through a fake `rt` decorator and invoke them directly with a mocked
CalendarServiceOperations.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from adapters.inbound.calendar_api import create_calendar_api_routes
from core.models.event.calendar_models import CalendarItem, CalendarItemType
from core.utils.result_simplified import Errors, Result

# ============================================================================
# Test infrastructure — capturing routes
# ============================================================================


class _RouteRegistry:
    """Capture handlers registered via @rt(path, methods=...)."""

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


def _make_calendar_item(**overrides) -> CalendarItem:
    base = dict(
        uid="cal_event_1",
        source_uid="event_1",
        item_type=CalendarItemType.EVENT,
        title="Smoke test item",
        start_time=datetime(2026, 5, 20, 10, 0),
        end_time=datetime(2026, 5, 20, 11, 0),
    )
    base.update(overrides)
    return CalendarItem(**base)  # type: ignore[arg-type]


def _make_request():
    """Minimal Starlette-like Request stub the handlers need."""
    request = SimpleNamespace()
    request.method = "GET"
    request.session = {"user_uid": "user_test"}  # routes require an authenticated session
    return request


@pytest.fixture
def routes_and_service():
    registry = _RouteRegistry()
    service = AsyncMock()
    create_calendar_api_routes(app=None, rt=registry, calendar_service=service)
    return registry, service


# ============================================================================
# GET /api/v2/calendar/items/{item_id}
# ============================================================================


class TestGetCalendarItem:
    @pytest.mark.asyncio
    async def test_found_item_returns_full_payload(self, routes_and_service) -> None:
        registry, service = routes_and_service
        item = _make_calendar_item(
            description="Retrieved item",
            location="Room 302",
            tags=["smoke"],
            attendee_emails=("a@x.com", "b@x.com"),
        )
        service.get_item = AsyncMock(return_value=Result.ok(item))

        handler = registry.get("/api/v2/calendar/items/{item_id}", "GET")
        response = await handler(_make_request(), item_id="cal_event_1")
        assert response.status_code == 200

        # JSONResponse — read its body directly
        import json

        body = json.loads(response.body)
        assert body["uid"] == "cal_event_1"
        assert body["source_uid"] == "event_1"
        assert body["item_type"] == "event"
        assert body["title"] == "Smoke test item"
        assert body["description"] == "Retrieved item"
        assert body["attendee_count"] == 2
        assert body["location"] == "Room 302"
        assert body["tags"] == ["smoke"]

    @pytest.mark.asyncio
    async def test_missing_item_returns_404(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_item = AsyncMock(return_value=Result.ok(None))

        handler = registry.get("/api/v2/calendar/items/{item_id}", "GET")
        response = await handler(_make_request(), item_id="missing")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_service_error_propagates(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_item = AsyncMock(return_value=Result.fail(Errors.database("get_item", "boom")))

        handler = registry.get("/api/v2/calendar/items/{item_id}", "GET")
        response = await handler(_make_request(), item_id="cal_event_1")
        assert response.status_code == 503


# ============================================================================
# Sanity: handlers were registered at the expected paths
# ============================================================================


def test_routes_registered(routes_and_service) -> None:
    registry, _ = routes_and_service
    assert ("/api/v2/calendar/items/{item_id}", "GET") in registry.handlers
