"""Feedback section for the PathStep detail page.

Renders report/feedback summaries for a user's submissions during a PathStep.
Filters to submissions that have reports and shows outcome badges with action links.
"""

from fasthtml.common import Div, Span

from core.ports.query_types import PathStepSubmissionRow
from ui.buttons import ButtonLink, ButtonT
from ui.layout import Size
from ui.patterns.empty_state import EmptyState

_OUTCOME_BADGE: dict[str, tuple[str, str]] = {
    "approved": (
        "Approved",
        "bg-green-100 text-green-800 border border-green-200 text-xs font-medium px-2 py-0.5 rounded-full",
    ),
    "needs_revision": (
        "Revision Requested",
        "bg-amber-100 text-amber-800 border border-amber-200 text-xs font-medium px-2 py-0.5 rounded-full",
    ),
}
_OUTCOME_DEFAULT = (
    "Reviewed",
    "bg-blue-100 text-blue-800 border border-blue-200 text-xs font-medium px-2 py-0.5 rounded-full",
)


def _feedback_row(sub: PathStepSubmissionRow) -> Div:
    """Single feedback row with outcome badge and action link."""
    outcome = (sub.get("report_outcome") or "").lower()
    label, cls = _OUTCOME_BADGE.get(outcome, _OUTCOME_DEFAULT)

    title = sub.get("exercise_title") or sub["title"] or sub["uid"]

    action_text = "View Report →"
    if outcome == "needs_revision":
        action_text = "Revise →"

    return Div(
        Div(
            Span(title, cls="text-sm font-medium text-foreground mr-auto"),
            Span(label, cls=cls),
            ButtonLink(
                action_text,
                href=f"/exercise-reports/detail?uid={sub['report_uid']}",
                variant=ButtonT.primary if action_text == "Revise →" else ButtonT.ghost,
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
