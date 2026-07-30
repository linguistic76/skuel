"""
Teaching Forms UI — Admin/Teacher View of Form Submissions
==========================================================

Three pages for viewing FormTemplate submissions:
- Template list with submission counts
- Submissions list for a specific template
- Single submission detail (read-only)

TEACHER role required for all endpoints.
"""

import json
from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, Small, Span

from adapters.inbound.auth import make_service_getter, require_authenticated_user
from adapters.inbound.auth.roles import UserRole, require_role
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.result_helpers import require_found
from core.utils.logging import get_logger
from ui.components import ButtonT
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink
from ui.teaching.forms import (
    form_data_preview,
    format_date,
    render_form_responses_section,
    render_submission_metadata,
)
from ui.teaching.nav import render_teaching_sidebar_page

if TYPE_CHECKING:
    from core.ports.report_protocols import TeacherReviewOperations

logger = get_logger(__name__)


def create_teaching_forms_ui_routes(
    _app: Any,
    rt: Any,
    form_template_service: Any,
    form_submission_service: Any,
    user_service: Any,
    teacher_review_service: "TeacherReviewOperations",
) -> list[Any]:
    """Create teaching forms UI routes.

    Returns list of route functions (FastHTML decorator registers immediately).
    """
    get_user_service = make_service_getter(user_service)

    # ==================================================================
    # GET /teaching/forms — Template list with submission counts
    # ==================================================================

    @rt("/teaching/forms")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_forms_list(request: Request, current_user: Any = None) -> Any:
        require_authenticated_user(request)

        result = await form_template_service.list(limit=200, order_by="created_at", order_desc=True)
        if result.is_error:
            content = Div(
                PageHeader("Forms"),
                render_error_banner("Failed to load form templates", str(result.error)),
            )
            return render_teaching_sidebar_page(content, active="forms", request=request)

        templates, _total = result.value
        if not templates:
            content = Div(
                PageHeader("Forms"),
                EmptyState("No form templates", "Create form templates to see them here."),
            )
            return render_teaching_sidebar_page(content, active="forms", request=request)

        # Gather submission counts
        rows = []
        for template in templates:
            count_result = await form_template_service.count_submissions(template.uid)
            count = count_result.value if not count_result.is_error else 0
            rows.append((template, count))

        template_cards = []
        for template, count in rows:
            count_variant = BadgeT.info if count > 0 else BadgeT.ghost
            field_count = len(template.form_schema) if template.form_schema else 0

            template_cards.append(
                CardGenerator.from_dataclass(
                    {"title": template.title},
                    display_fields=[],
                    subtitle=template.instructions[:100] if template.instructions else None,
                    header_badges=[
                        Badge(
                            f"{count} submission{'s' if count != 1 else ''}",
                            variant=count_variant,
                            size=Size.sm,
                        ),
                        Badge(
                            f"{field_count} field{'s' if field_count != 1 else ''}",
                            variant=BadgeT.ghost,
                            size=Size.sm,
                        ),
                    ],
                    show_labels=False,
                    actions=ButtonLink(
                        "View Submissions",
                        href=f"/teaching/forms/detail?uid={template.uid}",
                        cls=ButtonT.primary,
                        size="sm",
                    ),
                    card_attrs={"cls": "bg-background shadow-sm mb-2"},
                )
            )

        content = Div(PageHeader("Forms"), *template_cards)
        return render_teaching_sidebar_page(content, active="forms", request=request)

    # ==================================================================
    # GET /teaching/forms/detail?uid= — Submissions for a template
    # ==================================================================

    @rt("/teaching/forms/detail")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_forms_detail(
        request: Request, uid: str = "", current_user: Any = None
    ) -> Any:
        require_authenticated_user(request)

        if not uid:
            content = Div(
                PageHeader("Form Submissions"),
                render_error_banner("Missing template UID", "No uid query parameter provided."),
            )
            return render_teaching_sidebar_page(content, active="forms", request=request)

        # Fetch template
        template_result = require_found(await form_template_service.get(uid), "FormTemplate", uid)
        if template_result.is_error:
            content = Div(
                PageHeader("Form Submissions"),
                render_error_banner("Template not found", f"No template with UID: {uid}"),
            )
            return render_teaching_sidebar_page(content, active="forms", request=request)

        template = template_result.value

        # Fetch submissions
        subs_result = await form_submission_service.get_submissions_for_template(uid)
        if subs_result.is_error:
            content = Div(
                PageHeader(template.title, subtitle="Submissions"),
                render_error_banner("Failed to load submissions", str(subs_result.error)),
            )
            return render_teaching_sidebar_page(content, active="forms", request=request)

        submissions = subs_result.value or []

        back_link = A(
            "← Back to Forms",
            href="/teaching/forms",
            cls="text-sm text-muted-foreground hover:text-foreground mb-4 inline-block",
        )

        if not submissions:
            content = Div(
                back_link,
                PageHeader(template.title, subtitle="Submissions"),
                EmptyState(
                    "No submissions yet",
                    "Submissions will appear here when users respond to this form.",
                ),
            )
            return render_teaching_sidebar_page(content, active="forms", request=request)

        submission_rows = []
        for sub in submissions:
            user_name = sub.get("user_name") or sub.get("user_uid") or "Unknown"
            created_at = format_date(sub.get("created_at"))

            # Parse form_data for preview
            raw_form_data = sub.get("form_data")
            if isinstance(raw_form_data, str):
                try:
                    raw_form_data = json.loads(raw_form_data)
                except json.JSONDecodeError, TypeError:
                    raw_form_data = None

            preview = form_data_preview(raw_form_data)
            sub_uid = sub.get("uid", "")

            submission_rows.append(
                CardGenerator.from_dataclass(
                    {"title": sub.get("title", "Untitled")},
                    display_fields=[],
                    subtitle=Div(
                        Span(f"by {user_name}", cls="text-sm"),
                        Span(" · ", cls="text-muted-foreground"),
                        Span(created_at, cls="text-sm text-muted-foreground"),
                        cls="flex items-center gap-0",
                    ),
                    extra=Small(preview, cls="text-xs text-muted-foreground line-clamp-1"),
                    show_labels=False,
                    actions=ButtonLink(
                        "View",
                        href=f"/teaching/forms/submission?uid={sub_uid}",
                        cls=ButtonT.ghost,
                        size="sm",
                    ),
                    card_attrs={"cls": "bg-background shadow-sm mb-2"},
                )
            )

        content = Div(
            back_link,
            PageHeader(
                template.title,
                subtitle=f"{len(submissions)} submission{'s' if len(submissions) != 1 else ''}",
            ),
            *submission_rows,
        )
        return render_teaching_sidebar_page(content, active="forms", request=request)

    # ==================================================================
    # GET /teaching/forms/submission?uid= — Single submission detail
    # ==================================================================

    @rt("/teaching/forms/submission")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_forms_submission_detail(
        request: Request, uid: str = "", current_user: Any = None
    ) -> Any:
        if not uid:
            content = Div(
                PageHeader("Submission Detail"),
                render_error_banner("Missing submission UID", "No uid query parameter provided."),
            )
            return render_teaching_sidebar_page(content, active="forms", request=request)

        def render_not_found() -> Any:
            """The one not-found response — a submission outside the caller's
            classroom is indistinguishable from one that does not exist."""
            content = Div(
                PageHeader("Submission Detail"),
                render_error_banner("Submission not found", f"No submission with UID: {uid}"),
            )
            return render_teaching_sidebar_page(content, active="forms", request=request)

        result = await form_submission_service.get_submission_admin(uid)
        if result.is_error:
            return render_not_found()

        submission = result.value

        # The TEACHER role is not authority over a *particular* student: without
        # this gate any teacher can read any student's submission. Admins keep
        # the cross-classroom view this page is documented to provide.
        if not current_user.has_permission(UserRole.ADMIN):
            authority = await teacher_review_service.verify_teacher_authority(
                current_user.uid, submission.user_uid
            )
            if authority.is_error:
                logger.warning(
                    "Teacher %s denied access to submission %s (student %s): no shared classroom",
                    current_user.uid,
                    uid,
                    submission.user_uid,
                )
                return render_not_found()

        # Try to fetch the template for field labels
        template = None
        if submission.form_template_uid:
            template_result = await form_template_service.get(submission.form_template_uid)
            if not template_result.is_error and template_result.value:
                template = template_result.value

        # Build back link
        back_href = (
            f"/teaching/forms/detail?uid={submission.form_template_uid}"
            if submission.form_template_uid
            else "/teaching/forms"
        )
        back_link = A(
            "← Back to Submissions",
            href=back_href,
            cls="text-sm text-muted-foreground hover:text-foreground mb-4 inline-block",
        )

        form_schema = template.form_schema if template else None
        content = Div(
            back_link,
            PageHeader(submission.title or "Form Submission"),
            render_submission_metadata(submission, template),
            render_form_responses_section(submission.form_data, form_schema),
        )
        return render_teaching_sidebar_page(content, active="forms", request=request)

    return [teaching_forms_list, teaching_forms_detail, teaching_forms_submission_detail]
