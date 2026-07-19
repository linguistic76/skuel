"""
Submission Report & Progress UI Components
============================================

Renderers for teacher assessments, activity reports, and progress report cards.
Includes intelligence sections: trends, recommendations, life path, knowledge.
"""

from enum import Enum
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
    Span,
    Textarea,
    Ul,
)
from fasthtml.common import Button as HtmlButton

from ui.components import Button, ButtonT, Card, CardBody
from ui.feedback import Badge, BadgeT, Progress, ProgressT
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.format_date import format_date
from ui.primitives import ButtonLink

# ============================================================================
# SHARED HELPERS
# ============================================================================

_PROCESSOR_LABELS = {"llm": "LLM", "automatic": "Scheduled", "human": "Teacher"}
_PROCESSOR_BADGE_VARIANTS: dict[str, BadgeT] = {
    "llm": BadgeT.info,
    "automatic": BadgeT.ghost,
    "human": BadgeT.primary,
}


def _score_variant(score_pct: int) -> ProgressT:
    """Map a 0–100 score to a progress color band (≥70 success, ≥40 warning, else error)."""
    if score_pct >= 70:
        return ProgressT.success
    if score_pct >= 40:
        return ProgressT.warning
    return ProgressT.error


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
        return Badge("Awaiting Review", variant=BadgeT.info, size=Size.sm)
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

    # Allow deletion only when no feedback has been received yet
    delete_button: Any = ""
    if feedback_count == 0:
        delete_button = Button(
            "Delete",
            cls=(ButtonT.destructive, "ml-1"),
            size="sm",
            hx_post=f"/submissions/history/delete?uid={uid}",
            hx_target=f"#submission-row-{uid}",
            hx_swap="outerHTML",
            hx_confirm="Delete this submission? This cannot be undone.",
        )

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
                href=f"/gradebook/{uid}",
                cls=(ButtonT.primary, "ml-3"),
                size="sm",
            ),
            delete_button,
            cls="flex items-center gap-4",
        ),
        cls="bg-background shadow-sm mb-2",
        id=f"submission-row-{uid}",
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
    # Attribution is the AUTHOR (created_by), not the owner \u2014 reports are
    # owned by the student for access control.
    author_uid = getattr(assessment, "created_by", "") or getattr(assessment, "user_uid", "") or ""

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
                    f"From: {author_uid} \u00b7 {date_str} \u00b7 {source_label}",
                    cls="text-sm text-muted-foreground mb-2",
                ),
                P(preview, cls="text-sm"),
                ButtonLink(
                    "View Full",
                    href=f"/entry-reports/detail?uid={uid}",
                    cls=(ButtonT.primary, "mt-2"),
                    size="sm",
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
# EXERCISE REPORT DETAIL VIEW
# ============================================================================


_OUTCOME_LABELS: dict[str, tuple[str, BadgeT]] = {
    "approved": ("Approved", BadgeT.success),
    "needs_revision": ("Revision Requested", BadgeT.warning),
    "ai_evaluated": ("AI Evaluated", BadgeT.info),
}


def render_entry_report_detail(report: Any, revised_exercise: Any = None) -> Any:
    """Render the full detail view for a single EntryReport.

    Shows report content, outcome, processor type, assessment score,
    and a back link to the reports list.

    Args:
        report: EntryReport entity (or SubmissionEntity with report fields)
        revised_exercise: Optional RevisedExercise linked to this report
    """
    title = getattr(report, "title", "") or "Entry Report"
    report_content = getattr(report, "processed_content", "") or ""
    created_at = getattr(report, "created_at", None)
    user_uid = getattr(report, "user_uid", "") or ""
    subject_uid = getattr(report, "subject_uid", "") or ""
    assessment_score = getattr(report, "assessment_score", None)
    ptype_str = get_processor_type_str(report)
    date_str = format_date(created_at)

    # Outcome
    outcome_raw = getattr(report, "assessment_outcome", None)
    outcome_str = ""
    if outcome_raw is not None:
        _missing = object()
        outcome_val = getattr(outcome_raw, "value", _missing)
        outcome_str = str(outcome_val if outcome_val is not _missing else outcome_raw).lower()

    # Header badges
    badges: list[Any] = []
    if outcome_str:
        label, variant = _OUTCOME_LABELS.get(
            outcome_str, (outcome_str.replace("_", " ").title(), BadgeT.ghost)
        )
        badges.append(Badge(label, variant=variant))
    badges.append(render_processor_badge(ptype_str))

    # Metadata line — attribution is the AUTHOR (created_by), not the owner:
    # a teacher report is owned by the student (user_uid) for access control,
    # so "From: {user_uid}" credited the student with their own feedback.
    author_uid = getattr(report, "created_by", "") or ""
    meta_parts = []
    if author_uid or user_uid:
        source_label = "AI" if ptype_str == "llm" else "Teacher"
        meta_parts.append(f"From: {author_uid or user_uid} ({source_label})")
    if date_str:
        meta_parts.append(date_str)
    if subject_uid:
        meta_parts.append(f"Subject: {subject_uid}")

    # Assessment score section
    score_section: Any = None
    if assessment_score is not None:
        score_pct = round(float(assessment_score) * 100)
        score_section = Div(
            H3("Assessment Score", cls="font-semibold mb-3"),
            Div(
                P(f"{score_pct}%", cls="text-2xl font-bold mr-4"),
                Progress(value=score_pct, variant=_score_variant(score_pct), cls="flex-1"),
                cls="flex items-center mb-3",
            ),
            cls="mb-6",
        )

    # Report content section
    content_section = Div(
        H3("Report Content", cls="font-semibold mb-3"),
        P(report_content, cls="text-sm whitespace-pre-wrap leading-relaxed")
        if report_content
        else render_error_banner(
            "Report content is missing — this report may have incomplete data.", severity="warning"
        ),
        cls="mb-6",
    )

    # Revision section (when teacher requested revision)
    revision_section: Any = None
    if revised_exercise:
        re_uid = getattr(revised_exercise, "uid", "") or ""
        revision_section = Div(
            H3("Revision Requested", cls="font-semibold mb-3"),
            P(
                "Your teacher has created revision instructions for this submission.",
                cls="text-sm text-muted-foreground mb-3",
            ),
            Div(
                ButtonLink(
                    "View Revision Instructions \u2192",
                    href=f"/revised-exercises/detail?uid={re_uid}",
                    cls=ButtonT.primary,
                    size="sm",
                ),
                ButtonLink(
                    "Submit Revision",
                    href=f"/submit?exercise_uid={re_uid}",
                    cls=ButtonT.ghost,
                    size="sm",
                ),
                cls="flex flex-wrap gap-2",
            ),
            cls="mb-6 p-4 border border-amber-200 bg-amber-50 rounded-lg dark:border-amber-800 dark:bg-amber-950",
        )

    # Back link
    back = Div(
        ButtonLink(
            "\u2190 Back to Entry Reports",
            href="/entry-reports",
            cls=ButtonT.ghost,
        ),
        cls="mt-6",
    )

    return Div(
        # Header
        Div(
            P(title, cls="text-xl font-bold mb-1"),
            P(" \u00b7 ".join(meta_parts), cls="text-sm text-muted-foreground")
            if meta_parts
            else None,
            Div(*badges, cls="flex flex-wrap gap-2 mt-2") if badges else None,
            cls="mb-6",
        ),
        score_section,
        content_section,
        revision_section,
        back,
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

    domain_badges = [Badge(str(d), variant=BadgeT.ghost, size=Size.xs) for d in domains_covered]

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
            Card(
                card_content,
                cls="bg-background border border-border mb-2 hover:border-primary/50 transition-colors",
            ),
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
                action_text="Submit Activity Report",
                action_href="/submit-activity-report",
            ),
            id="activity-feedback-list",
        )
    return Div(
        *[render_activity_report_card(r) for r in items],
        id="activity-feedback-list",
    )


