"""
Submission Report & Progress UI Components
============================================

Renderers for teacher assessments, activity reports, and progress report cards.
"""

from typing import Any

from fasthtml.common import (
    H3,
    H4,
    A,
    Div,
    Form,
    Hr,
    Input,
    Label,
    Li,
    NotStr,
    P,
    Textarea,
    Ul,
)
from fasthtml.common import Button as HtmlButton

from ui.buttons import ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.empty_state import EmptyState

# ============================================================================
# SHARED HELPERS
# ============================================================================

_PROCESSOR_LABELS = {"llm": "LLM", "automatic": "Scheduled", "human": "Admin"}
_PROCESSOR_BADGE_VARIANTS: dict[str, BadgeT] = {
    "llm": BadgeT.info,
    "automatic": BadgeT.ghost,
    "human": BadgeT.primary,
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
    variant = _PROCESSOR_BADGE_VARIANTS.get(processor_type_str, BadgeT.ghost)
    return Badge(label, variant=variant, size=Size.sm)


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
            ButtonLink(
                "View",
                href=f"/submissions/{uid}",
                variant=ButtonT.secondary,
                size=Size.sm,
                cls="ml-3",
            ),
            cls="flex items-center gap-4",
        ),
        cls="bg-background shadow-sm mb-2",
    )


def render_yours_list(items: list[dict]) -> Any:
    """Render the full list of submissions with feedback status (HTMX swap target)."""
    if not items:
        return Div(
            EmptyState(title="No submissions yet"),
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
                ButtonLink(
                    "View Full",
                    href=f"/submissions/{uid}",
                    variant=ButtonT.secondary,
                    size=Size.sm,
                    cls="mt-2",
                ),
                cls="p-4",
            ),
            cls="bg-background shadow-sm mb-3",
        ),
    )


