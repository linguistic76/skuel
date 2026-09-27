"""
Teaching UI Detail Components
=============================

Submission content display and row components for detail views.
"""

from typing import Any

from fasthtml.common import H3, H4, Div, P, Span

from core.models.report.entry_report import EntryReport
from ui.activities._shared import safe_id
from ui.components import Button, ButtonT, Card, CardBody
from ui.feedback import Badge, BadgeT, StatusBadge
from ui.layout import Size
from ui.learning_loop.entry_body import EntryBody
from ui.learning_loop.turn_in_label import turn_in_label
from ui.patterns.card_generator import CardGenerator
from ui.patterns.sidebar import SidebarItem
from ui.patterns.skeleton import SkeletonLines
from ui.primitives import ButtonLink
from ui.teaching.badges import entity_type_badge
from ui.teaching.forms import render_review_actions
from ui.teaching.types import (
    ClassMember,
    SubmissionDetail,
    SubmissionRow,
)


def render_submission_content(detail: SubmissionDetail) -> Div:
    """The submission card a teacher reviews: the student's work, in their words.

    Shows the entry's ``content`` — what the student wrote or uploaded as text
    — with the exercise instructions above it for reference. A file with no
    text says so by its filename; the server path is never shown.
    """
    student_name = detail.student_name or detail.student_uid or "Unknown"

    meta_parts = [f"by {student_name}"]
    label = turn_in_label(detail.exercise_title, detail.revision)
    if label:
        meta_parts.append(f"Exercise: {label}")

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

    if detail.original_filename:
        empty = f"Uploaded file: {detail.original_filename} — no text to show."
    else:
        empty = "No text submitted."
    work = detail.content if detail.content and detail.content.strip() else None

    return Card(
        CardBody(
            Div(
                Div(
                    H4(detail.title or "Untitled", cls="font-semibold mb-1 wrap-break-word"),
                    P(" · ".join(meta_parts), cls="text-sm text-muted-foreground mb-0"),
                    cls="flex-1 min-w-0",
                ),
                Div(
                    entity_type_badge(detail.entity_type),
                    StatusBadge(detail.status),
                    cls="flex flex-wrap gap-2 items-center shrink-0",
                ),
                cls="flex flex-col gap-2 mb-4 sm:flex-row sm:items-start sm:justify-between sm:gap-4",
            ),
            exercise_section,
            Div(
                Span(
                    "Student's work",
                    cls="text-xs font-semibold text-muted-foreground uppercase tracking-wide",
                ),
                Div(EntryBody(work, empty=empty), cls="mt-1"),
            ),
            cls="p-4",
        ),
        cls="bg-background shadow-xs mb-4",
    )


def render_report_item(report: EntryReport) -> Div:
    """Render a single typed EntryReport. Delegates to shared component."""
    from ui.patterns.report_item import render_report_item as _shared_render

    return _shared_render(report)


def render_review_body(uid: str, detail: SubmissionDetail, history: list[EntryReport]) -> Div:
    """What a teacher reviews and does — the review page and the per-student panel.

    The student's work, the feedback already written on it, and the actions
    its status and supersession allow (``render_review_actions``, the one
    action rule).
    """
    history_section: Any = ""
    if history:
        history_section = Div(
            H3("Feedback History", cls="text-base font-semibold mb-2"),
            Div(*[render_report_item(fb) for fb in history]),
            cls="mb-4",
        )
    return Div(
        render_submission_content(detail),
        history_section,
        render_review_actions(uid, detail.status, bool(detail.exercise_uid), detail.superseded),
    )


def render_review_panel_inline(
    uid: str, detail: SubmissionDetail | None, history: list[EntryReport]
) -> Div:
    """Inline review panel — loaded by HTMX into a submission row's drawer.

    The same review body as the review page; a denied or missing submission is
    one "unavailable" line. Returned by GET /api/teaching/review/{uid}/panel.
    """
    body: Any = (
        render_review_body(uid, detail, history)
        if detail is not None
        else P(
            "Submission content unavailable.",
            cls="text-sm text-muted-foreground italic mb-4",
        )
    )
    return Div(body, cls="mt-3 border-t border-border pt-3")


def render_student_submission_inline_row(item: SubmissionRow) -> Div:
    """
    Submission row with clickable accordion header and HTMX-loaded review panel.

    Clicking the header lazy-loads the panel via HTMX on first click,
    then toggles visibility on subsequent clicks. No "Review" button —
    the student detail page is already the review context.
    """
    title = item.title or item.original_filename or "Untitled"
    dom_id = safe_id(item.uid)

    badges: list[Any] = []
    if item.feedback_count > 0:
        badges.append(Badge(f"{item.feedback_count} feedback", variant=BadgeT.info, size=Size.sm))
    badges.append(StatusBadge(item.status))

    exercise_label: Any = ""
    label = turn_in_label(item.exercise_title, item.revision)
    if label:
        exercise_label = Span(
            f" · {label}",
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
            icon="inbox",
            badge_text=str(pending_count) if pending_count else "",
        ),
        SidebarItem(
            "Revision Requested",
            href="",
            slug="revision",
            icon="pen-line",
            badge_text=str(revision_count) if revision_count else "",
        ),
        SidebarItem(
            "Completed",
            href="",
            slug="completed",
            icon="check-circle",
            badge_text=str(completed_count) if completed_count else "",
        ),
        SidebarItem("KU Progress", href="", slug="ku", icon="bar-chart-2"),
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
