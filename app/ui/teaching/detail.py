"""
Teaching UI Detail Components
=============================

Submission content display and row components for detail views.
"""

from typing import Any

from fasthtml.common import H3, H4, Div, Form, Input, Label, P, Span

from core.models.report.entry_report import EntryReport
from ui.components import Button, ButtonT, Card, CardBody
from ui.feedback import Badge, BadgeT, StatusBadge
from ui.forms import Textarea
from ui.layout import Size
from ui.patterns.card_generator import CardGenerator
from ui.patterns.sidebar import SidebarItem
from ui.patterns.skeleton import SkeletonLines
from ui.primitives import ButtonLink
from ui.teaching.badges import entity_type_badge
from ui.teaching.types import (
    NEEDS_REVIEW_STATUSES,
    ClassMember,
    SubmissionDetail,
    SubmissionRow,
)


def render_submission_content(detail: SubmissionDetail) -> Div:
    """
    Render the submission content card for teacher review.

    Shows processed_content if available, then content, then filename as fallback.
    Also surfaces exercise instructions for teacher reference.
    """
    student_name = detail.student_name or detail.student_uid or "Unknown"

    # Display file path or fall back to original filename
    display_content = detail.file_path or detail.original_filename or "(No file path available)"

    meta_parts = [f"by {student_name}"]
    if detail.exercise_title:
        meta_parts.append(f"Exercise: {detail.exercise_title}")

    exercise_section: Any = ""
    if detail.exercise_instructions:
        exercise_section = Div(
            Div(
                Span(
                    "Exercise instructions",
                    cls="text-xs font-semibold text-muted-foreground uppercase tracking-wide",
                ),
                P(
                    detail.exercise_instructions,
                    cls="text-sm text-muted-foreground whitespace-pre-wrap mt-1",
                ),
                cls="p-3 bg-muted/50 rounded-sm",
            ),
            cls="mb-3",
        )

    return Card(
        CardBody(
            Div(
                Div(
                    H4(detail.title or "Untitled", cls="font-semibold mb-1"),
                    P(" · ".join(meta_parts), cls="text-sm text-muted-foreground mb-0"),
                    cls="flex-1",
                ),
                Div(
                    entity_type_badge(detail.entity_type),
                    StatusBadge(detail.status),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-start justify-between gap-4 mb-4",
            ),
            exercise_section,
            Div(
                Span(
                    "Submission File Location",
                    cls="text-xs font-semibold text-muted-foreground uppercase tracking-wide",
                ),
                Div(
                    P(display_content, cls="text-sm font-mono break-all"),
                    cls="mt-1 p-3 bg-muted/50 rounded-sm border border-border select-all",
                ),
                cls="p-4 bg-muted/20 border-t",
            ),
            cls="p-4",
        ),
        cls="bg-background shadow-xs mb-4",
    )


def render_report_item(report: EntryReport) -> Div:
    """Render a single typed EntryReport. Delegates to shared component."""
    from ui.patterns.report_item import render_report_item as _shared_render

    return _shared_render(report)


def render_review_panel_inline(uid: str, detail: dict[str, Any], history: list[EntryReport]) -> Div:
    """
    Inline review panel fragment — loaded by HTMX into a submission card drawer.

    Renders: submission content, feedback history, and action forms (if actionable).
    Returned by GET /api/teaching/review/{uid}/panel.
    """
    dom_id = uid.replace(":", "-").replace(".", "-")
    status = (detail.get("status") or "").lower()
    is_actionable = status in NEEDS_REVIEW_STATUSES

    # Submission content
    if detail:
        d = SubmissionDetail(
            title=detail.get("title", "Untitled"),
            entity_type=detail.get("entity_type"),
            status=status,
            student_name=detail.get("student_name") or detail.get("student_uid") or "Unknown",
            student_uid=detail.get("student_uid", ""),
            exercise_title=detail.get("exercise_title"),
            exercise_instructions=detail.get("exercise_instructions"),
            processed_content=detail.get("processed_content"),
            content=detail.get("content"),
            original_filename=detail.get("original_filename"),
            file_path=detail.get("file_path"),
        )
        content_section: Any = render_submission_content(d)
    else:
        content_section = P(
            "Submission content unavailable.",
            cls="text-sm text-muted-foreground italic mb-4",
        )

    # Feedback history
    history_section: Any = ""
    if history:
        history_section = Div(
            H3("Feedback History", cls="text-base font-semibold mb-2"),
            Div(*[render_report_item(fb) for fb in history]),
            cls="mb-4",
        )

    # Action forms — only shown for actionable statuses
    actions_section: Any = ""
    if is_actionable:
        actions_section = Div(
            # Submit feedback (.md upload)
            Card(
                CardBody(
                    P(
                        "Upload your feedback as a Markdown file (.md).",
                        cls="text-sm text-muted-foreground mb-3",
                    ),
                    Form(
                        Div(
                            Label(
                                "Feedback file",
                                fr=f"feedback_file_{dom_id}",
                                cls="text-sm font-medium mb-1 block",
                            ),
                            Input(
                                type="file",
                                name="feedback_file",
                                id=f"feedback_file_{dom_id}",
                                accept=".md",
                                required=True,
                                cls="block w-full text-sm file:mr-3 file:py-1 file:px-3 file:rounded-sm file:border-0 file:text-sm file:bg-primary file:text-primary-foreground hover:file:bg-primary/90 cursor-pointer",
                            ),
                            cls="mb-4",
                        ),
                        Button("Submit Feedback", cls=ButtonT.primary, type="submit"),
                        enctype="multipart/form-data",
                        hx_post=f"/api/teaching/review/{uid}/report",
                        hx_target=f"#inline-result-{dom_id}",
                        hx_swap="innerHTML",
                        hx_encoding="multipart/form-data",
                    ),
                    cls="p-4",
                ),
                cls="bg-background shadow-xs mb-2",
            ),
            # Request revision + approve
            Card(
                CardBody(
                    P(
                        "Request the student revise their work, or approve as-is.",
                        cls="text-sm text-muted-foreground mb-3",
                    ),
                    Form(
                        # Hidden exercise_uid for RevisedExercise creation
                        Input(
                            type="hidden",
                            name="exercise_uid",
                            value=detail.get("exercise_uid", ""),
                        ),
                        # Instructions (required)
                        Div(
                            Label(
                                "Revision instructions",
                                fr=f"revision_instructions_{dom_id}",
                                cls="text-sm font-medium mb-1 block",
                            ),
                            Textarea(
                                name="instructions",
                                id=f"revision_instructions_{dom_id}",
                                placeholder="What should the student do differently?",
                                cls="h-20",
                                required=True,
                            ),
                            cls="mb-3",
                        ),
                        # Feedback points (Alpine-managed dynamic rows)
                        Div(
                            Label(
                                "Feedback points",
                                cls="text-sm font-medium mb-1 block",
                            ),
                            P(
                                "Categorize the specific gaps in the student's work.",
                                cls="text-xs text-muted-foreground mb-2",
                            ),
                            Div(
                                id=f"fp-rows-{dom_id}",
                                **{"x-ref": "fpRows"},
                            ),
                            Div(
                                Button(
                                    "+ Add feedback point",
                                    cls=ButtonT.ghost,
                                    size="sm",
                                    type="button",
                                    **{"@click": "addPoint()"},  # fasthtml dynamic-attr splat
                                ),
                                cls="mb-2",
                            ),
                            Input(
                                type="hidden",
                                name="fp_count",
                                value="0",
                                **{"x-bind:value": "points.length"},
                            ),
                            cls="mb-3",
                            **{"x-data": "revisionForm()"},
                        ),
                        # Revision rationale (optional)
                        Div(
                            Label(
                                "Revision rationale",
                                fr=f"revision_rationale_{dom_id}",
                                cls="text-sm font-medium mb-1 block",
                            ),
                            P(
                                "Optional: explain why this revision is needed.",
                                cls="text-xs text-muted-foreground mb-1",
                            ),
                            Textarea(
                                name="revision_rationale",
                                id=f"revision_rationale_{dom_id}",
                                placeholder="Why is this revision needed?",
                                cls="h-16",
                            ),
                            cls="mb-3",
                        ),
                        Div(
                            Button(
                                "Request Revision",
                                cls=ButtonT.secondary,
                                type="submit",
                            ),
                            Button(
                                "Approve",
                                cls=ButtonT.primary,
                                type="button",
                                hx_post=f"/api/teaching/review/{uid}/approve",
                                hx_target=f"#inline-result-{dom_id}",
                                hx_swap="innerHTML",
                                hx_confirm="Approve this submission?",
                            ),
                            cls="flex gap-3",
                        ),
                        hx_post=f"/api/teaching/review/{uid}/revision",
                        hx_target=f"#inline-result-{dom_id}",
                        hx_swap="innerHTML",
                    ),
                    cls="p-4",
                ),
                cls="bg-background shadow-xs",
            ),
            Div(id=f"inline-result-{dom_id}", cls="mt-3"),
        )

    return Div(
        content_section,
        history_section,
        actions_section,
        cls="mt-3 border-t border-border pt-3",
    )


def render_student_submission_inline_row(item: SubmissionRow) -> Div:
    """
    Submission row with clickable accordion header and HTMX-loaded review panel.

    Clicking the header lazy-loads the panel via HTMX on first click,
    then toggles visibility on subsequent clicks. No "Review" button —
    the student detail page is already the review context.
    """
    title = item.title or item.original_filename or "Untitled"
    dom_id = item.uid.replace(":", "-").replace(".", "-")

    badges: list[Any] = []
    if item.feedback_count > 0:
        badges.append(Badge(f"{item.feedback_count} feedback", variant=BadgeT.info, size=Size.sm))
    badges.append(StatusBadge(item.status))

    exercise_label: Any = ""
    if item.exercise_title:
        exercise_label = Span(
            f" · {item.exercise_title}",
            cls="text-sm text-muted-foreground font-normal",
        )

    delete_btn = Button(
        "Delete",
        cls=(ButtonT.destructive, "text-xs"),
        size="sm",
        **{"@click.stop": ""},  # fasthtml dynamic-attr splat
        hx_post=f"/api/teaching/submissions/{item.uid}/delete",
        hx_target=f"#row-{dom_id}",
        hx_swap="outerHTML",
        hx_confirm="Delete this submission? This cannot be undone.",
    )

    header = Div(
        Div(
            Div(
                H4(title, cls="font-semibold mb-0"),
                exercise_label,
                cls="flex items-baseline gap-1 flex-1 min-w-0",
            ),
            Div(
                *badges,
                delete_btn,
                Span(
                    "▸",
                    cls="text-muted-foreground ml-1 inline-block transition-transform duration-200",
                    **{":class": "open && 'rotate-90'"},
                ),
                cls="flex gap-2 items-center shrink-0",
            ),
            cls="flex items-center justify-between gap-4",
        ),
        cls="px-4 py-3 bg-background border border-border rounded-sm cursor-pointer hover:bg-muted/50 transition-colors select-none",
        **{"@click": "open = !open"},
        hx_get=f"/api/teaching/review/{item.uid}/panel",
        hx_target=f"#panel-{dom_id}",
        hx_swap="innerHTML",
        hx_trigger="click once",
    )

    panel = Div(
        SkeletonLines(count=3),
        id=f"panel-{dom_id}",
        **{"x-show": "open"},
    )

    return Div(
        header,
        panel,
        id=f"row-{dom_id}",
        cls="mb-3",
        **{"x-data": "{ open: false }"},
    )


def _render_submission_list(items: list[SubmissionRow], empty_message: str) -> Any:
    """Inline rows for a submission list, or a centered empty-state message."""
    if not items:
        return P(empty_message, cls="text-center text-muted-foreground py-8 text-sm")
    return Div(*[render_student_submission_inline_row(item) for item in items])


def _render_ku_progress(ku_detail: dict[str, Any] | None) -> Any:
    """KU progress summary + detail list, or an unavailable message."""
    if ku_detail is None:
        return P(
            "KU progress data unavailable.",
            cls="text-center text-muted-foreground py-8 text-sm",
        )
    from ui.admin.views import AdminLearningComponents

    return Div(
        AdminLearningComponents.render_user_ku_summary(ku_detail),
        Div(cls="mb-6"),
        AdminLearningComponents.render_user_ku_detail_list(ku_detail),
    )


def render_student_detail_tabs(
    pending: list[SubmissionRow],
    revision_requested: list[SubmissionRow],
    completed: list[SubmissionRow],
    student_name: str,
    ku_detail: dict[str, Any] | None = None,
    default_tab: str | None = None,
) -> Div:
    """
    Tabbed view of a student's submissions grouped by workflow status,
    plus an optional KU Progress tab.

    Tabs: Needs Review | Revision Requested | Completed | KU Progress
    Pending submissions have inline HTMX review panels.
    Other submissions show read-only rows with feedback history toggle.
    KU Progress tab shows learning state from AdminLearningComponents.
    """

    def _tab_button(tab_id: str, label: str, count: int | None = None) -> Any:
        count_badge: Any = ""
        if count:
            count_badge = Span(
                str(count),
                cls="ml-2 px-2 py-0.5 text-xs font-semibold rounded-full bg-primary/10",
            )
        return Div(
            Span(label),
            count_badge,
            cls="flex items-center gap-1 px-5 py-3 text-base font-semibold border-b-3 cursor-pointer transition-colors",
            **{
                "@click": f"tab = '{tab_id}'",
                ":class": f"tab === '{tab_id}' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'",
            },
        )

    if default_tab is None:
        default_tab = "pending" if pending else ("revision" if revision_requested else "completed")

    # Tab bar items
    tab_buttons = [
        _tab_button("pending", "Needs Review", len(pending)),
        _tab_button("revision", "Revision Requested", len(revision_requested)),
        _tab_button("completed", "Completed", len(completed)),
    ]
    # Tab panels
    tab_panels = [
        Div(
            _render_submission_list(pending, "No submissions awaiting review."),
            **{"x-show": "tab === 'pending'"},
        ),
        Div(
            _render_submission_list(revision_requested, "No submissions in this category."),
            **{"x-show": "tab === 'revision'"},
        ),
        Div(
            _render_submission_list(completed, "No submissions in this category."),
            **{"x-show": "tab === 'completed'"},
        ),
    ]

    # KU Progress tab (always shown — data may be unavailable)
    tab_buttons.append(_tab_button("ku", "KU Progress"))
    tab_panels.append(Div(_render_ku_progress(ku_detail), **{"x-show": "tab === 'ku'"}))

    return Div(
        Div(*tab_buttons, cls="flex border-b border-border mb-6"),
        *tab_panels,
        **{"x-data": f"{{ tab: '{default_tab}' }}", "x-cloak": True},
    )


def student_detail_sidebar_items(
    pending_count: int,
    revision_count: int,
    completed_count: int,
) -> list[SidebarItem]:
    """Build sidebar items for student detail sections."""
    return [
        SidebarItem(
            "Needs Review",
            href="",
            slug="pending",
            icon="📥",
            badge_text=str(pending_count) if pending_count else "",
        ),
        SidebarItem(
            "Revision Requested",
            href="",
            slug="revision",
            icon="✏️",
            badge_text=str(revision_count) if revision_count else "",
        ),
        SidebarItem(
            "Completed",
            href="",
            slug="completed",
            icon="✅",
            badge_text=str(completed_count) if completed_count else "",
        ),
        SidebarItem("KU Progress", href="", slug="ku", icon="📊"),
    ]


def render_student_detail_sections(
    pending: list[SubmissionRow],
    revision_requested: list[SubmissionRow],
    completed: list[SubmissionRow],
    student_name: str,
    ku_detail: dict[str, Any] | None = None,
) -> Div:
    """Section panels for student detail, controlled by Alpine `section` variable.

    The parent element must provide x-data with a `section` property.
    Each panel uses x-show="section === '...'" for instant switching.
    """

    return Div(
        Div(
            _render_submission_list(pending, "No submissions awaiting review."),
            **{"x-show": "section === 'pending'"},
        ),
        Div(
            _render_submission_list(revision_requested, "No submissions in this category."),
            **{"x-show": "section === 'revision'"},
        ),
        Div(
            _render_submission_list(completed, "No submissions in this category."),
            **{"x-show": "section === 'completed'"},
        ),
        Div(_render_ku_progress(ku_detail), **{"x-show": "section === 'ku'"}),
    )


def render_class_member_row(item: ClassMember) -> Div:
    """Render a member row in the class detail view."""
    pending_variant = BadgeT.warning if item.pending_count > 0 else BadgeT.ghost

    return CardGenerator.from_dataclass(
        {"title": item.user_name},
        display_fields=[],
        subtitle=P(f"{item.role} · {item.user_uid}", cls="text-xs text-foreground/40 mb-0"),
        header_badges=[
            Badge(f"{item.pending_count} pending", variant=pending_variant),
            Badge(f"{item.reviewed_count}/{item.submission_count} reviewed", variant=BadgeT.ghost),
        ],
        show_labels=False,
        actions=ButtonLink(
            "View Submissions",
            href=f"/teaching/students/{item.user_uid}",
            cls=ButtonT.ghost,
            size="sm",
        ),
        card_attrs={"cls": "bg-background shadow-xs mb-2"},
    )
