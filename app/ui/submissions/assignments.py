"""
Submission Assignment UI Components
====================================

Cards for exercises assigned to students via group membership,
and revised exercises targeting a student.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import H4, Div, P, Span

from core.utils.timestamp_helpers import days_until, parse_date
from ui.buttons import ButtonLink, ButtonT
from ui.cards import Card
from ui.feedback import Badge, BadgeT
from ui.layout import Size

if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise


def render_assignment_card(ex: dict[str, Any]) -> Any:
    """Render a single exercise assignment card."""
    uid = ex.get("uid", "")
    title = ex.get("title", "Untitled Exercise")
    instructions = ex.get("instructions") or ""
    due_date_str = ex.get("due_date")
    group_name = ex.get("group_name", "")
    has_submission = ex.get("has_submission", False)

    # Status badge
    if has_submission:
        status_badge = Badge("Submitted", variant=BadgeT.success)
    elif due_date_str:
        try:
            due = parse_date(str(due_date_str))
            remaining = days_until(due)
            if remaining is not None and remaining < 0:
                status_badge = Badge(f"Overdue ({-remaining}d)", variant=BadgeT.error)
            elif remaining is not None and remaining <= 3:
                status_badge = Badge(f"Due in {remaining}d", variant=BadgeT.warning)
            elif remaining is not None:
                status_badge = Badge(f"Due in {remaining}d", variant=BadgeT.info)
            else:
                status_badge = Badge("Pending", variant=BadgeT.ghost)
        except (ValueError, TypeError):
            status_badge = Badge("Pending", variant=BadgeT.ghost)
    else:
        status_badge = Badge("No deadline", variant=BadgeT.ghost)

    # Instructions preview (truncated)
    instructions_preview = ""
    if instructions:
        preview_text = instructions[:200] + ("..." if len(instructions) > 200 else "")
        instructions_preview = P(preview_text, cls="text-sm text-muted-foreground mt-2")

    group_tag = Badge(group_name, variant=BadgeT.outline, size=Size.sm) if group_name else ""
    due_display = ""
    if due_date_str:
        due_display = Span(f"Due: {due_date_str}", cls="text-sm text-muted-foreground")

    if has_submission:
        action = Span("Already submitted", cls="text-sm text-success")
    else:
        action = ButtonLink(
            "Submit",
            href=f"/submit?exercise_uid={uid}",
            variant=ButtonT.primary,
            size=Size.sm,
        )

    return Card(
        Div(
            Div(
                Div(
                    H4(title, cls="text-lg"),
                    status_badge,
                    cls="flex items-center gap-2 flex-wrap",
                ),
                Div(group_tag, due_display, cls="flex items-center gap-3 mt-1"),
                instructions_preview,
                cls="flex-1",
            ),
            Div(action, cls="flex items-center"),
            cls="flex justify-between gap-4",
        ),
        cls="bg-background shadow-sm p-4",
    )


def render_assignments_list(exercises: list[dict[str, Any]]) -> Any:
    """Render student's assigned exercises with submission status."""
    if not exercises:
        return Card(
            P(
                "No exercises assigned yet. You'll see exercises here when a teacher assigns them to your group.",
                cls="text-center text-muted-foreground py-8",
            ),
            cls="bg-background shadow-sm p-6",
        )

    cards = [render_assignment_card(ex) for ex in exercises]
    return Div(*cards, cls="space-y-4")


# ============================================================================
# REVISED EXERCISE CARDS
# ============================================================================


def render_revised_exercise_card(rev: RevisedExercise) -> Any:
    """Render a single revised exercise card with Submit button."""
    title = rev.title or "Untitled Revision"
    revision_badge = Badge(f"Revision {rev.revision_number}", variant=BadgeT.info, size=Size.sm)

    # Feedback points summary
    feedback_summary = ""
    if rev.feedback_points:
        count = len(rev.feedback_points)
        label = "feedback point" if count == 1 else "feedback points"
        feedback_summary = Badge(f"{count} {label}", variant=BadgeT.outline, size=Size.sm)

    instructions_preview = ""
    if rev.instructions:
        preview_text = rev.instructions[:200] + ("..." if len(rev.instructions) > 200 else "")
        instructions_preview = P(preview_text, cls="text-sm text-muted-foreground mt-2")

    rationale = ""
    if rev.revision_rationale:
        rationale = P(
            rev.revision_rationale[:150] + ("..." if len(rev.revision_rationale) > 150 else ""),
            cls="text-xs text-muted-foreground italic mt-1",
        )

    action = ButtonLink(
        "Submit",
        href=f"/submit?exercise_uid={rev.uid}",
        variant=ButtonT.primary,
        size=Size.sm,
    )

    return Card(
        Div(
            Div(
                Div(
                    H4(title, cls="text-lg"),
                    revision_badge,
                    feedback_summary,
                    cls="flex items-center gap-2 flex-wrap",
                ),
                instructions_preview,
                rationale,
                cls="flex-1",
            ),
            Div(action, cls="flex items-center"),
            cls="flex justify-between gap-4",
        ),
        cls="bg-background shadow-sm p-4",
    )


def render_revised_exercises_list(exercises: list[RevisedExercise]) -> Any:
    """Render student's revised exercises with Submit buttons."""
    if not exercises:
        return Card(
            P(
                "No revised exercises yet. You'll see revisions here when a teacher "
                "creates targeted follow-up exercises based on your report.",
                cls="text-center text-muted-foreground py-8",
            ),
            cls="bg-background shadow-sm p-6",
        )

    cards = [render_revised_exercise_card(rev) for rev in exercises]
    return Div(*cards, cls="space-y-4")
