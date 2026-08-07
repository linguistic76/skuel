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
from typing import TYPE_CHECKING, Any, Protocol

from fasthtml.common import A, Div, Small, Span, to_xml
from starlette.responses import HTMLResponse, Response

from adapters.inbound.auth import make_service_getter, require_authenticated_user
from adapters.inbound.auth.roles import UserRole, require_role
from adapters.inbound.fasthtml_types import Request
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorCategory
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
    from core.models.forms.form_template import FormTemplate
    from core.models.user.user import User
    from core.ports.form_protocols import FormSubmissionOperations, FormTemplateOperations

logger = get_logger(__name__)


class ScopeSubject(Protocol):
    """The slice of the authenticated user that decides a read's classroom scope.

    Structural rather than the concrete `User` so the contract is exactly the two
    members the decision reads, and so the handlers' FastHTML-boundary `Any` stops
    at this function instead of travelling into the decision itself. `Any` here
    would let `has_permission` being renamed or returning a truthy non-bool widen
    every scoped read to the ADMIN-wide one, silently.
    """

    @property
    def uid(self) -> str: ...

    def has_permission(self, required_role: UserRole) -> bool: ...


if TYPE_CHECKING:

    def _user_satisfies_scope_subject(injected: "User") -> ScopeSubject:
        """Static proof that what `@require_role` injects satisfies the protocol.

        Without this the protocol is decorative: nothing else in the tree checks
        the real `User` against it, so renaming `User.uid` would leave the
        contract type-checking against a shape no caller ever passes.
        """
        return injected


def _classroom_scope(current_user: ScopeSubject) -> UserUID | None:
    """The teacher UID that bounds a read, or None for the ADMIN-wide view.

    ADMIN keeps the cross-classroom view these pages are documented to provide;
    every other caller sees only their own classrooms. This is the same exemption
    the submission detail gate applies, kept in one place because the two must
    agree — a row this scope admits to the list has to open on the detail page,
    and a row it withholds must not be reachable by guessing its UID.
    """
    if current_user.has_permission(UserRole.ADMIN):
        return None
    return UserUID(current_user.uid)


def create_teaching_forms_ui_routes(
    _app: Any,
    rt: Any,
    form_template_service: "FormTemplateOperations",
    form_submission_service: "FormSubmissionOperations",
    user_service: Any,
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

        # Gather submission counts. Scoped to the caller's classrooms so the
        # badge counts what they can actually open — an unscoped total both
        # discloses other classrooms' activity and contradicts the list page it
        # links to.
        scope = _classroom_scope(current_user)
        rows: list[tuple[FormTemplate, int | None]] = []
        for template in templates:
            count_result = await form_template_service.count_submissions(template.uid, scope)
            if count_result.is_error:
                # None, not 0. The count query propagates backend failures on
                # purpose, and rendering "0 submissions" here would spend that
                # signal to tell a teacher their classroom is empty when the
                # database is simply down.
                logger.error(
                    "Submission count failed for template %s: %s",
                    template.uid,
                    count_result.expect_error().message,
                )
                rows.append((template, None))
            else:
                rows.append((template, count_result.value))

        template_cards = []
        for template, count in rows:
            count_variant = BadgeT.info if count else BadgeT.ghost
            count_label = (
                "count unavailable"
                if count is None
                else f"{count} submission{'s' if count != 1 else ''}"
            )
            field_count = len(template.form_schema) if template.form_schema else 0

            template_cards.append(
                CardGenerator.from_dataclass(
                    {"title": template.title},
                    display_fields=[],
                    subtitle=template.instructions[:100] if template.instructions else None,
                    header_badges=[
                        Badge(
                            count_label,
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
                    card_attrs={"cls": "bg-background shadow-xs mb-2"},
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

        # Fetch template. AGENTS.md's `require_found` convention covers a fetch
        # that may return None; `FormTemplateOperations.get` returns a
        # non-optional `Result[FormTemplate]` because the CRUD mixin already
        # converts a missing entity into NOT_FOUND, so there is no None to
        # guard and `Result`'s invariance rejects the call outright. The
        # normalization the helper provides has therefore already happened.
        template_result = await form_template_service.get(uid)
        if template_result.is_error:
            content = Div(
                PageHeader("Form Submissions"),
                render_error_banner("Template not found", f"No template with UID: {uid}"),
            )
            return render_teaching_sidebar_page(content, active="forms", request=request)

        template = template_result.value

        # Fetch submissions, bounded to the caller's classrooms. Every row here
        # carries the submitter's name and a preview of their answers, so the
        # TEACHER role alone is not enough — without this scope any teacher reads
        # every student's answers for any template, and the per-row authority
        # check on the detail page is bypassed by simply reading the list.
        subs_result = await form_submission_service.get_submissions_for_template(
            uid, _classroom_scope(current_user)
        )
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
                    card_attrs={"cls": "bg-background shadow-xs mb-2"},
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

        def render_not_found() -> Response:
            """The one not-found response — a submission outside the caller's
            classroom is indistinguishable from one that does not exist.

            Carries a real 404: a denied read must not reach clients or
            intermediaries as a success (docs/patterns/OWNERSHIP_VERIFICATION.md).
            """
            content = Div(
                PageHeader("Submission Detail"),
                render_error_banner("Submission not found", f"No submission with UID: {uid}"),
            )
            return HTMLResponse(
                to_xml(render_teaching_sidebar_page(content, active="forms", request=request)),
                status_code=404,
            )

        def render_unavailable(detail: str) -> Response:
            """A backend failure is not an access decision — keep it a 503 so
            the fault stays visible instead of reading as 'no such submission'."""
            content = Div(
                PageHeader("Submission Detail"),
                render_error_banner("Could not load submission", detail),
            )
            return HTMLResponse(
                to_xml(render_teaching_sidebar_page(content, active="forms", request=request)),
                status_code=503,
            )

        result = await form_submission_service.get_submission_admin(uid)
        if result.is_error:
            # Same rule as the authority check below: only a genuine NOT_FOUND
            # is a 404. get_submission_admin propagates backend errors with
            # their own category, so collapsing them here would report an
            # outage as a missing submission.
            fetch_error = result.expect_error()
            if fetch_error.category is not ErrorCategory.NOT_FOUND:
                logger.error("Failed to load submission %s: %s", uid, fetch_error.message)
                return render_unavailable("Could not load the submission. Please try again.")
            return render_not_found()

        submission = result.value

        # Authority is carried by *this submission's* share edges, not by the
        # caller's relationship to its author (the Model B gate — see
        # FormSubmissionService.verify_teacher_access). A student may study in
        # several groups, so sharing a classroom with the author does not make
        # a submission shared with another teacher's group readable here.
        # Admins keep the cross-classroom view this page is documented to give.
        if not current_user.has_permission(UserRole.ADMIN):
            authority = await form_submission_service.verify_teacher_access(uid, current_user.uid)
            if authority.is_error:
                error = authority.expect_error()
                # Only a real refusal becomes not-found. An infrastructure
                # failure reaching here would otherwise hand a legitimate
                # teacher a confident "no such submission".
                if error.category is not ErrorCategory.FORBIDDEN:
                    logger.error(
                        "Authority check failed for teacher %s on submission %s: %s",
                        current_user.uid,
                        uid,
                        error.message,
                    )
                    return render_unavailable("Could not verify access. Please try again.")
                logger.warning(
                    "Teacher %s denied access to submission %s: not shared with a group they own",
                    current_user.uid,
                    uid,
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
