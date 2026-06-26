"""Phase 3: EntryReport — PathStep feedback UI.

Renders EntryReport summaries for a user's submissions during a PathStep.
Filters to submissions that have a linked report (REPORT_FOR edge present).

Outcome badges map to assessment_outcome values:
    approved         → green "Approved" badge
    needs_revision   → amber "Revision Requested" badge + "Revise →" link (→ Phase 4)
    ai_evaluated / other → blue "Reviewed" badge

The "Revise →" action links to /entry-reports/detail?uid= which shows the full
EntryReport. When a RevisedExercise exists for that report, the detail page
surfaces the Phase 4 entry point.

Data is shared with submissions_section.py (Phase 2) — both render from the same
PathStepSubmissionRow list returned by LearningLoopQueryService.

Data shape: PathStepSubmissionRow TypedDict (core/ports/query_types.py).
"""

from typing import Any

from fasthtml.common import Div, Span
from monsterui.franken import ButtonT

from core.ports.query_types import PathStepSubmissionRow
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.primitives import ButtonLink


def _outcome_badge(outcome: str) -> Any:
    """Render a Badge for a feedback outcome value."""
    if outcome == "approved":
        return Badge("Approved", variant=BadgeT.success, size=Size.sm)
    if outcome == "needs_revision":
        return Badge(
            "Revision Requested",
            variant=None,
            cls="bg-amber-100 text-amber-800 border-amber-200",
            size=Size.sm,
        )
    return Badge("Reviewed", variant=BadgeT.info, size=Size.sm)


def _feedback_row(sub: PathStepSubmissionRow) -> Div:
    """Single feedback row with outcome badge and action link."""
    outcome = (sub.get("report_outcome") or "").lower()

    title = sub.get("exercise_title") or sub["title"] or sub["uid"]

    action_text = "View Report →"
    if outcome == "needs_revision":
        action_text = "Revise →"

    return Div(
        Div(
            Span(title, cls="text-sm font-medium text-foreground mr-auto"),
            _outcome_badge(outcome),
            ButtonLink(
                action_text,
                href=f"/entry-reports/detail?uid={sub['report_uid']}",
                cls=ButtonT.primary if action_text == "Revise →" else ButtonT.ghost,
                size=Size.sm,
            ),
            cls="flex items-center gap-2",
        ),
        cls="py-2.5 border-b border-border/50 last:border-0",
    )


def render_ps_feedback(submissions: list[PathStepSubmissionRow]) -> Div:
    """Render feedback for submissions that have reports, or an empty state."""
    with_reports = [s for s in submissions if s.get("report_uid")]

    if not with_reports:
        return EmptyState(
            title="No feedback yet",
            description="Feedback from teachers will appear here after your submissions are reviewed.",
        )

    count_note = Span(
        f"{len(with_reports)} report{'s' if len(with_reports) != 1 else ''}",
        cls="text-xs text-muted-foreground mb-3 block",
    )
    rows = [_feedback_row(s) for s in with_reports]
    return Div(count_note, Div(*rows))
