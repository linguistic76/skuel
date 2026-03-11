"""
Form Submissions UI - User-Facing Pages
=========================================

UI routes for viewing and managing user's form submissions.

Routes:
- GET /my-forms - List of user's form submissions
- GET /my-forms/detail?uid= - Form submission detail page
"""

from typing import Any

from fasthtml.common import H2, A, Div, P, Request, Span

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

logger = get_logger(__name__)


def create_form_submissions_ui_routes(
    app: Any,
    rt: Any,
    form_submission_service: Any,
    user_service: Any = None,
) -> list[Any]:
    """Create form submission UI routes."""

    @rt("/my-forms")
    async def my_forms_page(request: Request) -> Any:
        """List user's form submissions."""
        user_uid = require_authenticated_user(request)

        result = await form_submission_service.get_my_submissions(user_uid)
        submissions = result.value if result.is_ok else []

        if not submissions:
            content = Div(
                P("You haven't submitted any forms yet.", cls="text-base-content/60"),
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
                                    cls="text-xs text-base-content/50 ml-2",
                                ),
                                cls="flex items-center",
                            ),
                            Span(
                                str(created)[:10] if created else "",
                                cls="text-xs text-base-content/50",
                            ),
                            cls="flex justify-between items-center py-3 px-4 hover:bg-base-200 rounded-lg",
                        ),
                        href=f"/my-forms/detail?uid={uid}",
                    )
                )
            content = Div(*rows, cls="space-y-1")

        return BasePage(
            Div(
                H2("My Form Submissions", cls="text-2xl font-bold mb-6"),
                content,
            ),
            title="My Form Submissions",
            page_type=PageType.STANDARD,
            request=request,
        )

    @rt("/my-forms/detail")
    async def form_submission_detail(request: Request) -> Any:
        """Form submission detail page."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid")

        if not uid:
            return BasePage(
                P("No submission UID provided.", cls="text-error"),
                title="Form Submission",
                page_type=PageType.STANDARD,
                request=request,
            )

        result = await form_submission_service.get_submission(uid, user_uid)
        if result.is_error:
            return BasePage(
                P("Form submission not found.", cls="text-error"),
                title="Form Submission",
                page_type=PageType.STANDARD,
                request=request,
            )

        submission = result.value
        form_data = submission.form_data or {}

        # Render form data as key-value pairs
        data_rows = []
        for key, value in form_data.items():
            data_rows.append(
                Div(
                    Span(key.replace("_", " ").title(), cls="font-medium text-sm w-40"),
                    Span(str(value), cls="text-sm"),
                    cls="flex gap-4 py-2 border-b border-base-200",
                )
            )

        # Delete button
        delete_btn = A(
            "Delete Submission",
            hx_delete=f"/api/form-submissions/delete?uid={uid}",
            hx_confirm="Are you sure you want to delete this submission?",
            hx_swap="none",
            cls="btn btn-error btn-sm mt-6",
        )

        return BasePage(
            Div(
                H2(submission.title or "Form Submission", cls="text-2xl font-bold mb-2"),
                P(
                    f"Submitted: {str(submission.created_at)[:19]}",
                    cls="text-sm text-base-content/60 mb-6",
                ),
                Div(*data_rows) if data_rows else P("No form data.", cls="text-base-content/60"),
                delete_btn,
                A("Back to My Forms", href="/my-forms", cls="btn btn-ghost btn-sm mt-4 ml-2"),
            ),
            title=submission.title or "Form Submission",
            page_type=PageType.STANDARD,
            request=request,
        )

    return []
