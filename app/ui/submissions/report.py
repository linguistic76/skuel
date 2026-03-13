"""
Submission Report & Progress UI Components
============================================

Renderers for teacher assessments, activity reports, and progress report cards.
"""

from typing import Any

from fasthtml.common import H4, Div, NotStr, P

from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.cards import Card, CardBody

# ============================================================================
# SHARED HELPERS
# ============================================================================

_PROCESSOR_LABELS = {"llm": "LLM", "automatic": "Scheduled", "human": "Admin"}
_PROCESSOR_BADGE_CLASSES = {
    "llm": "badge-info",
    "automatic": "badge-ghost",
    "human": "badge-primary",
}


def get_processor_type_str(report: Any) -> str:
    """Extract processor_type as lowercase string from a report/entity."""
    processor_type = getattr(report, "processor_type", None)
    if processor_type is None:
        return ""
    _missing = object()
    ptype_val = getattr(processor_type, "value", _missing)
    return str(ptype_val if ptype_val is not _missing else processor_type).lower()


def render_processor_badge(processor_type_str: str) -> Any:
    """Render a badge for processor type (LLM / Scheduled / Admin)."""
    label = _PROCESSOR_LABELS.get(processor_type_str, processor_type_str or "AI")
    badge_cls = _PROCESSOR_BADGE_CLASSES.get(processor_type_str, "badge-ghost")
    return Badge(label, variant=None, size=Size.sm, cls=badge_cls)


def format_date(dt_value: Any) -> str:
    """Format a datetime-like value to a display string."""
    if not dt_value:
        return ""
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(str(dt_value))
        return dt.strftime("%d %b %Y")
    except (ValueError, TypeError):
        return str(dt_value)[:10]


# ============================================================================
# REVIEW STATUS (student submission history)
# ============================================================================


def render_review_status_badge(status: str, feedback_count: int) -> Any:
    """Return a badge indicating the teacher review outcome."""
    if feedback_count > 0 and status == "completed":
        return Badge("Reviewed", variant=BadgeT.success, size=Size.sm)
    if status == "revision_requested":
        return Badge("Revision Needed", variant=BadgeT.warning, size=Size.sm)
    if feedback_count == 0 and status == "submitted":
        return Badge("Awaiting Review", variant=BadgeT.neutral, size=Size.sm)
    return Badge(status.replace("_", " ").title(), variant=BadgeT.ghost, size=Size.sm)


def render_submission_history_row(item: dict) -> Any:
    """Render a single submission row with review status for the history list."""
    from fasthtml.common import A

    filename = item.get("original_filename") or item.get("title") or "Untitled"
    status = item.get("status") or "submitted"
    feedback_count = item.get("feedback_count") or 0
    uid = item.get("uid", "")
    created_str = format_date(item.get("created_at"))

    feedback_chip: Any = ""
    if feedback_count > 0:
        label = f"{feedback_count} feedback round{'s' if feedback_count != 1 else ''}"
        feedback_chip = Badge(label, variant=BadgeT.outline, size=Size.sm, cls="ml-2")

    return Card(
        Div(
            Div(
                P(filename, cls="font-semibold mb-0"),
                P(created_str, cls="text-xs text-muted-foreground mb-0"),
                cls="flex-1",
            ),
            Div(
                render_review_status_badge(status, feedback_count),
                feedback_chip,
                cls="flex items-center gap-2",
            ),
            A(
                "View",
                href=f"/submissions/{uid}",
                cls="btn btn-sm btn-ghost ml-3",
            ),
            cls="flex items-center gap-4",
        ),
        cls="bg-background shadow-sm mb-2",
    )


def render_yours_list(items: list[dict]) -> Any:
    """Render the full list of submissions with feedback status (HTMX swap target)."""
    if not items:
        return Div(
            P(
                "No submissions yet.",
                cls="text-center text-muted-foreground py-8",
            ),
            id="submissions-yours-list",
        )
    return Div(
        *[render_submission_history_row(item) for item in items],
        id="submissions-yours-list",
    )


# ============================================================================
# TEACHER ASSESSMENT CARDS (feedback received by student)
# ============================================================================


def render_report_card(assessment: Any) -> Any:
    """Render a single received-report card (server-side, no inline JS)."""
    from fasthtml.common import A

    uid = getattr(assessment, "uid", "") or ""
    title = getattr(assessment, "title", "") or "Assessment"
    content = getattr(assessment, "content", "") or ""
    preview = content[:200] + ("..." if len(content) > 200 else "")
    created_at = getattr(assessment, "created_at", None)
    user_uid = getattr(assessment, "user_uid", "") or ""

    processor_type = getattr(assessment, "processor_type", None)
    if processor_type:
        _missing = object()
        ptype_val = getattr(processor_type, "value", _missing)
        ptype_str = ptype_val if ptype_val is not _missing else str(processor_type)
        source_label = "AI" if ptype_str == "llm" else "Teacher"
    else:
        source_label = "Teacher"

    date_str = format_date(created_at)

    return Div(
        Card(
            CardBody(
                H4(title, cls="font-semibold mb-1"),
                P(
                    f"From: {user_uid} \u00b7 {date_str} \u00b7 {source_label}",
                    cls="text-sm text-muted-foreground mb-2",
                ),
                P(preview, cls="text-sm"),
                A("View Full", href=f"/submissions/{uid}", cls="btn btn-sm btn-ghost mt-2"),
                cls="p-4",
            ),
            cls="bg-background shadow-sm mb-3",
        ),
    )


