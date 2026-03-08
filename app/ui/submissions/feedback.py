"""
Submission Feedback & Progress UI Components
=============================================

Renderers for teacher assessments, activity feedback, and progress report cards.
"""

from typing import Any

from fasthtml.common import H4, Div, NotStr, P, Span

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
    """Render a DaisyUI badge for processor type (LLM / Scheduled / Admin)."""
    label = _PROCESSOR_LABELS.get(processor_type_str, processor_type_str or "AI")
    badge_cls = _PROCESSOR_BADGE_CLASSES.get(processor_type_str, "badge-ghost")
    return Span(label, cls=f"badge {badge_cls} badge-sm")


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
    """Return a DaisyUI badge indicating the teacher review outcome."""
    if feedback_count > 0 and status == "completed":
        return Span("Reviewed", cls="badge badge-success badge-sm")
    if status == "revision_requested":
        return Span("Revision Needed", cls="badge badge-warning badge-sm")
    if feedback_count == 0 and status == "submitted":
        return Span("Awaiting Review", cls="badge badge-neutral badge-sm")
    return Span(status.replace("_", " ").title(), cls="badge badge-ghost badge-sm")


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
        feedback_chip = Span(label, cls="badge badge-outline badge-sm ml-2")

    return Div(
        Div(
            Div(
                P(filename, cls="font-semibold mb-0"),
                P(created_str, cls="text-xs text-base-content/50 mb-0"),
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
        cls="card bg-base-100 shadow-sm mb-2",
    )


def render_yours_list(items: list[dict]) -> Any:
    """Render the full list of submissions with feedback status (HTMX swap target)."""
    if not items:
        return Div(
            P(
                "No submissions yet.",
                cls="text-center text-base-content/60 py-8",
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


def render_feedback_card(assessment: Any) -> Any:
    """Render a single received-feedback card (server-side, no inline JS)."""
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
        Div(
            Div(
                H4(title, cls="font-semibold mb-1"),
                P(
                    f"From: {user_uid} \u00b7 {date_str} \u00b7 {source_label}",
                    cls="text-sm text-base-content/60 mb-2",
                ),
                P(preview, cls="text-sm"),
                A("View Full", href=f"/submissions/{uid}", cls="btn btn-sm btn-ghost mt-2"),
                cls="card-body p-4",
            ),
            cls="card bg-base-100 shadow-sm mb-3",
        ),
    )


def render_received_feedback_list(items: list[Any]) -> Any:
    """Render the full list of received feedback (HTMX swap target)."""
    if not items:
        return Div(
            P("No feedback yet.", cls="text-center text-base-content/60 py-6"),
            P(
                "Assessments from teachers will appear here once submitted.",
                cls="text-sm text-center text-base-content/40",
            ),
            id="feedback-list",
        )
    return Div(
        *[render_feedback_card(a) for a in items],
        id="feedback-list",
    )


# ============================================================================
# ACTIVITY FEEDBACK CARDS
# ============================================================================


def render_activity_feedback_card(report: Any) -> Any:
    """Render a single activity feedback card (server-side)."""
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

    return Div(
        Div(
            Div(
                Div(
                    P(title, cls="font-semibold mb-0 text-sm"),
                    P(subtitle, cls="text-xs text-base-content/50 mb-1") if subtitle else None,
                ),
                render_processor_badge(ptype_str),
                cls="flex items-start justify-between gap-2",
            ),
            P(truncated, cls="text-xs text-base-content/70 mt-1") if truncated else None,
            cls="card-body p-3",
        ),
        cls="card bg-base-100 border border-base-200 mb-2",
    )


def render_activity_feedback_list(items: list[Any]) -> Any:
    """Render the full list of activity feedback (HTMX swap target)."""
    if not items:
        return Div(
            P(
                "No activity feedback yet.",
                cls="text-center text-base-content/60 py-4",
            ),
            id="activity-feedback-list",
        )
    return Div(
        *[render_activity_feedback_card(r) for r in items],
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
        badges.append(Span(str(time_period), cls="badge badge-outline badge-sm"))
    if depth:
        badges.append(Span(str(depth), cls="badge badge-outline badge-sm"))
    badges.append(render_processor_badge(ptype_str))

    domain_badges = [Span(str(d), cls="badge badge-ghost badge-xs") for d in domains_covered]

    if content:
        content_section = Div(
            NotStr(
                "<details class='mt-2'>"
                "<summary class='cursor-pointer text-sm text-base-content/70 select-none'>"
                "Read insights</summary>"
            ),
            P(content, cls="text-sm mt-2 whitespace-pre-wrap"),
            NotStr("</details>"),
        )
    else:
        content_section = P(
            "No insights generated yet.",
            cls="text-sm text-base-content/40 mt-1",
        )

    return Div(
        Div(
            Div(
                Div(
                    H4(title, cls="font-semibold mb-0"),
                    P(date_str, cls="text-xs text-base-content/60 mb-0") if date_str else None,
                ),
                cls="flex items-start justify-between gap-4 mb-2",
            ),
            Div(*badges, cls="flex flex-wrap gap-1 mb-2") if badges else None,
            Div(*domain_badges, cls="flex flex-wrap gap-1 mb-2") if domain_badges else None,
            content_section,
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-3",
    )


def render_progress_report_list(items: list[Any]) -> Any:
    """Render the full list of progress reports (HTMX swap target)."""
    if not items:
        return Div(
            P(
                "No activity feedback yet. Generate your first one above!",
                cls="text-center text-base-content/60 py-4",
            ),
            id="progress-list",
        )
    return Div(
        *[render_progress_report_card(r) for r in items],
        id="progress-list",
    )
