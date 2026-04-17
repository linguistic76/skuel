"""Shared report item rendering for submission report display.

Used by the teacher review UI and the student submission detail page. Takes
a typed ``ExerciseReport`` — the persistence boundary returns these directly
via ``ExerciseReportService.list_for_submission``.
"""

from datetime import datetime
from typing import Any

from fasthtml.common import A, Div, P, Span

from core.models.enums.pipeline import ReportSource
from core.models.report.exercise_report import ExerciseReport


def render_report_item(report: ExerciseReport) -> Div:
    """Render a single typed ExerciseReport as a history card."""
    author = report.user_uid or "Author"
    content = report.processed_content or ""
    title = report.title or ""

    time_display = ""
    if report.created_at:
        if isinstance(report.created_at, datetime):
            time_display = report.created_at.strftime("%b %d, %H:%M")
        else:
            time_display = str(report.created_at)[:16]

    is_revision = "revision" in title.lower() if title else False
    is_ai = report.processor_type == ReportSource.LLM
    border_cls = "border-l-warning" if is_revision else "border-l-info"
    if is_revision:
        type_label = "Revision Request"
    elif is_ai:
        type_label = "AI Feedback"
    else:
        type_label = "Feedback"

    badge: Any = ""
    if is_ai:
        badge = Span(
            "AI",
            cls=(
                "ml-2 px-1.5 py-0.5 text-[10px] font-semibold rounded "
                "bg-info/10 text-info uppercase tracking-wide"
            ),
        )

    download_link: Any = ""
    if report.report_file_path and report.uid:
        download_link = A(
            "Download Feedback (.md)",
            href=f"/api/reports/{report.uid}/download",
            cls="text-xs text-primary underline mt-2 inline-block",
        )

    return Div(
        Div(
            Div(
                Span(type_label, cls="font-medium text-sm"),
                badge,
                Span(f" by {author}", cls="text-sm text-muted-foreground"),
                Span(f" · {time_display}", cls="text-xs text-foreground/40")
                if time_display
                else "",
                cls="mb-1",
            ),
            P(content, cls="text-sm whitespace-pre-wrap"),
            download_link,
            cls="p-3",
        ),
        cls=f"border-l-4 {border_cls} bg-muted/50 rounded-r mb-2",
    )
