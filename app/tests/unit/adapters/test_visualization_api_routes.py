"""Visualization API security/wiring pins (adapters/inbound/visualization_api.py).

Testing-gap roadmap item 6 (tranche 2, analytics/insight cluster): PIN tests
over the Chart.js/Gantt data routes — auth gate (401) and the
January-2026 IDOR hardening: data is ALWAYS fetched for the authenticated
user; a ``user_uid`` query param must not select another user's data. Harness
mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.visualization_api import create_visualization_api_routes
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_GOAL_UID = "goal_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    vis: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    service = MagicMock()
    empty_chart = Result.ok({"type": "bar", "data": {}, "options": {}})
    service.get_completion_chart_data = AsyncMock(return_value=empty_chart)
    service.get_priority_distribution_chart_data = AsyncMock(return_value=empty_chart)
    service.get_streak_chart_data = AsyncMock(return_value=empty_chart)
    service.get_status_distribution_chart_data = AsyncMock(return_value=empty_chart)
    service.get_tasks_gantt_data = AsyncMock(return_value=Result.ok({"tasks": []}))
    service.get_goal_gantt_data = AsyncMock(return_value=Result.ok({"tasks": []}))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.visualization_api.require_authenticated_user", _fake_auth
        )

    create_visualization_api_routes(app, rt, service)
    return _Harness(client=TestClient(app), vis=service)


class TestAuthGate:
    def test_completion_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/visualizations/completion")

        assert response.status_code == 401
        harness.vis.get_completion_chart_data.assert_not_awaited()


class TestIdorHardening:
    def test_user_uid_param_cannot_select_another_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # January-2026 hardening pin: the route must ignore ?user_uid=... and
        # fetch for the AUTHENTICATED user only.
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/visualizations/completion?user_uid=user_victim")

        assert response.status_code == 200
        kwargs = harness.vis.get_completion_chart_data.await_args.kwargs
        assert kwargs["user_uid"] == _USER_UID


class TestChartRoutes:
    def test_completion_defaults_to_week_period(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/visualizations/completion")

        assert response.status_code == 200
        harness.vis.get_completion_chart_data.assert_awaited_once_with(
            user_uid=_USER_UID, period="week"
        )

    def test_streaks_scopes_to_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/visualizations/streaks")

        assert response.status_code == 200
        harness.vis.get_streak_chart_data.assert_awaited_once_with(user_uid=_USER_UID)


class TestGanttRoutes:
    def test_goal_gantt_forwards_goal_uid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(f"/api/visualizations/gantt/goal/{_GOAL_UID}")

        assert response.status_code == 200
        harness.vis.get_goal_gantt_data.assert_awaited_once_with(
            user_uid=_USER_UID, goal_uid=_GOAL_UID
        )
