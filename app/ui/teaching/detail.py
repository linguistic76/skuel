"""
Teaching UI Detail Components
=============================

Submission content display and row components for detail views.
"""

from typing import Any

from fasthtml.common import H3, H4, Div, Form, Input, Label, P, Span

from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.forms import Textarea
from ui.layout import Size
from ui.patterns.card_generator import CardGenerator
from ui.teaching.badges import entity_type_badge, status_badge
from ui.teaching.types import ClassMember, SubmissionDetail, SubmissionRow

# Statuses that require teacher action
_NEEDS_REVIEW_STATUSES = {"submitted", "active", "queued", "processing"}
_REVISION_STATUSES = {"revision_requested"}
_COMPLETED_STATUSES = {"completed", "failed"}


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
                cls="p-3 bg-muted/50 rounded",
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
                    status_badge(detail.status),
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
                    cls="mt-1 p-3 bg-muted/50 rounded border border-border select-all",
                ),
                cls="p-4 bg-muted/20 border-t",
            ),
            cls="p-4",
        ),
        cls="bg-background shadow-sm mb-4",
    )


def render_report_item(fb: dict[str, Any]) -> Div:
    """Render a single report history item. Delegates to shared component."""
    from ui.patterns.report_item import render_report_item as _shared_render

    return _shared_render(fb)


def render_exercise_submission_row(item: SubmissionRow) -> Div:
    """Render a submission row in the exercise-detail view."""
    title = item.title or item.original_filename or "Untitled"
    student_name = item.student_name or item.student_uid or "Unknown"

    feedback_badge: Any = None
    if item.feedback_count > 0:
        feedback_badge = Badge(
            f"{item.feedback_count} feedback",
            variant=BadgeT.info,
            size=Size.sm,
        )

    return CardGenerator.from_dataclass(
        {"title": title},
        display_fields=[],
        subtitle=f"by {student_name}",
        header_badges=[feedback_badge, status_badge(item.status)],
        show_labels=False,
        actions=ButtonLink(
            "Review",
            href=f"/teaching/review/{item.uid}",
            variant=ButtonT.primary,
            size=Size.sm,
        ),
        card_attrs={"cls": "bg-background shadow-sm mb-2"},
    )


def render_student_submission_row(item: SubmissionRow) -> Div:
    """Render a submission row in the student-detail view with feedback toggle."""
    title = item.title or item.original_filename or "Untitled"
    dom_id = item.uid.replace(":", "-").replace(".", "-")

    exercise_subtitle: Any = None
    if item.exercise_title:
        exercise_subtitle = Span(
            f"Exercise: {item.exercise_title}", cls="text-xs text-muted-foreground"
        )

    feedback_badge: Any = None
    if item.feedback_count > 0:
        feedback_badge = Badge(
            f"{item.feedback_count} feedback",
            variant=BadgeT.info,
            size=Size.sm,
        )

    feedback_toggle: Any = None
    if item.feedback_count > 0:
        feedback_toggle = Div(
            Button(
                "View Feedback",
                variant=ButtonT.ghost,
                size=Size.xs,
                type="button",
                hx_get=f"/api/submissions/{item.uid}/reports",
                hx_target=f"#feedback-{dom_id}",
                hx_swap="innerHTML",
            ),
            Div(id=f"feedback-{dom_id}"),
            cls="mt-2",
        )

    return CardGenerator.from_dataclass(
        {"title": title},
        display_fields=[],
        subtitle=exercise_subtitle,
        header_badges=[feedback_badge, status_badge(item.status)],
        show_labels=False,
        actions=ButtonLink(
            "Review",
            href=f"/teaching/review/{item.uid}",
            variant=ButtonT.primary,
            size=Size.sm,
        ),
        extra=feedback_toggle,
        card_attrs={"cls": "bg-background shadow-sm mb-2"},
    )


def render_review_panel_inline(
    uid: str, detail: dict[str, Any], history: list[dict[str, Any]]
) -> Div:
    """
    Inline review panel fragment — loaded by HTMX into a submission card drawer.

    Renders: submission content, feedback history, and action forms (if actionable).
    Returned by GET /api/teaching/review/{uid}/panel.
    """
    dom_id = uid.replace(":", "-").replace(".", "-")
    status = (detail.get("status") or "").lower()
    is_actionable = status in _NEEDS_REVIEW_STATUSES

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
                                cls="block w-full text-sm file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-primary file:text-primary-foreground hover:file:bg-primary/90 cursor-pointer",
                            ),
                            cls="mb-4",
                        ),
                        Button("Submit Feedback", variant=ButtonT.primary, type="submit"),
                        enctype="multipart/form-data",
                        **{
                            "hx-post": f"/api/teaching/review/{uid}/report",
                            "hx-target": f"#inline-result-{dom_id}",
                            "hx-swap": "innerHTML",
                            "hx-encoding": "multipart/form-data",
                        },
                    ),
                    cls="p-4",
                ),
                cls="bg-background shadow-sm mb-2",
            ),
            # Request revision + approve
            Card(
                CardBody(
                    P(
                        "Request the student revise their work, or approve as-is.",
                        cls="text-sm text-muted-foreground mb-3",
                    ),
                    Form(
                        Div(
                            Label(
                                "Revision notes",
                                fr=f"revision_notes_{dom_id}",
                                cls="text-sm font-medium mb-1 block",
                            ),
                            Textarea(
                                name="notes",
                                id=f"revision_notes_{dom_id}",
                                placeholder="Describe what needs to be revised...",
                                cls="h-20",
                                required=True,
                            ),
                            cls="mb-3",
                        ),
                        Div(
                            Button(
                                "Request Revision",
                                variant=ButtonT.warning,
                                type="submit",
                            ),
                            Button(
                                "Approve",
                                variant=ButtonT.success,
                                type="button",
                                **{
                                    "hx-post": f"/api/teaching/review/{uid}/approve",
                                    "hx-target": f"#inline-result-{dom_id}",
                                    "hx-swap": "innerHTML",
                                    "hx-confirm": "Approve this submission?",
                                },
                            ),
                            cls="flex gap-3",
                        ),
                        **{
                            "hx-post": f"/api/teaching/review/{uid}/revision",
                            "hx-target": f"#inline-result-{dom_id}",
                            "hx-swap": "innerHTML",
                        },
                    ),
                    cls="p-4",
                ),
                cls="bg-background shadow-sm",
            ),
            Div(id=f"inline-result-{dom_id}", cls="mt-3"),
        )

    return Div(
        content_section,
        history_section,
        actions_section,
        ButtonLink(
            "Full review page →",
            href=f"/teaching/review/{uid}",
            variant=ButtonT.ghost,
            size=Size.sm,
            cls="mt-2",
        ),
        cls="mt-3 border-t border-border pt-3",
    )


