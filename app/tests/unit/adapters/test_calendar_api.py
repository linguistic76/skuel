"""Smoke tests for calendar_api route handlers.

Calendar API routes had 0% coverage. We can't easily spin up the full FastHTML
app in unit tests, so we capture handlers through a fake `rt` decorator and
invoke them directly with a mocked CalendarServiceOperations.

CSRF is disabled via SKUEL_CSRF_ENFORCE=false (env override) so POST handlers
can be exercised without a token.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastcore.xml import to_xml  # type: ignore[import-untyped]

from adapters.inbound.calendar_api import create_calendar_api_routes
from core.models.event.calendar_models import CalendarItem, CalendarItemType
from core.utils.result_simplified import Errors, Result


def _render(response) -> str:
    """Render a FastHTML FT (or anything stringable) to HTML for substring checks.

    FastHTML FT components return their `id` from __str__ when one is set, so
    `_render(response)` is unreliable for content checks. `to_xml` always renders.
    """
    try:
        return to_xml(response)
    except Exception:
        return _render(response)


@pytest.fixture(autouse=True)
def _disable_csrf(monkeypatch) -> None:
    """csrf_protected reads env at call time — force enforcement off for unit tests."""
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")


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


def _make_request(json_body=None, form_data=None):
    """Minimal Starlette-like Request stub the handlers need."""
    request = SimpleNamespace()
    if json_body is not None:
        request.json = AsyncMock(return_value=json_body)
    if form_data is not None:
        request.form = AsyncMock(return_value=form_data)
    request.method = "POST"
    request.session = {"user_uid": "user_test"}  # routes now require an authenticated session
    return request


@pytest.fixture
def routes_and_service():
    registry = _RouteRegistry()
    service = AsyncMock()
    create_calendar_api_routes(app=None, rt=registry, calendar_service=service)
    return registry, service


# ============================================================================
# POST /api/calendar/quick-create
# ============================================================================


class TestQuickCreate:
    @pytest.mark.asyncio
    async def test_success_returns_item_payload(self, routes_and_service) -> None:
        registry, service = routes_and_service
        item = _make_calendar_item(title="Created via API")
        service.quick_create = AsyncMock(return_value=Result.ok(item))

        handler = registry.get("/api/calendar/quick-create", "POST")
        request = _make_request(
            json_body={
                "type": "event",
                "title": "Created via API",
                "start_time": "2026-05-20T10:00:00",
                "extras": {},
            }
        )
        response = await handler(request)

        # boundary_handler converts Result.ok to a JSONResponse with status 201.
        assert response.status_code == 201
        service.quick_create.assert_awaited_once()
        kwargs = service.quick_create.await_args.kwargs
        assert kwargs["item_type"] == "event"
        assert kwargs["title"] == "Created via API"
        assert kwargs["start_time"] == datetime(2026, 5, 20, 10, 0)

    @pytest.mark.asyncio
    async def test_invalid_body_returns_validation_failure(self, routes_and_service) -> None:
        registry, service = routes_and_service
        handler = registry.get("/api/calendar/quick-create", "POST")
        request = _make_request(json_body={"title": "missing type field"})

        response = await handler(request)
        assert response.status_code == 400
        service.quick_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_service_failure_propagates(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.quick_create = AsyncMock(
            return_value=Result.fail(Errors.business("calendar.full", "Day is full"))
        )

        handler = registry.get("/api/calendar/quick-create", "POST")
        request = _make_request(
            json_body={
                "type": "task",
                "title": "Won't fit",
                "start_time": "2026-05-20T10:00:00",
                "extras": {},
            }
        )
        response = await handler(request)
        # Errors.business → 422 via boundary_handler status_map
        assert response.status_code == 422


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
    async def test_service_error_returns_404(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.get_item = AsyncMock(return_value=Result.fail(Errors.database("get_item", "boom")))

        handler = registry.get("/api/v2/calendar/items/{item_id}", "GET")
        response = await handler(_make_request(), item_id="cal_event_1")
        # The handler treats any non-ok-with-value as not_found
        assert response.status_code == 404


# ============================================================================
# PATCH /api/events/calendar/reschedule
# ============================================================================


class TestRescheduleItem:
    @pytest.mark.asyncio
    async def test_success_sets_hx_refresh(self, routes_and_service) -> None:
        registry, service = routes_and_service
        item = _make_calendar_item(start_time=datetime(2026, 5, 21, 9, 0))
        service.reschedule_item = AsyncMock(return_value=Result.ok(item))

        handler = registry.get("/api/events/calendar/reschedule", "PATCH")
        request = _make_request(
            form_data={"uid": "cal_event_1", "new_start": "2026-05-21T09:00:00"}
        )
        response = await handler(request)
        assert response.headers.get("HX-Refresh") == "true"
        service.reschedule_item.assert_awaited_once_with(
            user_uid="user_test",
            item_uid="cal_event_1",
            new_start=datetime(2026, 5, 21, 9, 0),
        )

    @pytest.mark.asyncio
    async def test_missing_uid_returns_inline_error(self, routes_and_service) -> None:
        registry, service = routes_and_service
        handler = registry.get("/api/events/calendar/reschedule", "PATCH")
        request = _make_request(form_data={"new_start": "2026-05-21T09:00:00"})
        response = await handler(request)
        # Returns a Div(error) — render to string and check for the error text.
        assert "Missing item uid" in _render(response)
        service.reschedule_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_new_start_returns_inline_error(self, routes_and_service) -> None:
        registry, service = routes_and_service
        handler = registry.get("/api/events/calendar/reschedule", "PATCH")
        request = _make_request(form_data={"uid": "cal_event_1"})
        response = await handler(request)
        assert "Missing new_start" in _render(response)
        service.reschedule_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_service_failure_returns_inline_error(self, routes_and_service) -> None:
        registry, service = routes_and_service
        service.reschedule_item = AsyncMock(
            return_value=Result.fail(Errors.business("reschedule.locked", "Locked"))
        )
        handler = registry.get("/api/events/calendar/reschedule", "PATCH")
        request = _make_request(
            form_data={"uid": "cal_event_1", "new_start": "2026-05-21T09:00:00"}
        )
        response = await handler(request)
        assert "Failed to reschedule" in _render(response)


# ============================================================================
# Sanity: handlers were registered at the expected paths
# ============================================================================


def test_all_three_routes_registered(routes_and_service) -> None:
    registry, _ = routes_and_service
    assert ("/api/calendar/quick-create", "POST") in registry.handlers
    assert ("/api/v2/calendar/items/{item_id}", "GET") in registry.handlers
    assert ("/api/events/calendar/reschedule", "PATCH") in registry.handlers
