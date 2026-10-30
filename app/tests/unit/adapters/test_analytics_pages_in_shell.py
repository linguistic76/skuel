"""The /ui/analytics pages answer in the page shell (adapters/inbound/analytics_ui.py).

A full-page request to the dashboard, the Life Path alignment page or the weekly life
summary gets ``BasePage``: one ``<main id="main-content">``, the top navbar and the
bottom nav — on success and on a failed read, whose banner renders inside the shell.
The result fragment the dashboard's form loads stays a fragment. The weekly summary
reads ``start_date`` by the one query rule: blank is this week, malformed is a 400.

The dashboard's result (``/ui/analytics/view``) and period fields read the same rule.
The domain and period pickers mint their values: missing or blank is the picker's
first choice, a word outside the vocabulary a bare 400 the slot never swaps in. The
custom range's dates are the learner's typing, so a range that does not read answers
the form's banner (200). No refusal reaches the service.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

import adapters.inbound.analytics_ui as analytics_ui
from core.models.analytics.analytics import AnalyticsSummary
from core.models.enums import AnalyticsDomain, AnalyticsPeriod
from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result
from tests.helpers.settings_stub import settings_stub

ALIGNMENT = {
    "life_path_uid": "lp.x.teacher",
    "life_path_title": "Become a patient teacher",
    "alignment_score": 0.62,
    "knowledge_count": 12,
    "embodied_knowledge": 5,
    "theoretical_knowledge": 3,
}
SUMMARY = {"period": {"start": "2026-10-26", "end": "2026-11-01"}, "total_activity_score": 74.0}
REPORT = AnalyticsSummary(
    uid="report_0123456789abcdef",
    user_uid=UserUID("user_learner"),
    analytics_domain=AnalyticsDomain.TASKS,
    period_start=date(2026, 10, 26),
    period_end=date(2026, 11, 1),
    metrics={"total_count": 7},
    generated_at=datetime(2026, 10, 30, 9, 0),
    title="Tasks Report: Week of Oct 26, 2026",
)
#: The report methods ``/ui/analytics/view`` dispatches to.
REPORT_METHODS = (
    "generate_report",
    "generate_weekly_report",
    "generate_monthly_report",
    "generate_yearly_report",
)


def _client(monkeypatch: pytest.MonkeyPatch, service: MagicMock) -> TestClient:
    def signed_in(_request: object) -> UserUID:
        return UserUID("user_learner")

    monkeypatch.setattr(analytics_ui, "require_authenticated_user", signed_in)
    monkeypatch.setattr(analytics_ui, "get_settings", settings_stub(debug=False))
    app, rt = fast_app(pico=False, default_hdrs=False)
    analytics_ui.create_analytics_ui_routes(app, rt, service)
    return TestClient(app)


def _service() -> MagicMock:
    service = MagicMock()
    service.calculate_life_path_alignment = AsyncMock(return_value=Result.ok(ALIGNMENT))
    service.generate_weekly_life_summary = AsyncMock(return_value=Result.ok(SUMMARY))
    for method in REPORT_METHODS:
        setattr(service, method, AsyncMock(return_value=Result.ok(REPORT)))
    return service


def _assert_no_report(service: MagicMock) -> None:
    for method in REPORT_METHODS:
        getattr(service, method).assert_not_awaited()


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
    assert "read failed" not in response.text  # the detail renders only in debug


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


# ---------------------------------------------------------------------------
# /ui/analytics/view and /ui/analytics/period-fields — the one query rule
# ---------------------------------------------------------------------------


def test_the_pickers_offer_each_member_of_their_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _client(monkeypatch, _service()).get("/ui/analytics").text

    for name, vocabulary in (("analytics_domain", AnalyticsDomain), ("period", AnalyticsPeriod)):
        select = re.search(rf'<select[^>]*name="{name}".*?</select>', page, re.DOTALL)
        assert select is not None
        offered = re.findall(r'<option value="([^"]*)"', select.group(0))
        assert offered == [member.value for member in vocabulary]


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ("/ui/analytics/view?analytics_domain=finance&period=week_current", "analytics_domain"),
        ("/ui/analytics/view?analytics_domain=tasks&period=fortnight", "period"),
        ("/ui/analytics/view?analytics_domain=Tasks&period=custom&start_date=2026-10-01&end_date=2026-10-30", "analytics_domain"),
        ("/ui/analytics/period-fields?period=fortnight", "period"),
    ],
)  # fmt: skip
def test_a_picker_value_that_does_not_read_is_a_bare_400(
    monkeypatch: pytest.MonkeyPatch, path: str, field: str
) -> None:
    service = _service()
    response = _client(monkeypatch, service).get(path, headers={"HX-Request": "true"})

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/plain")
    assert "X-SKUEL-Refusal" not in response.headers  # htmx leaves the slot as it was
    assert response.text.startswith(f"{field} must be one of: ")
    _assert_no_report(service)


@pytest.mark.parametrize(
    "query", ["", "?analytics_domain=&period=", "?analytics_domain=&period=&start_date=junk"]
)
def test_missing_pickers_read_this_weeks_tasks(monkeypatch: pytest.MonkeyPatch, query: str) -> None:
    service = _service()
    response = _client(monkeypatch, service).get(f"/ui/analytics/view{query}")

    assert response.status_code == 200
    assert REPORT.title in response.text
    service.generate_weekly_report.assert_awaited_once()
    user_uid, domain, week_start = service.generate_weekly_report.await_args.args
    assert (user_uid, domain) == ("user_learner", AnalyticsDomain.TASKS)
    assert week_start.weekday() == 0  # this week's Monday


@pytest.mark.parametrize(
    ("today", "period", "method", "args"),
    [
        (date(2026, 10, 30), "week_current", "generate_weekly_report", (date(2026, 10, 26),)),
        (date(2026, 10, 30), "week_last", "generate_weekly_report", (date(2026, 10, 19),)),
        (date(2026, 10, 30), "month_current", "generate_monthly_report", (2026, 10)),
        (date(2026, 10, 30), "month_last", "generate_monthly_report", (2026, 9)),
        (date(2026, 1, 15), "month_last", "generate_monthly_report", (2025, 12)),
        (date(2026, 10, 30), "year_current", "generate_yearly_report", (2026,)),
    ],
)  # fmt: skip
def test_each_period_asks_for_its_report(
    monkeypatch: pytest.MonkeyPatch,
    today: date,
    period: str,
    method: str,
    args: tuple[int | date, ...],
) -> None:
    def fixed_today(_zone: object) -> date:
        return today

    monkeypatch.setattr(analytics_ui, "today_in", fixed_today)
    service = _service()
    response = _client(monkeypatch, service).get(
        f"/ui/analytics/view?analytics_domain=habits&period={period}"
    )

    assert response.status_code == 200
    getattr(service, method).assert_awaited_once_with("user_learner", AnalyticsDomain.HABITS, *args)


@pytest.mark.parametrize(
    ("dates", "message"),
    [
        ("", "A custom range needs both a start and an end date."),
        ("&start_date=&end_date=2026-10-30", "A custom range needs both a start and an end date."),
        ("&start_date=2026-10-01&end_date=", "A custom range needs both a start and an end date."),
        ("&start_date=2026-10-30&end_date=2026-10-01", "The start date must be on or before the end date."),
        ("&start_date=10/01/2026&end_date=2026-10-30", "Enter each date as YYYY-MM-DD."),
        ("&start_date=2026-10-01&end_date=2026-02-30", "Enter each date as YYYY-MM-DD."),
    ],
)  # fmt: skip
def test_a_typed_range_that_does_not_read_answers_the_forms_banner(
    monkeypatch: pytest.MonkeyPatch, dates: str, message: str
) -> None:
    service = _service()
    response = _client(monkeypatch, service).get(
        f"/ui/analytics/view?analytics_domain=goals&period=custom{dates}",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "<html" not in response.text
    assert 'role="alert"' in response.text
    assert message in response.text
    _assert_no_report(service)


def test_a_one_day_range_is_a_range(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    response = _client(monkeypatch, service).get(
        "/ui/analytics/view?analytics_domain=events&period=custom"
        "&start_date=2026-10-30&end_date=2026-10-30"
    )

    assert response.status_code == 200
    service.generate_report.assert_awaited_once_with(
        "user_learner", AnalyticsDomain.EVENTS, date(2026, 10, 30), date(2026, 10, 30)
    )


def test_a_failed_report_shows_the_learner_no_developer_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.generate_weekly_report = AsyncMock(
        return_value=Result.fail(Errors.database("calculate_task_metrics", "read failed"))
    )
    response = _client(monkeypatch, service).get(
        "/ui/analytics/view?analytics_domain=tasks&period=week_current"
    )

    assert response.status_code == 200
    assert "Could not generate your analytics" in response.text
    assert "read failed" not in response.text  # the detail renders only in debug
    assert "database:" not in response.text  # nor ErrorContext's developer form


@pytest.mark.parametrize("query", ["", "?period=", "?period=week_last"])
def test_a_closed_period_needs_no_date_fields(monkeypatch: pytest.MonkeyPatch, query: str) -> None:
    response = _client(monkeypatch, _service()).get(
        f"/ui/analytics/period-fields{query}", headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    assert 'name="start_date"' not in response.text
