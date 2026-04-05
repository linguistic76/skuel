"""Submissions section for the PathStep detail page.

Renders a user's submissions that occurred during a specific PathStep,
with status badges, exercise names, and links to view submission/feedback.
"""

from typing import Any

from fasthtml.common import A, Div, Span

from core.ports.query_types import PathStepSubmissionRow
from ui.feedback import Badge, BadgeT, StatusBadge
from ui.layout import Size
from ui.patterns.empty_state import EmptyState

# Submission statuses that are valid EntityStatus values
_ENTITY_STATUSES = {"submitted", "processing", "completed"}

# Non-EntityStatus submission statuses
_EXTRA_STATUS_MAP: dict[str, tuple[str, BadgeT | None, str]] = {
    "reviewed": ("Reviewed", BadgeT.accent, ""),
    "approved": ("Approved", BadgeT.success, ""),
    "revision_needed": (
        "Revision Needed",
        None,
        "bg-amber-100 text-amber-800 border-amber-200",
    ),
}


def _status_badge(status: str | None) -> Any:
    s = status or "submitted"
    if s in _ENTITY_STATUSES:
        return StatusBadge(s, size=Size.sm)
    label, variant, custom_cls = _EXTRA_STATUS_MAP.get(
        s, (s.replace("_", " ").title(), BadgeT.neutral, "")
    )
    return Badge(label, variant=variant, cls=custom_cls, size=Size.sm)


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
