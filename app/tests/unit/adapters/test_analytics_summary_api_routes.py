"""Analytics Summary API security/wiring pins (adapters/inbound/analytics_summary_api.py).

Testing-gap roadmap item 6 (tranche 2, analytics/insight cluster): PIN tests
over the read-only Layer-3 analytics routes — auth gate (401), the strict
required-param guards (400 before the service), the end-before-start date
guard, and exact service args. Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.analytics_summary_api import create_analytics_summary_api_routes
from core.utils.result_simplified import Result

_USER_UID = "user_owner"


def _fake_auth(request: object) -> str:
    return _USER_UID


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    analytics: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    service = MagicMock()
    service.calculate_life_path_alignment = AsyncMock(
        return_value=Result.ok({"alignment_score": 0.4})
    )
    service.generate_weekly_life_summary = AsyncMock(return_value=Result.ok({"summary": "ok"}))
    service.generate_monthly_life_review = AsyncMock(return_value=Result.ok({"summary": "ok"}))
    service.generate_quarterly_progress = AsyncMock(return_value=Result.ok({"summary": "ok"}))
    service.generate_yearly_review = AsyncMock(return_value=Result.ok({"summary": "ok"}))
    service.detect_cross_domain_patterns = AsyncMock(return_value=Result.ok({"patterns": []}))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.analytics_summary_api.require_authenticated_user", _fake_auth
        )

    create_analytics_summary_api_routes(app, rt, service)
    return _Harness(client=TestClient(app), analytics=service)


class TestAuthGate:
    def test_alignment_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/analytics/life-path-alignment")

        assert response.status_code == 401
        harness.analytics.calculate_life_path_alignment.assert_not_awaited()


class TestAlignment:
    def test_scopes_to_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/analytics/life-path-alignment")

        assert response.status_code == 200
        harness.analytics.calculate_life_path_alignment.assert_awaited_once_with(_USER_UID)


class TestStrictParamGuards:
    def test_monthly_review_missing_year_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/analytics/monthly-life-review?month=3")

        assert response.status_code == 400
        harness.analytics.generate_monthly_life_review.assert_not_awaited()

    def test_quarterly_progress_rejects_quarter_5(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/analytics/quarterly-progress?year=2026&quarter=5")

        assert response.status_code == 400
        harness.analytics.generate_quarterly_progress.assert_not_awaited()

    def test_cross_domain_patterns_rejects_reversed_range(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(
            "/api/analytics/cross-domain-patterns?start_date=2026-07-10&end_date=2026-07-01"
        )

        assert response.status_code == 400
        harness.analytics.detect_cross_domain_patterns.assert_not_awaited()


class TestHappyPaths:
    def test_monthly_review_forwards_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/analytics/monthly-life-review?year=2026&month=7")

        assert response.status_code == 200
        harness.analytics.generate_monthly_life_review.assert_awaited_once_with(_USER_UID, 2026, 7)

    def test_cross_domain_patterns_forwards_parsed_dates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(
            "/api/analytics/cross-domain-patterns?start_date=2026-07-01&end_date=2026-07-10"
        )

        assert response.status_code == 200
        harness.analytics.detect_cross_domain_patterns.assert_awaited_once_with(
            _USER_UID, date(2026, 7, 1), date(2026, 7, 10)
        )

    def test_weekly_summary_forwards_explicit_start(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/analytics/weekly-life-summary?start_date=2026-07-13")

        assert response.status_code == 200
        harness.analytics.generate_weekly_life_summary.assert_awaited_once_with(
            _USER_UID, week_start=date(2026, 7, 13)
        )