def render_received_report_list(items: list[Any]) -> Any:
    """Render the full list of received reports (HTMX swap target)."""
    if not items:
        return Div(
            EmptyState(
                title="No reports yet",
                description="Assessments from teachers will appear here once submitted.",
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
    """Render a single activity report card — clickable link to detail view."""
    uid = getattr(report, "uid", "") or ""
    title = getattr(report, "title", "") or "Activity Feedback"
    created_at = getattr(report, "created_at", None)
    time_period = getattr(report, "time_period", None)
    domains_covered = getattr(report, "domains_covered", ()) or ()
    content = getattr(report, "processed_content", "") or ""
    truncated = content[:200] + ("..." if len(content) > 200 else "")
    ptype_str = get_processor_type_str(report)
    date_str = format_date(created_at)

    date_parts = [date_str] if date_str else []
    if time_period:
        date_parts.append(str(time_period))
    subtitle = " \u00b7 ".join(date_parts)

    domain_badges = [
        Badge(str(d), variant=BadgeT.ghost, size=Size.xs) for d in domains_covered
    ]

    card_content = CardBody(
        Div(
            Div(
                P(title, cls="font-semibold mb-0 text-sm"),
                P(subtitle, cls="text-xs text-muted-foreground mb-1") if subtitle else None,
            ),
            render_processor_badge(ptype_str),
            cls="flex items-start justify-between gap-2",
        ),
        Div(*domain_badges, cls="flex flex-wrap gap-1 mt-1") if domain_badges else None,
        P(truncated, cls="text-xs text-muted-foreground mt-1") if truncated else None,
        cls="p-3",
    )

    if uid:
        return A(
            Card(card_content, cls="bg-background border border-border mb-2 hover:border-primary/50 transition-colors"),
            href=f"/activity-reports/detail?uid={uid}",
            cls="block no-underline text-foreground",
        )
    return Card(card_content, cls="bg-background border border-border mb-2")


def render_activity_report_list(items: list[Any]) -> Any:
    """Render the full list of activity reports (HTMX swap target)."""
    if not items:
        return Div(
            EmptyState(
                title="No activity reports yet",
                description="Generate your first report or wait for a scheduled one.",
                action_text="Generate Report",
                action_href="/generate-reports",
            ),
            id="activity-feedback-list",
        )
    return Div(
        *[render_activity_report_card(r) for r in items],
        id="activity-feedback-list",
    )


def render_time_period_filter(active_period: str = "") -> Any:
    """Render time-period filter buttons for activity reports."""
    periods = [("", "All"), ("7d", "7 days"), ("14d", "14 days"), ("30d", "30 days"), ("90d", "90 days")]
    buttons = []
    for value, label in periods:
        is_active = value == active_period
        cls = "px-3 py-1 text-sm rounded-md border transition-colors "
        cls += "bg-primary text-primary-foreground border-primary" if is_active else "bg-background text-foreground border-border hover:border-primary/50"
        buttons.append(
            HtmlButton(
                label,
                cls=cls,
                **{
                    "hx-get": f"/reports/activity-list?time_period={value}",
                    "hx-target": "#activity-feedback-list",
                    "hx-swap": "outerHTML",
                },
            )
        )
    return Div(*buttons, cls="flex gap-2 flex-wrap mb-4")


# ============================================================================
# ACTIVITY REPORT DETAIL VIEW
# ============================================================================


def render_domain_summary_card(domain_name: str, data: dict[str, Any]) -> Any:
    """Render a summary card for a single domain within a report snapshot."""
    count = data.get("count", 0)
    completed = data.get("completed")
    items = data.get("items", [])

    stats_parts = [f"{count} total"]
    if completed is not None:
        stats_parts.append(f"{completed} completed")

    item_rows = []
    for item in items[:5]:
        title = item.get("title", "Untitled")
        status = item.get("status", "")
        extra_parts = []
        if status:
            status_str = status.value if hasattr(status, "value") else str(status)
            extra_parts.append(status_str)
        if item.get("progress") is not None:
            extra_parts.append(f"{item['progress']}%")
        if item.get("streak"):
            extra_parts.append(f"streak: {item['streak']}")
        if item.get("alignment") is not None:
            extra_parts.append(f"alignment: {item['alignment']}")
        suffix = f" ({', '.join(extra_parts)})" if extra_parts else ""
        item_rows.append(Li(f"{title}{suffix}", cls="text-sm text-muted-foreground"))

    return Card(
        CardBody(
            Div(
                H4(domain_name.replace("_", " ").title(), cls="font-semibold mb-0 text-sm"),
                P(", ".join(stats_parts), cls="text-xs text-muted-foreground"),
                cls="mb-2",
            ),
            Ul(*item_rows, cls="list-disc list-inside space-y-1") if item_rows else P("No items in this period.", cls="text-xs text-muted-foreground"),
            cls="p-3",
        ),
        cls="bg-muted/30 border border-border",
    )


def render_activity_report_detail(report: Any, snapshot: dict[str, Any] | None = None) -> Any:
    """Render the full detail view for a single ActivityReport."""
    uid = getattr(report, "uid", "") or ""
    title = getattr(report, "title", "") or "Activity Report"
    created_at = getattr(report, "created_at", None)
    time_period = getattr(report, "time_period", None)
    depth = getattr(report, "depth", None)
    domains_covered = getattr(report, "domains_covered", ()) or ()
    content = getattr(report, "processed_content", "") or ""
    ptype_str = get_processor_type_str(report)
    date_str = format_date(created_at)
    annotation_mode = getattr(report, "annotation_mode", None)
    user_annotation = getattr(report, "user_annotation", None)
    user_revision = getattr(report, "user_revision", None)

    # Header badges
    badges = []
    if time_period:
        badges.append(Badge(str(time_period), variant=BadgeT.outline, size=Size.sm))
    if depth:
        badges.append(Badge(str(depth), variant=BadgeT.outline, size=Size.sm))
    badges.append(render_processor_badge(ptype_str))
    domain_badges = [Badge(str(d), variant=BadgeT.ghost, size=Size.sm) for d in domains_covered]

    # Report content section
    content_section = Div(
        H3("Report Content", cls="font-semibold mb-3"),
        P(content, cls="text-sm whitespace-pre-wrap leading-relaxed") if content else P("No content generated.", cls="text-sm text-muted-foreground"),
        cls="mb-6",
    )

    # Domain breakdown from snapshot metadata
    domain_cards: list[Any] = []
    if snapshot:
        domains_data = snapshot.get("domains", {})
        if domains_data:
            domain_cards.append(Hr(cls="my-6"))
            domain_cards.append(H3("Domain Breakdown", cls="font-semibold mb-3"))
            grid_items = [render_domain_summary_card(name, data) for name, data in domains_data.items()]
            domain_cards.append(Div(*grid_items, cls="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6"))

    # Annotation section
    existing_text = ""
    if annotation_mode == "additive" and user_annotation:
        existing_text = user_annotation
    elif annotation_mode == "revision" and user_revision:
        existing_text = user_revision

    annotation_section = Div(
        Hr(cls="my-6"),
        H3("Your Notes", cls="font-semibold mb-3"),
        P(
            "Add your own commentary or revision to this report.",
            cls="text-sm text-muted-foreground mb-3",
        ),
        Form(
            Input(type="hidden", name="uid", value=uid),
            Div(
                Div(
                    Label(
                        Input(
                            type="radio",
                            name="annotation_mode",
                            value="additive",
                            checked=annotation_mode != "revision",
                            cls="mr-1",
                        ),
                        "Add commentary",
                        cls="text-sm cursor-pointer",
                    ),
                    Label(
                        Input(
                            type="radio",
                            name="annotation_mode",
                            value="revision",
                            checked=annotation_mode == "revision",
                            cls="mr-1 ml-4",
                        ),
                        "Replace for sharing",
                        cls="text-sm cursor-pointer",
                    ),
                    cls="flex items-center mb-2",
                ),
                Textarea(
                    existing_text,
                    name="annotation_text",
                    rows="4",
                    placeholder="Write your notes here...",
                    cls="w-full p-2 border border-border rounded-md text-sm bg-background",
                ),
                cls="mb-3",
            ),
            Div(
                ButtonLink(
                    "Save Notes",
                    href="#",
                    variant=ButtonT.primary,
                    size=Size.sm,
                    cls="cursor-pointer",
                ),
                Div(id="annotation-status", cls="ml-3 text-sm"),
                cls="flex items-center",
            ),
            **{
                "hx-post": "/api/activity-reports/annotate",
                "hx-target": "#annotation-status",
                "hx-swap": "innerHTML",
                "hx-vals": 'js:{'
                    + '"uid": document.querySelector("[name=uid]").value,'
                    + '"annotation_mode": document.querySelector("[name=annotation_mode]:checked").value,'
                    + '"user_annotation": document.querySelector("[name=annotation_mode]:checked").value === "additive" ? document.querySelector("[name=annotation_text]").value : null,'
                    + '"user_revision": document.querySelector("[name=annotation_mode]:checked").value === "revision" ? document.querySelector("[name=annotation_text]").value : null'
                    + '}',
                "hx-headers": '{"Content-Type": "application/json"}',
            },
        ),
    )

    # Back link
    back = Div(
        ButtonLink(
            "\u2190 Back to Activity Reports",
            href="/activity-reports",
            variant=ButtonT.ghost,
        ),
        cls="mt-6",
    )

    return Div(
        Div(
            P(title, cls="text-xl font-bold mb-1"),
            P(date_str, cls="text-sm text-muted-foreground") if date_str else None,
            Div(*badges, cls="flex flex-wrap gap-1 mt-2") if badges else None,
            Div(*domain_badges, cls="flex flex-wrap gap-1 mt-1") if domain_badges else None,
            cls="mb-6",
        ),
        content_section,
        *domain_cards,
        annotation_section,
        back,
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
