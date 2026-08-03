"""Calendar v2 API security/wiring pins (adapters/inbound/calendar_api.py).

Testing-gap roadmap item 6 (tranche 2, system/infra cluster): TestClient pins
for the single JSON calendar route — auth gate (401), owner-scoped fetch
(service receives the AUTHENTICATED user), not-found 404, and the response
shape contract. Complements the handler-level smoke tests in
``test_calendar_api.py``; harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.calendar_api import create_calendar_api_routes
from core.models.event.calendar_models import CalendarItem, CalendarItemType
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_ITEM_UID = "calendar_item_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


def _item() -> CalendarItem:
    return CalendarItem(
        uid=_ITEM_UID,
        source_uid="task_1",
        item_type=CalendarItemType.TASK,
        title="Write essay",
        description="",
        start_time=datetime(2026, 7, 18, 9, 0),
        end_time=datetime(2026, 7, 18, 10, 0),
    )


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    calendar: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    calendar = MagicMock()
    calendar.get_item = AsyncMock(return_value=Result.ok(_item()))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.calendar_api.require_authenticated_user", _fake_auth)

    create_calendar_api_routes(app, rt, calendar)
    return _Harness(client=TestClient(app), calendar=calendar)


class TestAuthGate:
    def test_get_item_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get(f"/api/v2/calendar/items/{_ITEM_UID}")

        assert response.status_code == 401
        harness.calendar.get_item.assert_not_awaited()


class TestOwnerScoping:
    def test_fetch_scoped_to_authenticated_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(f"/api/v2/calendar/items/{_ITEM_UID}")

        assert response.status_code == 200
        harness.calendar.get_item.assert_awaited_once_with(_USER_UID, _ITEM_UID)

    def test_missing_item_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.calendar.get_item.return_value = Result.ok(None)

        response = harness.client.get(f"/api/v2/calendar/items/{_ITEM_UID}")

        assert response.status_code == 404


class TestResponseShape:
    def test_item_payload_contract(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(f"/api/v2/calendar/items/{_ITEM_UID}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["uid"] == _ITEM_UID
        assert payload["source_uid"] == "task_1"
        assert payload["item_type"] == CalendarItemType.TASK.value
        assert payload["start_time"] == "2026-07-18T09:00:00"
        assert payload["attendee_count"] == 0
