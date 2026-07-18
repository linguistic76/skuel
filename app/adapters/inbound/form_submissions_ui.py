"""
Form Submissions UI - User-Facing Pages
=========================================

UI routes for viewing and managing user's form submissions.

Routes:
- GET /my-forms - List of user's form submissions
- GET /my-forms/content - Fragment: submission list
- GET /my-forms/detail?uid= - Form submission detail page
- GET /my-forms/detail/content?uid= - Fragment: submission detail
"""

from typing import Any

from fasthtml.common import A, Div, P, Request, Span

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.components import Button, ButtonT
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink

logger = get_logger(__name__)


def create_form_submissions_ui_routes(
    app: Any,
    rt: Any,
    form_submission_service: Any,
    user_service: Any = None,
) -> list[Any]:
    """Create form submission UI routes."""

    @rt("/my-forms")
    def my_forms_page(request: Request) -> Any:
        """Shell: returns immediately; content fills via HTMX."""
        require_authenticated_user(request)
        return BasePage(
            Div(
                PageHeader("My Form Submissions"),
                content_loading_placeholder("/my-forms/content", "my-forms-content"),
            ),
            title="My Form Submissions",
            page_type=PageType.STANDARD,
            request=request,
        )

    @rt("/my-forms/content")
    async def my_forms_content(request: Request) -> Any:
        """Fragment: fetches and renders the submission list."""
        user_uid = require_authenticated_user(request)

        result = await form_submission_service.get_my_submissions(user_uid)
        submissions = result.value if result.is_ok else []

        if not submissions:
            inner = Div(
                P("You haven't submitted any forms yet.", cls="text-muted-foreground"),
                cls="text-center py-12",
            )
        else:
            rows = []
            for sub in submissions:
                title = sub.get("title", "Untitled")
                uid = sub.get("uid", "")
                created = sub.get("created_at", "")
                template_uid = sub.get("form_template_uid", "")

                rows.append(
                    A(
                        Div(
                            Div(
                                Span(title, cls="font-medium"),
                                Span(
                                    f"Template: {template_uid}" if template_uid else "",
                                    cls="text-xs text-muted-foreground ml-2",
                                ),
                                cls="flex items-center",
                            ),
                            Span(
                                str(created)[:10] if created else "",
                                cls="text-xs text-muted-foreground",
                            ),
                            cls="flex justify-between items-center py-3 px-4 hover:bg-muted rounded-lg",
                        ),
                        href=f"/my-forms/detail?uid={uid}",
                    )
                )
            inner = Div(*rows, cls="space-y-1")

        return Div(inner, id="my-forms-content")

    @rt("/my-forms/detail")
    def form_submission_detail(request: Request) -> Any:
        """Shell: validates UID, returns immediately; content fills via HTMX."""
        require_authenticated_user(request)
        uid = request.query_params.get("uid")

        if not uid:
            return BasePage(
                render_error_banner("No submission UID provided"),
                title="Form Submission",
                page_type=PageType.STANDARD,
                request=request,
            )

        return BasePage(
            content_loading_placeholder(
                f"/my-forms/detail/content?uid={uid}", "my-forms-detail-content"
            ),
            title="Form Submission",
            page_type=PageType.STANDARD,
            request=request,
        )

    @rt("/my-forms/detail/content")
    async def form_submission_detail_content(request: Request) -> Any:
        """Fragment: fetches and renders the submission detail."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")

        result = await form_submission_service.get_submission(uid, user_uid)
        if result.is_error:
            return Div(
                render_error_banner("Form submission not found"),
                id="my-forms-detail-content",
            )

        submission = result.value
        form_data = submission.form_data or {}

        data_rows = []
        for key, value in form_data.items():
            data_rows.append(
                Div(
                    Span(key.replace("_", " ").title(), cls="font-medium text-sm w-40"),
                    Span(str(value), cls="text-sm"),
                    cls="flex gap-4 py-2 border-b border-border",
                )
            )

        delete_btn = Button(
            "Delete Submission",
            hx_delete=f"/api/form-submissions/delete?uid={uid}",
            hx_confirm="Are you sure you want to delete this submission?",
            hx_swap="none",
            cls=(ButtonT.destructive, "mt-6"),
            size="sm",
        )

        return Div(
            PageHeader(
                submission.title or "Form Submission",
                subtitle=f"Submitted: {str(submission.created_at)[:19]}",
            ),
            Div(*data_rows) if data_rows else EmptyState(title="No form data"),
            delete_btn,
            ButtonLink(
                "Back to My Forms",
                href="/my-forms",
                cls=(ButtonT.ghost, "mt-4 ml-2"),
                size="sm",
            ),
            id="my-forms-detail-content",
        )

    return []
