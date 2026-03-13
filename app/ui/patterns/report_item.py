"""Shared report item rendering for submission report display.

Used by both the teacher review UI and the student submission detail page.
"""

from datetime import datetime
from typing import Any

from fasthtml.common import Div, P, Span


def render_report_item(fb: dict[str, Any]) -> Div:
    """Render a single report history item."""
    teacher_name = fb.get("teacher_name") or fb.get("teacher_uid") or "Teacher"
    content = fb.get("content") or ""
    created_at = fb.get("created_at", "")
    title = fb.get("title", "")

    time_display = ""
    if created_at:
        if isinstance(created_at, datetime):
            time_display = created_at.strftime("%b %d, %H:%M")
        else:
            time_display = str(created_at)[:16]

    is_revision = "revision" in title.lower() if title else False
    border_cls = "border-l-warning" if is_revision else "border-l-info"
    type_label = "Revision Request" if is_revision else "Feedback"

    return Div(
        Div(
            Div(
                Span(type_label, cls="font-medium text-sm"),
                Span(f" by {teacher_name}", cls="text-sm text-muted-foreground"),
                Span(f" · {time_display}", cls="text-xs text-foreground/40")
                if time_display
                else "",
                cls="mb-1",
            ),
            P(content, cls="text-sm whitespace-pre-wrap"),
            cls="p-3",
        ),
        cls=f"border-l-4 {border_cls} bg-muted/50 rounded-r mb-2",
    )
