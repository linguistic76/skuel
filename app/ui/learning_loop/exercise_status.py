"""Shared exercise status helpers — status pills, action links, exercise list rendering.

Extracted from library_ui.py so both the Library exercises tab and
the PathStep detail page can render exercise rows with submission/feedback status.
"""

from fasthtml.common import A, Div, P, Span

from core.ports.query_types import ExerciseStatusRow
from ui.buttons import ButtonLink, ButtonT
from ui.layout import Size
from ui.patterns.empty_state import EmptyState

_STATUS_PILL: dict[str, tuple[str, str]] = {
    # key -> (label, CSS classes)
    "not_submitted": (
        "Not Submitted",
        "bg-muted text-muted-foreground border border-border text-xs font-medium px-2 py-0.5 rounded-full",
    ),
    "submitted": (
        "Submitted",
        "bg-blue-100 text-blue-800 border border-blue-200 text-xs font-medium px-2 py-0.5 rounded-full",
    ),
    "feedback_available": (
        "Feedback Available",
        "bg-green-100 text-green-800 border border-green-200 text-xs font-medium px-2 py-0.5 rounded-full",
    ),
    "revision_requested": (
        "Revision Requested",
        "bg-amber-100 text-amber-800 border border-amber-200 text-xs font-medium px-2 py-0.5 rounded-full",
    ),
}


def exercise_status_key(row: ExerciseStatusRow) -> str:
    """Derive display status key from exercise row fields."""
    if row["has_report"]:
        if (row["report_outcome"] or "").lower() == "needs_revision":
            return "revision_requested"
        return "feedback_available"
    if row["has_submission"]:
        return "submitted"
    return "not_submitted"


def exercise_action_link(row: ExerciseStatusRow, from_ps: str | None = None) -> A:
    """Return the primary action link for an exercise row.

    Args:
        row: Exercise status data.
        from_ps: Optional PathStep UID — when set, the "Submit →" link
                 includes &from_ps= so the submit page can navigate back.
    """
    status = exercise_status_key(row)
    uid = row["uid"]
    if status == "not_submitted":
        submit_href = f"/submit?exercise_uid={uid}"
        if from_ps:
            submit_href += f"&from_ps={from_ps}"
        return ButtonLink(
            "Submit →",
            href=submit_href,
            variant=ButtonT.primary,
            size=Size.sm,
        )
    if status == "submitted":
        return ButtonLink(
            "View Submission →",
            href=f"/gradebook/{row['submission_uid']}",
            variant=ButtonT.ghost,
            size=Size.sm,
        )
    # feedback_available or revision_requested
    return ButtonLink(
        "View Report →",
        href=f"/exercise-reports/detail?uid={row['report_uid']}",
        variant=ButtonT.ghost,
        size=Size.sm,
    )


def exercise_item(row: ExerciseStatusRow, from_ps: str | None = None) -> Div:
    """Single row for an exercise showing submission/feedback status."""
    snippet = (row["description"] or "")[:120]
    if len(row["description"] or "") > 120:
        snippet += "…"

    status_key = exercise_status_key(row)
    status_label, status_cls = _STATUS_PILL[status_key]

    return Div(
        Div(
            A(
                row["title"] or row["uid"],
                href=f"/exercises/get?uid={row['uid']}",
                cls="text-sm font-medium text-foreground hover:text-primary hover:underline mr-auto",
            ),
            Span(status_label, cls=status_cls),
            ButtonLink(
                "Download",
                href=f"/api/exercises/md?uid={row['uid']}",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            exercise_action_link(row, from_ps=from_ps),
            cls="flex items-center gap-2",
        ),
        P(snippet, cls="text-xs text-muted-foreground mt-0.5") if snippet else None,
        cls="py-2.5 border-b border-border/50 last:border-0",
    )


def render_exercise_list(exercises: list[ExerciseStatusRow], from_ps: str | None = None) -> Div:
    """Render exercises with submission/feedback status.

    Args:
        exercises: Exercise status rows.
        from_ps: Optional PathStep UID for contextual "Submit →" links.
    """
    if not exercises:
        return EmptyState(
            title="No exercises yet",
            description="Exercises appear here when you enroll in a Path Step or are assigned one by a teacher.",
        )

    count_note = Span(
        f"{len(exercises)} exercise{'s' if len(exercises) != 1 else ''}",
        cls="text-xs text-muted-foreground mb-3 block",
    )
    rows = [exercise_item(ex, from_ps=from_ps) for ex in exercises]
    return Div(count_note, Div(*rows))
