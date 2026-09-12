"""The activity report request form's period vocabulary and the period door's
"generate" state (``ui/patterns/generate_report.py``)."""

from __future__ import annotations

from datetime import date

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from ui.patterns.generate_report import (
    period_options,
    render_activity_report_request_card,
    render_period_report_prompt,
)


def test_period_options_offer_trailing_windows_then_the_current_and_previous_periods() -> None:
    options = period_options(date(2026, 9, 12))
    assert [token for _, token in options] == [
        "7d",
        "14d",
        "30d",
        "90d",
        "2026-09",
        "2026-08",
        "2026-W37",
        "2026-W36",
    ]
    labels = {token: label for label, token in options}
    assert labels["2026-09"].startswith("This month")
    assert "September 2026" in labels["2026-09"]
    assert labels["2026-W36"].startswith("Last week")


def test_period_options_carry_year_boundaries() -> None:
    tokens = [token for _, token in period_options(date(2026, 1, 3))]
    assert "2025-12" in tokens  # last month
    assert "2026-01" in tokens
    assert "2026-W01" in tokens and "2025-W52" in tokens


def test_request_card_lists_the_periods_with_the_week_default() -> None:
    html = to_xml(render_activity_report_request_card(date(2026, 9, 12)))
    assert 'value="7d" selected' in html
    assert 'value="2026-09"' in html
    assert 'value="2026-W37"' in html
    assert 'hx-post="/api/reports/progress/generate"' in html


def test_period_prompt_is_a_csrf_protected_post_carrying_the_token() -> None:
    html = to_xml(
        render_period_report_prompt(
            token="2026-08", label="August 2026", is_closed=True, note="Wait an hour."
        )
    )
    assert "No report for August 2026 yet" in html
    assert "has closed" in html
    assert 'name="csrf_token"' in html
    assert 'name="time_period" value="2026-08"' in html
    assert 'action="/activity-reports/for"' in html
    assert "Wait an hour." in html
    open_html = to_xml(
        render_period_report_prompt(token="2026-09", label="September 2026", is_closed=False)
    )
    assert "still open" in open_html