def render_time_period_filter(active_period: str = "") -> Any:
    """Render time-period filter buttons for activity reports."""
    periods = [
        ("", "All"),
        ("7d", "7 days"),
        ("14d", "14 days"),
        ("30d", "30 days"),
        ("90d", "90 days"),
    ]
    buttons = []
    for value, label in periods:
        is_active = value == active_period
        cls = "px-3 py-1 text-sm rounded-md border transition-colors "
        cls += (
            "bg-primary text-primary-foreground border-primary"
            if is_active
            else "bg-background text-foreground border-border hover:border-primary/50"
        )
        buttons.append(
            HtmlButton(
                label,
                cls=cls,
                hx_get=f"/reports/activity-list?time_period={value}",
                hx_target="#activity-feedback-list",
                hx_swap="outerHTML",
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
            status_str = status.value if isinstance(status, Enum) else str(status)
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
            Ul(*item_rows, cls="list-disc list-inside space-y-1")
            if item_rows
            else P("No items in this period.", cls="text-xs text-muted-foreground"),
            cls="p-3",
        ),
        cls="bg-muted/30 border border-border",
    )


def render_activity_report_detail(
    report: Any,
    snapshot: dict[str, Any] | None = None,
    intelligence: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
) -> Any:
    """Render the full detail view for a single ActivityReport.

    Args:
        report: ActivityReport entity
        snapshot: Report snapshot metadata (entity counts per domain)
        intelligence: Intelligence metadata (trends, patterns, recommendations, life path)
        comparison: Period-over-period comparison data (previous report deltas)
    """
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

    # Comparison banner (when prior report exists)
    comparison_section = _render_comparison_banner(comparison, intelligence) if comparison else None

    # Report content section
    content_section = Div(
        H3("Report Content", cls="font-semibold mb-3"),
        P(content, cls="text-sm whitespace-pre-wrap leading-relaxed")
        if content
        else render_error_banner("Report content has not been generated yet.", severity="info"),
        cls="mb-6",
    )

    # Intelligence sections (from baked metadata)
    intelligence_sections = _render_intelligence_sections(intelligence) if intelligence else []

    # Domain breakdown from snapshot metadata
    domain_cards: list[Any] = []
    if snapshot:
        domains_data = snapshot.get("domains", {})
        if domains_data:
            domain_cards.append(Hr(cls="my-6"))
            domain_cards.append(H3("Domain Breakdown", cls="font-semibold mb-3"))
            grid_items = [
                render_domain_summary_card(name, data) for name, data in domains_data.items()
            ]
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
                    cls=(ButtonT.primary, "cursor-pointer"),
                    size="sm",
                ),
                Div(id="annotation-status", cls="ml-3 text-sm"),
                cls="flex items-center",
            ),
            hx_post="/api/activity-reports/annotate",
            hx_target="#annotation-status",
            hx_swap="innerHTML",
            hx_vals="js:{"
            + '"uid": document.querySelector("[name=uid]").value,'
            + '"annotation_mode": document.querySelector("[name=annotation_mode]:checked").value,'
            + '"user_annotation": document.querySelector("[name=annotation_mode]:checked").value === "additive" ? document.querySelector("[name=annotation_text]").value : null,'
            + '"user_revision": document.querySelector("[name=annotation_mode]:checked").value === "revision" ? document.querySelector("[name=annotation_text]").value : null'
            + "}",
            hx_headers='{"Content-Type": "application/json"}',
        ),
    )

    # Back link
    back = Div(
        ButtonLink(
            "\u2190 Back to Activity Reports",
            href="/activity-reports",
            cls=ButtonT.ghost,
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
        comparison_section,
        content_section,
        *intelligence_sections,
        *domain_cards,
        annotation_section,
        back,
    )


# ============================================================================
# INTELLIGENCE UI SECTIONS
# ============================================================================

_TREND_ARROW = {"improved": "\u2191", "declined": "\u2193", "stable": "\u2192"}
_TREND_COLOR = {
    "improved": "text-green-600",
    "declined": "text-amber-600",
    "stable": "text-muted-foreground",
}


def _render_comparison_banner(
    comparison: dict[str, Any], intelligence: dict[str, Any] | None
) -> Any:
    """Render a compact period-over-period comparison banner at top of detail view."""
    previous_trends = comparison.get("previous_trends", {})
    current_trends = intelligence.get("domain_trends", {}) if intelligence else {}
    previous_period = comparison.get("previous_period", "")

    if not previous_trends or not current_trends:
        return None

    delta_chips = []
    for domain in ("tasks", "goals", "habits", "events", "choices", "principles"):
        prev = previous_trends.get(domain, {})
        curr = current_trends.get(domain, {})

        # Use the most meaningful metric per domain
        if domain == "tasks":
            prev_val = prev.get("completion_rate", 0)
            curr_val = curr.get("completion_rate", 0)
            label = "Tasks"
            fmt = "{:+.0%}"
        elif domain == "goals":
            prev_val = prev.get("avg_progress", 0)
            curr_val = curr.get("avg_progress", 0)
            label = "Goals"
            fmt = "{:+.0f}%"
        elif domain == "habits":
            prev_val = prev.get("avg_streak", 0)
            curr_val = curr.get("avg_streak", 0)
            label = "Habits"
            fmt = "{:+.1f}"
        else:
            prev_val = prev.get("total", 0)
            curr_val = curr.get("total", 0)
            label = domain.title()
            fmt = "{:+d}"

        delta = curr_val - prev_val
        if delta == 0:
            continue

        direction = "improved" if delta > 0 else "declined"
        arrow = _TREND_ARROW[direction]
        color = _TREND_COLOR[direction]
        try:
            delta_str = fmt.format(delta)
        except (ValueError, TypeError):  # fmt: skip
            delta_str = str(delta)

        delta_chips.append(Span(f"{label} {arrow}{delta_str}", cls=f"text-xs font-medium {color}"))

    # Life path delta
    prev_lp = comparison.get("previous_life_path_score")
    curr_lp = (intelligence or {}).get("life_path", {}).get("alignment_score")
    if prev_lp is not None and curr_lp is not None:
        lp_delta = curr_lp - prev_lp
        if lp_delta != 0:
            direction = "improved" if lp_delta > 0 else "declined"
            delta_chips.append(
                Span(
                    f"Life Path {_TREND_ARROW[direction]}{lp_delta:+.2f}",
                    cls=f"text-xs font-medium {_TREND_COLOR[direction]}",
                )
            )

    if not delta_chips:
        return None

    period_label = f"vs previous {previous_period}" if previous_period else "vs previous"
    return Card(
        CardBody(
            Div(
                Span(period_label, cls="text-xs text-muted-foreground mr-3"),
                *delta_chips,
                cls="flex flex-wrap items-center gap-3",
            ),
            cls="py-2 px-3",
        ),
        cls="bg-muted/20 border border-border mb-4",
    )


def _render_intelligence_sections(intelligence: dict[str, Any]) -> list[Any]:
    """Render all intelligence sections from baked metadata."""
    sections: list[Any] = []

    # Trends section
    domain_trends = intelligence.get("domain_trends")
    if domain_trends:
        sections.append(_render_trends_section(domain_trends))

    # Recommendations section
    recommendations = intelligence.get("recommendations")
    if recommendations:
        sections.append(_render_recommendations_section(recommendations))

    # Life path alignment section
    life_path = intelligence.get("life_path")
    if life_path and life_path.get("alignment_score") is not None:
        sections.append(_render_life_path_section(life_path))

    # Knowledge intelligence section
    knowledge = intelligence.get("knowledge")
    if knowledge:
        sections.append(_render_knowledge_section(knowledge))

    # Cross-domain patterns section
    patterns = intelligence.get("cross_domain_patterns")
    if patterns:
        sections.append(_render_cross_domain_section(patterns))

    # ZPD summary (FULL tier only)
    zpd = intelligence.get("zpd_summary")
    if zpd:
        sections.append(_render_zpd_section(zpd))

    return sections


def _render_trends_section(domain_trends: dict[str, Any]) -> Any:
    """Render per-domain trend indicators."""
    trend_cards = []
    for domain, data in domain_trends.items():
        metrics = []
        if "completion_rate" in data:
            rate = data["completion_rate"]
            metrics.append(P(f"Completion: {rate:.0%}", cls="text-xs text-muted-foreground"))
        if data.get("avg_progress"):
            metrics.append(
                P(f"Avg progress: {data['avg_progress']:.0f}%", cls="text-xs text-muted-foreground")
            )
        if data.get("avg_streak"):
            metrics.append(
                P(f"Avg streak: {data['avg_streak']:.1f}", cls="text-xs text-muted-foreground")
            )
        if data.get("milestones"):
            metrics.append(
                P(f"Milestones: {data['milestones']}", cls="text-xs text-muted-foreground")
            )
        if "principled" in data and data.get("total", 0) > 0:
            metrics.append(
                P(
                    f"Principle-guided: {data['principled']}/{data['total']}",
                    cls="text-xs text-muted-foreground",
                )
            )
        if "aligned" in data:
            metrics.append(
                P(
                    f"Aligned: {data['aligned']}, Needs attention: {data.get('needs_attention', 0)}",
                    cls="text-xs text-muted-foreground",
                )
            )

        total = data.get("total", 0)
        if total == 0 and not metrics:
            continue

        trend_cards.append(
            Div(
                P(domain.title(), cls="text-sm font-medium mb-1"),
                P(f"{total} total", cls="text-xs text-muted-foreground"),
                *metrics,
                cls="p-3 bg-muted/20 rounded-md border border-border",
            )
        )

    if not trend_cards:
        return Div()

    return Div(
        Hr(cls="my-6"),
        H3("Domain Trends", cls="font-semibold mb-3"),
        Div(*trend_cards, cls="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4"),
    )


def _render_recommendations_section(recommendations: list[dict[str, str]]) -> Any:
    """Render actionable recommendation cards."""
    if not recommendations:
        return Div()

    _severity_variant: dict[str, BadgeT] = {
        "warning": BadgeT.warning,
        "info": BadgeT.info,
        "critical": BadgeT.error,
    }

    items = []
    for rec in recommendations:
        severity = rec.get("severity", "info")
        domain = rec.get("domain", "")
        text = rec.get("text", "")
        variant = _severity_variant.get(severity, BadgeT.ghost)
        items.append(
            Div(
                Div(
                    Badge(domain.title(), variant=BadgeT.outline, size=Size.xs) if domain else None,
                    Badge(severity.title(), variant=variant, size=Size.xs),
                    cls="flex gap-1 mb-1",
                ),
                P(text, cls="text-sm"),
                cls="p-3 bg-muted/20 rounded-md border border-border",
            )
        )

    return Div(
        Hr(cls="my-6"),
        H3("Recommendations", cls="font-semibold mb-3"),
        Div(*items, cls="space-y-2 mb-4"),
    )


def _render_life_path_section(life_path: dict[str, Any]) -> Any:
    """Render life path alignment score and details."""
    score = life_path.get("alignment_score")
    if score is None:
        return Div()

    score_pct = round(score * 100) if isinstance(score, float) else 0

    details = []
    if life_path.get("life_path_title"):
        details.append(
            P(f"Path: {life_path['life_path_title']}", cls="text-sm text-muted-foreground")
        )
    if life_path.get("embodied_knowledge") is not None:
        details.append(
            P(
                f"Knowledge: {life_path.get('embodied_knowledge', 0)} embodied, "
                f"{life_path.get('theoretical_knowledge', 0)} theoretical",
                cls="text-sm text-muted-foreground",
            )
        )
    if life_path.get("recommendations"):
        recs = life_path["recommendations"][:3]
        details.append(
            Ul(
                *[Li(r, cls="text-xs text-muted-foreground") for r in recs],
                cls="list-disc list-inside mt-1",
            )
        )

    return Div(
        Hr(cls="my-6"),
        H3("Life Path Alignment", cls="font-semibold mb-3"),
        Div(
            Div(
                P(f"{score_pct}%", cls="text-2xl font-bold"),
                P("alignment score", cls="text-xs text-muted-foreground"),
                cls="mr-4",
            ),
            Div(
                Progress(value=score_pct, variant=_score_variant(score_pct)),
                cls="flex-1 pt-3",
            ),
            cls="flex items-start mb-3",
        ),
        *details,
        cls="mb-4",
    )


def _render_knowledge_section(knowledge: dict[str, Any]) -> Any:
    """Render knowledge intelligence (opportunities, suggestions)."""
    items: list[Any] = []

    suggestions = knowledge.get("suggestions", {})
    if isinstance(suggestions, dict):
        patterns = suggestions.get("entity_patterns", [])
        gaps = suggestions.get("knowledge_gaps", [])
        if patterns:
            items.append(
                Div(
                    H4("Knowledge Patterns", cls="text-sm font-medium mb-1"),
                    Ul(
                        *[
                            Li(p.get("pattern", ""), cls="text-xs text-muted-foreground")
                            for p in patterns[:5]
                        ],
                        cls="list-disc list-inside",
                    ),
                    cls="mb-2",
                )
            )
        if gaps:
            items.append(
                Div(
                    H4("Knowledge Gaps", cls="text-sm font-medium mb-1"),
                    Ul(
                        *[Li(g, cls="text-xs text-muted-foreground") for g in gaps[:5]],
                        cls="list-disc list-inside",
                    ),
                    cls="mb-2",
                )
            )

    opportunities = knowledge.get("opportunities", {})
    if isinstance(opportunities, dict):
        opps = opportunities.get("opportunities", [])
        focus = opportunities.get("recommended_focus", [])
        if opps:
            items.append(
                Div(
                    H4("Learning Opportunities", cls="text-sm font-medium mb-1"),
                    Ul(
                        *[
                            Li(o.get("title", ""), cls="text-xs text-muted-foreground")
                            for o in opps[:5]
                        ],
                        cls="list-disc list-inside",
                    ),
                    cls="mb-2",
                )
            )
        if focus:
            items.append(
                Div(
                    H4("Recommended Focus", cls="text-sm font-medium mb-1"),
                    Ul(
                        *[Li(f, cls="text-xs text-muted-foreground") for f in focus[:3]],
                        cls="list-disc list-inside",
                    ),
                    cls="mb-2",
                )
            )

    if not items:
        return Div()

    return Div(
        Hr(cls="my-6"),
        H3("Knowledge Intelligence", cls="font-semibold mb-3"),
        *items,
    )


def _render_cross_domain_section(patterns: dict[str, Any]) -> Any:
    """Render cross-domain pattern insights."""
    items: list[Any] = []

    # Choice-principle alignment
    cpa = patterns.get("choice_principle_alignment", {})
    if isinstance(cpa, dict) and cpa.get("alignment_ratio") is not None:
        ratio = cpa["alignment_ratio"]
        items.append(
            P(
                f"Choice-principle alignment: {ratio:.0%}",
                cls="text-sm text-muted-foreground",
            )
        )

    # Goal-habit support
    ghs = patterns.get("goal_habit_support", {})
    if isinstance(ghs, dict) and ghs.get("supported_goals") is not None:
        items.append(
            P(
                f"Goals with habit support: {ghs['supported_goals']}",
                cls="text-sm text-muted-foreground",
            )
        )

    # Domain balance
    balance = patterns.get("domain_balance", {})
    if isinstance(balance, dict) and balance.get("balance_score") is not None:
        items.append(
            P(
                f"Domain balance score: {balance['balance_score']:.2f}",
                cls="text-sm text-muted-foreground",
            )
        )

    if not items:
        return Div()

    return Div(
        Hr(cls="my-6"),
        H3("Cross-Domain Insights", cls="font-semibold mb-3"),
        *items,
        cls="mb-4",
    )


def _render_zpd_section(zpd: dict[str, Any]) -> Any:
    """Render Zone of Proximal Development summary (FULL tier only).

    Reads the summary baked by ``ProgressReportGenerator._extract_zpd_summary``:
    ``proximal_count`` / ``max_readiness`` (dict-derived — there is no scalar
    per-user readiness on ZPDAssessment), plus gap and action counts. Older
    baked snapshots without these keys collapse to whatever counts they carry.
    """
    proximal = zpd.get("proximal_count", 0)
    max_readiness = zpd.get("max_readiness")
    blocking = zpd.get("blocking_gaps_count", 0)
    recommended = zpd.get("recommended_count", 0)

    items = []
    if proximal > 0:
        items.append(P(f"Ready next steps: {proximal}", cls="text-sm"))
    if max_readiness is not None:
        items.append(P(f"Top readiness: {max_readiness:.0%}", cls="text-sm"))
    if blocking > 0:
        items.append(P(f"Blocking gaps: {blocking}", cls="text-sm text-amber-600"))
    if recommended > 0:
        items.append(P(f"Recommended actions: {recommended}", cls="text-sm text-muted-foreground"))

    if not items:
        return Div()

    return Div(
        Hr(cls="my-6"),
        H3("Zone of Proximal Development", cls="font-semibold mb-3"),
        *items,
        cls="mb-4",
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
