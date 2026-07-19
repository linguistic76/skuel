"""Insights API security/wiring pins (adapters/inbound/insights_api.py).

Testing-gap roadmap item 6 (tranche 2, analytics/insight cluster): PIN tests
over the insight lifecycle routes — auth gate (401), CSRF on mutations (403),
body guards refusing before the store (400), the details-route ownership rule
(foreign insight → 404, no field leak), and exact store args on dismiss /
bulk / snooze (note: snooze currently just dismisses — pinned as-is). Harness
mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.insights_api import create_insights_api_routes
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_INSIGHT_UID = "insight_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    store: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    store = MagicMock()
    store.dismiss_insight = AsyncMock(return_value=Result.ok(True))
    store.mark_actioned = AsyncMock(return_value=Result.ok(True))
    store.bulk_dismiss = AsyncMock(return_value=Result.ok({"dismissed": 2}))
    store.bulk_mark_actioned = AsyncMock(return_value=Result.ok({"actioned": 2}))
    store.smart_dismiss = AsyncMock(return_value=Result.ok({"dismissed": 1}))
    store.get_active_insights = AsyncMock(return_value=Result.ok([]))
    store.get_insight_stats = AsyncMock(return_value=Result.ok({"total": 0}))
    foreign_insight = MagicMock()
    foreign_insight.user_uid = "user_other"
    store.get_insight_by_uid = AsyncMock(return_value=Result.ok(foreign_insight))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.insights_api.require_authenticated_user", _fake_auth)

    create_insights_api_routes(None, rt, store)
    return _Harness(client=TestClient(app), store=store)


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


class TestAuthGate:
    def test_dismiss_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = _post_json(harness.client, f"/api/insights/{_INSIGHT_UID}/dismiss", {})

        assert response.status_code == 401
        harness.store.dismiss_insight.assert_not_awaited()


class TestCsrfEnforcement:
    def test_dismiss_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(f"/api/insights/{_INSIGHT_UID}/dismiss")

        assert response.status_code == 403
        harness.store.dismiss_insight.assert_not_awaited()


class TestDismiss:
    def test_dismiss_forwards_notes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            f"/api/insights/{_INSIGHT_UID}/dismiss",
            {"notes": "not relevant"},
        )

        assert response.status_code == 200
        # Result[FT] fragments render as HTML (boundary FT branch) — this
        # 500'd before the fix.
        assert "Insight dismissed" in response.text
        harness.store.dismiss_insight.assert_awaited_once_with(
            _INSIGHT_UID, _USER_UID, notes="not relevant"
        )

    def test_dismiss_without_body_defaults_to_empty_notes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        token = mint_token()
        harness.client.cookies.set(CSRF_COOKIE_NAME, token)
        response = harness.client.post(
            f"/api/insights/{_INSIGHT_UID}/dismiss", headers={CSRF_HEADER_NAME: token}
        )

        assert response.status_code == 200
        harness.store.dismiss_insight.assert_awaited_once_with(_INSIGHT_UID, _USER_UID, notes="")


class TestBulkActions:
    def test_bulk_dismiss_forwards_uids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Shadowing regression pin: before the registration-order fix,
        # /api/insights/bulk/dismiss matched /{uid}/dismiss with uid="bulk"
        # and the bulk handler was unreachable.
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/insights/bulk/dismiss", {"uids": ["i1", "i2"]})

        assert response.status_code == 200
        harness.store.bulk_dismiss.assert_awaited_once_with(["i1", "i2"], _USER_UID)

    def test_bulk_dismiss_empty_uids_refuses_before_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/insights/bulk/dismiss", {"uids": []})

        assert response.status_code == 400
        harness.store.bulk_dismiss.assert_not_awaited()

    def test_smart_dismiss_forwards_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            "/api/insights/bulk/smart-dismiss",
            {"filter_type": "impact", "filter_value": "low"},
        )

        assert response.status_code == 200
        harness.store.smart_dismiss.assert_awaited_once_with(_USER_UID, "impact", "low")


class TestDetailsOwnership:
    def test_foreign_insight_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The store returns an insight owned by another user — the route must
        # 404 without leaking any fields.
        harness = _make_harness(monkeypatch)

        response = harness.client.get(f"/api/insights/{_INSIGHT_UID}/details")

        assert response.status_code == 404
        assert "user_other" not in response.text


class TestSnooze:
    def test_snooze_out_of_range_refuses_before_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, f"/api/insights/{_INSIGHT_UID}/snooze", {"days": 0})

        assert response.status_code == 400
        harness.store.dismiss_insight.assert_not_awaited()

    def test_snooze_currently_dismisses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Pinned as-is: snooze has no snooze_until_date yet — it dismisses and
        # reports the requested duration back.
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, f"/api/insights/{_INSIGHT_UID}/snooze", {"days": 3})

        assert response.status_code == 200
        assert response.json()["days"] == 3
        harness.store.dismiss_insight.assert_awaited_once_with(_INSIGHT_UID, _USER_UID)


class TestActiveInsights:
    def test_active_scopes_to_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/insights/active?domain=tasks&limit=10")

        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 0
        assert payload["domain_filter"] == "tasks"
        harness.store.get_active_insights.assert_awaited_once_with(
            user_uid=_USER_UID, domain="tasks", limit=10
        )