def render_student_submission_inline_row(item: SubmissionRow) -> Div:
    """
    Submission row with inline HTMX-loadable review panel.

    Clicking "Review" lazy-loads the panel via HTMX into the panel div below
    the card. Pure HTMX — no Alpine required for the expand.
    """
    title = item.title or item.original_filename or "Untitled"
    status_str = (item.status or "").lower()
    is_actionable = status_str in _NEEDS_REVIEW_STATUSES

    feedback_badge: Any = None
    if item.feedback_count > 0:
        feedback_badge = Badge(f"{item.feedback_count} feedback", variant=BadgeT.info, size=Size.sm)

    dom_id = item.uid.replace(":", "-").replace(".", "-")

    exercise_subtitle: Any = None
    if item.exercise_title:
        exercise_subtitle = Span(
            f"Exercise: {item.exercise_title}", cls="text-xs text-muted-foreground"
        )

    review_btn_label = "Review" if is_actionable else "View"

    return Div(
        CardGenerator.from_dataclass(
            {"title": title},
            display_fields=[],
            subtitle=exercise_subtitle,
            header_badges=[feedback_badge, status_badge(item.status)],
            show_labels=False,
            actions=Button(
                review_btn_label,
                variant=ButtonT.primary if is_actionable else ButtonT.ghost,
                size=Size.sm,
                type="button",
                hx_get=f"/api/teaching/review/{item.uid}/panel",
                hx_target=f"#panel-{dom_id}",
                hx_swap="innerHTML",
            ),
            card_attrs={"cls": "bg-background shadow-sm mb-0"},
        ),
        Div(id=f"panel-{dom_id}"),
        cls="mb-3",
    )


def render_student_detail_tabs(
    pending: list[SubmissionRow],
    revision_requested: list[SubmissionRow],
    completed: list[SubmissionRow],
    student_name: str,
) -> Div:
    """
    Tabbed view of a student's submissions grouped by workflow status.

    Tabs: Needs Review | Revision Requested | Completed
    Pending submissions have inline HTMX review panels.
    Other submissions show read-only rows with feedback history toggle.
    """

    def _tab_button(tab_id: str, label: str, count: int) -> Any:
        count_badge = (
            Span(str(count), cls="ml-1.5 px-1.5 py-0.5 text-xs rounded-full bg-primary/10")
            if count
            else ""
        )
        return Div(
            Span(label),
            count_badge,
            cls="flex items-center gap-1 px-4 py-2 text-sm font-medium rounded-t border-b-2 cursor-pointer transition-colors",
            **{
                "@click": f"tab = '{tab_id}'",
                ":class": f"tab === '{tab_id}' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'",
            },
        )

    def _render_pending_list() -> Any:
        if not pending:
            return P(
                "No submissions awaiting review.",
                cls="text-center text-muted-foreground py-8 text-sm",
            )
        return Div(*[render_student_submission_inline_row(item) for item in pending])

    def _render_simple_list(items: list[SubmissionRow]) -> Any:
        if not items:
            return P(
                "No submissions in this category.",
                cls="text-center text-muted-foreground py-8 text-sm",
            )
        return Div(*[render_student_submission_row(item) for item in items])

    default_tab = "pending" if pending else ("revision" if revision_requested else "completed")

    return Div(
        # Tab bar
        Div(
            _tab_button("pending", "Needs Review", len(pending)),
            _tab_button("revision", "Revision Requested", len(revision_requested)),
            _tab_button("completed", "Completed", len(completed)),
            cls="flex border-b border-border mb-4",
        ),
        # Tab panels
        Div(_render_pending_list(), **{"x-show": "tab === 'pending'"}),
        Div(_render_simple_list(revision_requested), **{"x-show": "tab === 'revision'"}),
        Div(_render_simple_list(completed), **{"x-show": "tab === 'completed'"}),
        **{"x-data": f"{{ tab: '{default_tab}' }}", "x-cloak": True},
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
            variant=ButtonT.ghost,
            size=Size.sm,
        ),
        card_attrs={"cls": "bg-background shadow-sm mb-2"},
    )
