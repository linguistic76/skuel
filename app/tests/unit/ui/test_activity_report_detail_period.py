"""The report detail's period line: a calendar-period report names its period,
says whether it is partial, and offers the one explicit refresh."""

from __future__ import annotations

from datetime import datetime

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from core.models.enums.pipeline import ReportSource
from core.models.report.activity_report import ActivityReport
from ui.learning_loop.report import render_activity_report_detail


def _report(**overrides) -> ActivityReport:  # type: ignore[no-untyped-def]  # boundary: test kwargs
    fields = {
        "uid": "ar_period",
        "title": "Activity Report — Sep 01 to Sep 30, 2026",
        "user_uid": "user_reports",
        "subject_uid": "user_reports",
        "processor_type": ReportSource.AUTOMATIC,
        "time_period": "2026-09",
        "period_start": datetime(2026, 9, 1),
        "period_end": datetime(2026, 9, 30, 23, 59, 59, 999999),
        "data_cutoff": datetime(2026, 9, 12, 10, 0),
        "processed_content": "# Progress Report",
        "created_at": datetime(2026, 9, 12, 10, 0),
        "metadata": {"is_partial": True},
    }
    fields.update(overrides)
    return ActivityReport(**fields)


def test_calendar_report_shows_its_period_partial_state_and_regenerate() -> None:
    html = to_xml(render_activity_report_detail(_report()))
    assert 'data-report-period="2026-09"' in html
    assert "September 2026 · Partial · counted through Sep 12, 2026" in html
    assert "Regenerate" in html
    assert 'name="time_period" value="2026-09"' in html
    assert 'action="/activity-reports/for"' in html
    assert 'name="csrf_token"' in html


def test_final_report_says_so() -> None:
    final = _report(
        data_cutoff=datetime(2026, 9, 30, 23, 59, 59, 999999), metadata={"is_partial": False}
    )
    html = to_xml(render_activity_report_detail(final))
    assert "September 2026 · Final" in html


def test_trailing_window_report_has_no_period_line() -> None:
    html = to_xml(render_activity_report_detail(_report(time_period="7d", metadata={})))
    assert "data-report-period" not in html
    assert "Regenerate" not in html
