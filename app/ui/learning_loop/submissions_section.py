"""Phase 2: UserEntry — PathStep submissions UI (ADR-054).

Renders a user's UserEntry submissions for a specific PathStep. Submissions are
discovered via the Interaction graph — not by querying submissions directly:

    (user)-[:OWNS]->(entry:UserEntry)-[:RECORDS]<-(interaction)-[:INTERACTION_DURING]->(ps)

This means only submissions made *while the user was in this PathStep* appear here,
preserving the curriculum context in which the work was done.

Data is fetched by LearningLoopQueryService.get_submissions_for_path_step() and
shared with feedback_section.py (Phase 3) in a single query result. Both sections
are rendered together by render_ps_submissions_and_feedback() and served by the
/learning-loop/ps/{ps_uid}/submissions-and-feedback HTMX endpoint.

Data shape: PathStepSubmissionRow TypedDict (core/ports/query_types.py).
"""

from typing import Any

from fasthtml.common import H3, A, Div, P, Span

from core.ports.query_types import PathStepSubmissionRow
from ui.feedback import Badge, BadgeT, StatusBadge
from ui.layout import Size
from ui.learning_loop.feedback_section import render_ps_feedback
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
            href=f"/entry-reports/detail?uid={sub['report_uid']}",
            cls="text-xs text-primary hover:underline shrink-0",
        )

    # Exercise-anchored submissions also link into the exchange thread (C5) —
    # the whole (student, exercise) chain, not just this one artifact.
    exchange_action = (
        A(
            "Exchange →",
            href=f"/exchange?exercise={sub['exercise_uid']}",
            cls="text-xs text-primary hover:underline shrink-0",
        )
        if sub.get("exercise_uid")
        else None
    )

    return Div(
        Div(
            Span(title, cls="text-sm font-medium text-foreground mr-auto"),
            _status_badge(sub["status"]),
            exercise_note,
            action,
            exchange_action,
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


def render_ps_submissions_and_feedback(rows: list[PathStepSubmissionRow]) -> Div:
    """Render both submissions and feedback sections for a PathStep.

    Composes the submissions list and feedback list into a single fragment,
    used by the /learning-loop/ps/{ps_uid}/submissions-and-feedback endpoint.
    The page renders the "Submissions & Feedback" heading unconditionally, so
    an empty fragment reads as a headed void — with no submissions, render one
    muted line instead of the full two-section stack.
    """
    if not rows:
        return Div(
            P(
                "Nothing submitted for this step yet.",
                cls="text-[13px] text-muted-foreground",
            )
        )
    return Div(
        H3("My Submissions", cls="text-base font-semibold mb-2 mt-6"),
        render_ps_submissions(rows),
        H3("Feedback", cls="text-base font-semibold mb-2 mt-6"),
        render_ps_feedback(rows),
    )
