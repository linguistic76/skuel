"""The /ui/analytics pages answer in the page shell (adapters/inbound/analytics_ui.py).

A full-page request to the dashboard, the Life Path alignment page or the weekly life
summary gets ``BasePage``: one ``<main id="main-content">``, the top navbar and the
bottom nav — on success and on a failed read, whose banner renders inside the shell.
The result fragment the dashboard's form loads stays a fragment. The weekly summary
reads ``start_date`` by the one query rule: blank is this week, malformed is a 400.
"""

from __future__ import annotations

import re
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

import adapters.inbound.analytics_ui as analytics_ui
from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result

ALIGNMENT = {
    "life_path_uid": "lp.x.teacher",
    "life_path_title": "Become a patient teacher",
    "alignment_score": 0.62,
    "knowledge_count": 12,
    "embodied_knowledge": 5,
    "theoretical_knowledge": 3,
}
SUMMARY = {"period": {"start": "2026-10-26", "end": "2026-11-01"}, "total_activity_score": 74.0}


def _client(monkeypatch: pytest.MonkeyPatch, service: MagicMock) -> TestClient:
    def signed_in(_request: object) -> UserUID:
        return UserUID("user_learner")

    monkeypatch.setattr(analytics_ui, "require_authenticated_user", signed_in)
    app, rt = fast_app(pico=False, default_hdrs=False)
    analytics_ui.create_analytics_ui_routes(app, rt, service)
    return TestClient(app)


def _service() -> MagicMock:
    service = MagicMock()
    service.calculate_life_path_alignment = AsyncMock(return_value=Result.ok(ALIGNMENT))
    service.generate_weekly_life_summary = AsyncMock(return_value=Result.ok(SUMMARY))
    return service


def _assert_in_shell(page: str) -> None:
    assert page.count('id="main-content"') == 1, "the page is not the shell's"
    assert 'aria-label="Main navigation"' in page
    assert 'aria-label="Primary navigation"' in page  # the bottom nav


@pytest.mark.parametrize(
    "path",
    ["/ui/analytics", "/ui/analytics/life-path-alignment", "/ui/analytics/weekly-life-summary"],
)
def test_each_page_answers_in_the_shell(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    response = _client(monkeypatch, _service()).get(path)

    assert response.status_code == 200
    _assert_in_shell(response.text)


def test_the_dashboard_builds_no_navbar_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _client(monkeypatch, _service()).get("/ui/analytics").text

    assert page.count('aria-label="Main navigation"') == 1
    main = page[page.index('id="main-content"') :]
    assert 'aria-label="Main navigation"' not in main


def test_the_result_slot_is_out_of_the_layout_until_a_result_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _client(monkeypatch, _service()).get("/ui/analytics").text

    slot = re.search(r'<div id="analytics-display" class="([^"]*)"></div>', page)
    assert slot is not None
    assert set(slot.group(1).split()) == {"mt-6", "empty:hidden"}


@pytest.mark.parametrize(
    ("path", "method", "message"),
    [
        ("/ui/analytics/life-path-alignment", "calculate_life_path_alignment", "Could not load your Life Path alignment"),
        ("/ui/analytics/weekly-life-summary", "generate_weekly_life_summary", "Could not load your weekly life summary"),
    ],
)  # fmt: skip
def test_a_failed_read_renders_its_banner_in_the_shell(
    monkeypatch: pytest.MonkeyPatch, path: str, method: str, message: str
) -> None:
    service = _service()
    setattr(
        service,
        method,
        AsyncMock(return_value=Result.fail(Errors.database("read_alignment", "read failed"))),
    )
    response = _client(monkeypatch, service).get(path)

    assert response.status_code == 200
    _assert_in_shell(response.text)
    assert message in response.text


def test_the_result_fragment_stays_a_fragment(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch, _service()).get(
        "/ui/analytics/period-fields?period=custom", headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    assert "<html" not in response.text
    assert 'name="start_date"' in response.text


def test_a_blank_start_date_reads_this_week(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    response = _client(monkeypatch, service).get("/ui/analytics/weekly-life-summary?start_date=")

    assert response.status_code == 200
    service.generate_weekly_life_summary.assert_awaited_once_with("user_learner")


def test_a_start_date_picks_its_week(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    response = _client(monkeypatch, service).get(
        "/ui/analytics/weekly-life-summary?start_date=2026-10-26"
    )

    assert response.status_code == 200
    service.generate_weekly_life_summary.assert_awaited_once_with(
        "user_learner", week_start=date(2026, 10, 26)
    )


def test_a_malformed_start_date_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    response = _client(monkeypatch, service).get(
        "/ui/analytics/weekly-life-summary?start_date=last-week"
    )

    assert response.status_code == 400
    assert "start_date" in response.text
    service.generate_weekly_life_summary.assert_not_awaited()
