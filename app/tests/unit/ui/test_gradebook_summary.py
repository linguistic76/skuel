"""GradeBook summary renderers — the arc 2 C1+C2 page contract.

Pins the per-exercise exchange lines (one line per exchange, opening its
/exchange thread), the derived status text, the chip + source filtering
(server-side, applied by ``filter_exchange_lines``), and the two conditional
groups' hidden-when-empty rule (``None``, not an empty section).
"""

from __future__ import annotations

from fasthtml.common import to_xml

from core.models.enums.pipeline import ExchangeStatus
from core.ports.query_types import GradebookOtherReport, StudentExchangeSummary
from ui.gradebook.summary import (
    filter_exchange_lines,
    normalize_exchange_filters,
    render_activity_reports_group,
    render_exchange_section,
    render_other_feedback_group,
)


def _row(**overrides) -> StudentExchangeSummary:
    row: StudentExchangeSummary = {
        "exercise_uid": "ex.test.one",
        "exercise_title": "Test Exercise",
        "latest_entry_uid": "ue_1",
        "latest_entry_status": "submitted",
        "latest_entry_created_at": "2026-08-01T10:00:00",
        "latest_report_uid": None,
        "latest_report_source": None,
        "latest_report_created_at": None,
        "entry_count": 1,
        "report_count": 0,
        "exchange_status": ExchangeStatus.WAITING.value,
        "latest_activity_at": "2026-08-01T10:00:00",
    }
    row.update(overrides)  # type: ignore[typeddict-item]
    return row


_ROWS: list[StudentExchangeSummary] = [
    _row(
        exercise_uid="ex.a",
        exercise_title="Waiting One",
        exchange_status=ExchangeStatus.WAITING.value,
    ),
    _row(
        exercise_uid="ex.b",
        exercise_title="Feedback One",
        latest_report_uid="er_1",
        latest_report_source="human",
        latest_report_created_at="2026-08-01T11:00:00Z",
        report_count=1,
        exchange_status=ExchangeStatus.FEEDBACK_RECEIVED.value,
    ),
    _row(
        exercise_uid="ex.c",
        exercise_title="Revision One",
        latest_entry_status="revision_requested",
        latest_report_uid="er_2",
        latest_report_source="human",
        report_count=1,
        exchange_status=ExchangeStatus.REVISION_REQUESTED.value,
    ),
    _row(
        exercise_uid="ex.d",
        exercise_title="AI Feedback One",
        latest_report_uid="er_3",
        latest_report_source="llm",
        report_count=2,
        entry_count=2,
        exchange_status=ExchangeStatus.FEEDBACK_RECEIVED.value,
    ),
]


class TestFiltering:
    def test_all_all_passes_everything(self) -> None:
        assert filter_exchange_lines(_ROWS, "all", "all") == _ROWS

    def test_status_filter_narrows(self) -> None:
        waiting = filter_exchange_lines(_ROWS, ExchangeStatus.WAITING.value, "all")
        assert [r["exercise_uid"] for r in waiting] == ["ex.a"]

    def test_source_filter_narrows_and_drops_unreported_lines(self) -> None:
        """A line with no feedback has no source — a specific source filter drops it."""
        human = filter_exchange_lines(_ROWS, "all", "human")
        assert [r["exercise_uid"] for r in human] == ["ex.b", "ex.c"]

    def test_status_and_source_combine(self) -> None:
        both = filter_exchange_lines(_ROWS, ExchangeStatus.FEEDBACK_RECEIVED.value, "llm")
        assert [r["exercise_uid"] for r in both] == ["ex.d"]

    def test_normalize_clamps_unknown_values(self) -> None:
        assert normalize_exchange_filters("junk", "alien") == ("all", "all")
        assert normalize_exchange_filters(ExchangeStatus.WAITING.value, "llm") == (
            ExchangeStatus.WAITING.value,
            "llm",
        )


class TestExchangeSection:
    def test_lines_render_with_status_and_thread_link(self) -> None:
        html = to_xml(render_exchange_section(_ROWS, "all", "all"))
        for row in _ROWS:
            assert f"/exchange?exercise={row['exercise_uid']}" in html
            assert row["exercise_title"] in html
        assert "Waiting" in html
        assert "Feedback received" in html
        assert "Revision requested" in html
        # Source of the latest feedback appears on the line
        assert "from Teacher" in html
        assert "from AI" in html
        # Counts summarize the lineage
        assert "2 submissions · 2 reports" in html

    def test_chips_and_source_select_target_the_fragment(self) -> None:
        html = to_xml(render_exchange_section(_ROWS, "all", "all"))
        assert 'hx-get="/gradebook/lines?status=waiting&amp;source=all"' in html
        assert 'hx-target="#gradebook-exchange"' in html
        assert 'name="source"' in html

    def test_filtered_out_rows_do_not_render(self) -> None:
        html = to_xml(render_exchange_section(_ROWS, ExchangeStatus.WAITING.value, "all"))
        assert "Waiting One" in html
        assert "Feedback One" not in html

    def test_no_match_and_no_rows_render_distinct_empty_states(self) -> None:
        no_match = to_xml(
            render_exchange_section(_ROWS[:1], ExchangeStatus.REVISION_REQUESTED.value, "all")
        )
        assert "No exchanges match this filter." in no_match
        empty = to_xml(render_exchange_section([], "all", "all"))
        assert "No exercise exchanges yet" in empty


class TestConditionalGroups:
    def test_groups_are_hidden_when_empty(self) -> None:
        """Hidden means None — no header, no empty section (arc 2 C1)."""
        assert render_other_feedback_group([]) is None
        assert render_activity_reports_group(None) is None

    def test_other_feedback_links_to_report_detail(self) -> None:
        rows: list[GradebookOtherReport] = [
            {
                "uid": "er_solo",
                "title": "Standalone feedback",
                "source": "human",
                "created_at": "2026-07-01T09:00:00Z",
            }
        ]
        html = to_xml(render_other_feedback_group(rows))
        assert "Other feedback" in html
        assert "Standalone feedback" in html
        assert "/entry-reports/detail?uid=er_solo" in html
