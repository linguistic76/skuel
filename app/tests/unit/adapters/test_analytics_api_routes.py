"""Analytics API security/wiring pins (adapters/inbound/analytics_api.py).

Testing-gap roadmap item 6 (tranche 2, analytics/insight cluster): PIN tests
over the cross-domain analytics routes — auth gate (401), the days_back
clamp, response shaping from the metrics objects, and exact service args.
Note this factory has the ``register_analytics_routes(app, services)``
signature (reads ``services.cross_domain_analytics`` and ``app.route``).
Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.analytics_api import register_analytics_routes
from core.utils.result_simplified import Result

_USER_UID = "user_owner"


def _fake_auth(request: object) -> str:
    return _USER_UID


def _velocity_metrics() -> MagicMock:
    metrics = MagicMock()
    metrics.user_uid = _USER_UID
    metrics.period_days = 30
    metrics.kus_mastered_per_week = 1.5
    metrics.paths_completed = 2
    metrics.total_learning_hours = 12.0
    metrics.velocity_trend = "steady"
    metrics.compared_to_previous_period = 10.0
    return metrics


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    analytics: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, _rt = fast_app(pico=False, default_hdrs=False)

    analytics = MagicMock()
    analytics.get_learning_velocity = AsyncMock(return_value=Result.ok(_velocity_metrics()))
    analytics.get_productivity_metrics = AsyncMock(
        return_value=Result.ok(
            {
                "user_uid": _USER_UID,
                "tasks_completed": 7,
                "first_completion_at": None,
                "last_completion_at": None,
                "velocity_window_days": 30,
                "tasks_completed_in_window": 5,
                "completion_velocity": 1.17,
            }
        )
    )
    analytics.get_habit_consistency = AsyncMock(
        return_value=Result.ok(
            {
                "user_uid": _USER_UID,
                "total_completions": 3,
                "first_completion_at": None,
                "last_completion_at": None,
                "consistency_window_days": 30,
                "completions_in_window": 2,
                "consistency_score": 0.47,
            }
        )
    )
    analytics.get_combined_dashboard = AsyncMock(return_value=Result.ok({"widgets": []}))

    services = MagicMock()
    services.cross_domain_analytics = analytics

    if authenticated:
        monkeypatch.setattr("adapters.inbound.analytics_api.require_authenticated_user", _fake_auth)

    register_analytics_routes(app, services)
    return _Harness(client=TestClient(app), analytics=analytics)


class TestAuthGate:
    def test_learning_velocity_unauthenticated_is_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/analytics/learning-velocity")

        assert response.status_code == 401
        harness.analytics.get_learning_velocity.assert_not_awaited()


class TestLearningVelocity:
    def test_defaults_and_response_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/analytics/learning-velocity")

        assert response.status_code == 200
        payload = response.json()
        assert payload["kus_mastered_per_week"] == 1.5
        assert payload["velocity_trend"] == "steady"
        harness.analytics.get_learning_velocity.assert_awaited_once_with(_USER_UID, 30)

    def test_days_back_clamped_to_365(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/analytics/learning-velocity?days_back=9999")

        assert response.status_code == 200
        harness.analytics.get_learning_velocity.assert_awaited_once_with(_USER_UID, 365)


class TestProductivity:
    def test_response_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/analytics/productivity")

        assert response.status_code == 200
        payload = response.json()
        assert payload["tasks_completed"] == 7
        assert payload["first_completion_at"] is None
        harness.analytics.get_productivity_metrics.assert_awaited_once_with(_USER_UID)

    def test_the_velocity_window_is_served_with_the_rate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tasks/week figure is uninterpretable without the window it spans.

        ``completion_velocity`` is a rate over a fixed trailing window, not a
        lifetime average, and the derived ``tasks_completed`` beside it is a
        different quantity entirely — 7 currently completed, 5 of them recent,
        1.17 per week. Serving the rate alone invited exactly the confusion the
        old first→last denominator hid behind.
        """
        harness = _make_harness(monkeypatch)

        payload = harness.client.get("/api/analytics/productivity").json()

        assert payload["velocity_window_days"] == 30
        assert payload["tasks_completed_in_window"] == 5
        assert payload["completion_velocity"] == 1.17


class TestDashboard:
    def test_dashboard_forwards_days_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/analytics/dashboard?days_back=14")

        assert response.status_code == 200
        harness.analytics.get_combined_dashboard.assert_awaited_once_with(_USER_UID, 14)
