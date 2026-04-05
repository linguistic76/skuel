"""Submissions section for the PathStep detail page.

Renders a user's submissions that occurred during a specific PathStep,
with status badges, exercise names, and links to view submission/feedback.
"""

from fasthtml.common import A, Div, Span

from core.ports.query_types import PathStepSubmissionRow
from ui.patterns.empty_state import EmptyState

_SUB_STATUS_BADGE: dict[str, str] = {
    "submitted": "bg-blue-100 text-blue-800 border border-blue-200",
    "processing": "bg-yellow-100 text-yellow-800 border border-yellow-200",
    "completed": "bg-green-100 text-green-800 border border-green-200",
    "reviewed": "bg-violet-100 text-violet-800 border border-violet-200",
    "approved": "bg-green-100 text-green-800 border border-green-200",
    "revision_needed": "bg-amber-100 text-amber-800 border border-amber-200",
}
_SUB_STATUS_DEFAULT = "bg-muted text-muted-foreground border border-border"


def _status_badge(status: str | None) -> Span:
    label = (status or "submitted").replace("_", " ").title()
    cls_base = _SUB_STATUS_BADGE.get(status or "", _SUB_STATUS_DEFAULT)
    return Span(label, cls=f"{cls_base} text-xs font-medium px-2 py-0.5 rounded-full")


def _submission_row(sub: PathStepSubmissionRow) -> Div:
    """Single submission row with status badge and action links."""
    title = sub["title"] or sub["uid"]
    exercise_note = (
        Span(
            f"for {sub['exercise_title']}",
            cls="text-xs text-muted-foreground",
        )
        if sub.get("exercise_title")
        else None
    )

    action = A(
        "View Submission →",
        href=f"/gradebook/{sub['uid']}",
        cls="text-xs text-primary hover:underline shrink-0",
    )
    if sub.get("report_uid"):
        action = A(
            "View Feedback →",
            href=f"/exercise-reports/detail?uid={sub['report_uid']}",
            cls="text-xs text-primary hover:underline shrink-0",
        )

    return Div(
        Div(
            Span(title, cls="text-sm font-medium text-foreground mr-auto"),
            _status_badge(sub["status"]),
            exercise_note,
            action,
            cls="flex items-center gap-2",
        ),
        cls="py-2.5 border-b border-border/50 last:border-0",
    )


def render_ps_submissions(submissions: list[PathStepSubmissionRow]) -> Div:
    """Render submissions for a PathStep or an empty state."""
    if not submissions:
        return EmptyState(
            title="No submissions yet",
            description="Submit work for an exercise in this step to see it here.",
        )

    count_note = Span(
        f"{len(submissions)} submission{'s' if len(submissions) != 1 else ''}",
        cls="text-xs text-muted-foreground mb-3 block",
    )
    rows = [_submission_row(s) for s in submissions]
    return Div(count_note, Div(*rows))
