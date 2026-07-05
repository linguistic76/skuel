"""Phase 2→3 bridge: exercise status — status pills, action links, exercise list rendering.

Status reflects both Phase 2 (UserEntry state, ADR-054) and Phase 3 (EntryReport
outcome) collapsed into a single display key:

    not_submitted     — no UserEntry exists yet → "Submit →" link
    in_progress       — a vault living entry declares the exercise
                        (fulfills_exercise_uid intent, no turn-in yet) → "View Entry →"
    submitted         — turn-in exists, no report yet → "View Submission →" link
    feedback_available — EntryReport exists (APPROVED or AI_EVALUATED) → "View Report →"
    revision_requested — EntryReport with NEEDS_REVISION → "View Report →"

Precedence is loop-phase order: a report beats a turn-in beats declared intent —
after the copy files, the chip advances to "Submitted" even though the living
entry keeps its intent property.

Used by both the PathStep detail page (/explore/ps/{uid}) and the Library exercises
tab (/library/exercises) — extracted from library_ui.py for this shared purpose.

Data shape: ExerciseStatusRow TypedDict (core/ports/query_types.py).
"""

from typing import Any

from fasthtml.common import A, Div, P, Span

from core.ports.query_types import ExerciseStatusRow
from ui.components import ButtonT
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.primitives import ButtonLink

_EXERCISE_STATUS_MAP: dict[str, tuple[str, BadgeT | None, str]] = {
    "not_submitted": ("Not Submitted", BadgeT.neutral, ""),
    "in_progress": ("In Progress", BadgeT.accent, ""),
    "submitted": ("Submitted", BadgeT.info, ""),
    "feedback_available": ("Feedback Available", BadgeT.success, ""),
    "revision_requested": (
        "Revision Requested",
        None,
        "bg-amber-100 text-amber-800 border-amber-200",
    ),
}


def exercise_status_badge(key: str) -> Any:
    """Render a Badge for an exercise workflow status key."""
    label, variant, custom_cls = _EXERCISE_STATUS_MAP[key]
    return Badge(label, variant=variant, cls=custom_cls, size=Size.sm)


def exercise_status_key(row: ExerciseStatusRow) -> str:
    """Derive display status key from exercise row fields (loop-phase precedence)."""
    if row["has_report"]:
        if (row["report_outcome"] or "").lower() == "needs_revision":
            return "revision_requested"
        return "feedback_available"
    if row["has_submission"]:
        return "submitted"
    if row["has_in_progress"]:
        return "in_progress"
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
            cls=ButtonT.primary,
            size="sm",
        )
    if status == "in_progress":
        return ButtonLink(
            "View Entry →",
            href=f"/gradebook/{row['in_progress_uid']}",
            cls=ButtonT.ghost,
            size="sm",
        )
    if status == "submitted":
        return ButtonLink(
            "View Submission →",
            href=f"/gradebook/{row['submission_uid']}",
            cls=ButtonT.ghost,
            size="sm",
        )
    # feedback_available or revision_requested
    return ButtonLink(
        "View Report →",
        href=f"/entry-reports/detail?uid={row['report_uid']}",
        cls=ButtonT.ghost,
        size="sm",
    )


def exercise_item(row: ExerciseStatusRow, from_ps: str | None = None) -> Div:
    """Single row for an exercise showing submission/feedback status."""
    snippet = (row["description"] or "")[:120]
    if len(row["description"] or "") > 120:
        snippet += "…"

    status_key = exercise_status_key(row)

    return Div(
        Div(
            A(
                row["title"] or row["uid"],
                href=f"/exercises/get?uid={row['uid']}",
                cls="text-sm font-medium text-foreground hover:text-primary hover:underline mr-auto",
            ),
            exercise_status_badge(status_key),
            ButtonLink(
                "Download",
                href=f"/api/exercises/md?uid={row['uid']}",
                cls=ButtonT.ghost,
                size="sm",
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