def render_received_report_list(items: list[Any]) -> Any:
    """Render the full list of received reports (HTMX swap target)."""
    if not items:
        return Div(
            P("No reports yet.", cls="text-center text-muted-foreground py-6"),
            P(
                "Assessments from teachers will appear here once submitted.",
                cls="text-sm text-center text-foreground/40",
            ),
            id="feedback-list",
        )
    return Div(
        *[render_report_card(a) for a in items],
        id="feedback-list",
    )


# ============================================================================
# ACTIVITY FEEDBACK CARDS
# ============================================================================


def render_activity_report_card(report: Any) -> Any:
    """Render a single activity report card (server-side)."""
    title = getattr(report, "title", "") or "Activity Feedback"
    created_at = getattr(report, "created_at", None)
    time_period = getattr(report, "time_period", None)
    content = getattr(report, "processed_content", "") or ""
    truncated = content[:200] + ("..." if len(content) > 200 else "")
    ptype_str = get_processor_type_str(report)
    date_str = format_date(created_at)

    date_parts = [date_str] if date_str else []
    if time_period:
        date_parts.append(str(time_period))
    subtitle = " \u00b7 ".join(date_parts)

    return Card(
        CardBody(
            Div(
                Div(
                    P(title, cls="font-semibold mb-0 text-sm"),
                    P(subtitle, cls="text-xs text-muted-foreground mb-1") if subtitle else None,
                ),
                render_processor_badge(ptype_str),
                cls="flex items-start justify-between gap-2",
            ),
            P(truncated, cls="text-xs text-muted-foreground mt-1") if truncated else None,
            cls="p-3",
        ),
        cls="bg-background border border-border mb-2",
    )


def render_activity_report_list(items: list[Any]) -> Any:
    """Render the full list of activity reports (HTMX swap target)."""
    if not items:
        return Div(
            P(
                "No activity reports yet.",
                cls="text-center text-muted-foreground py-4",
            ),
            id="activity-feedback-list",
        )
    return Div(
        *[render_activity_report_card(r) for r in items],
        id="activity-feedback-list",
    )


# ============================================================================
# PROGRESS REPORT CARDS
# ============================================================================


def render_progress_report_card(report: Any) -> Any:
    """Render a single progress report card (server-side)."""
    title = getattr(report, "title", "") or "Activity Feedback"
    created_at = getattr(report, "created_at", None)
    time_period = getattr(report, "time_period", None)
    depth = getattr(report, "depth", None)
    domains_covered = getattr(report, "domains_covered", ()) or ()
    content = getattr(report, "processed_content", "") or ""
    ptype_str = get_processor_type_str(report)
    date_str = format_date(created_at)

    badges = []
    if time_period:
        badges.append(Badge(str(time_period), variant=BadgeT.outline, size=Size.sm))
    if depth:
        badges.append(Badge(str(depth), variant=BadgeT.outline, size=Size.sm))
    badges.append(render_processor_badge(ptype_str))

    domain_badges = [Badge(str(d), variant=BadgeT.ghost, size=Size.xs) for d in domains_covered]

    if content:
        content_section = Div(
            NotStr(
                "<details class='mt-2'>"
                "<summary class='cursor-pointer text-sm text-muted-foreground select-none'>"
                "Read insights</summary>"
            ),
            P(content, cls="text-sm mt-2 whitespace-pre-wrap"),
            NotStr("</details>"),
        )
    else:
        content_section = P(
            "No insights generated yet.",
            cls="text-sm text-foreground/40 mt-1",
        )

    return Card(
        CardBody(
            Div(
                Div(
                    H4(title, cls="font-semibold mb-0"),
                    P(date_str, cls="text-xs text-muted-foreground mb-0") if date_str else None,
                ),
                cls="flex items-start justify-between gap-4 mb-2",
            ),
            Div(*badges, cls="flex flex-wrap gap-1 mb-2") if badges else None,
            Div(*domain_badges, cls="flex flex-wrap gap-1 mb-2") if domain_badges else None,
            content_section,
            cls="p-4",
        ),
        cls="bg-background shadow-sm mb-3",
    )


def render_progress_report_list(items: list[Any]) -> Any:
    """Render the full list of progress reports (HTMX swap target)."""
    if not items:
        return Div(
            P(
                "No activity feedback yet. Generate your first one above!",
                cls="text-center text-muted-foreground py-4",
            ),
            id="progress-list",
        )
    return Div(
        *[render_progress_report_card(r) for r in items],
        id="progress-list",
    )
