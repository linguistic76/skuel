"""
Teaching UI Routes — Teacher Review Queue
==========================================

Teacher-facing pages for reviewing student submissions.
Provides a review queue and detail view with feedback/revision/approve actions.

TEACHER role required for all endpoints.

Layout: Unified sidebar (Tailwind + Alpine) with teaching navigation.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
    H4,
    A,
    Div,
    Form,
    P,
    Span,
    Textarea,
)
from starlette.requests import Request

from core.auth import require_authenticated_user
from core.auth.roles import UserRole, require_role
from core.ui.daisy_components import Button, ButtonT
from core.utils.logging import get_logger
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from core.services.protocols import TeacherReviewOperations

logger = get_logger("skuel.routes.teaching.ui")


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

TEACHING_SIDEBAR_ITEMS = [
    SidebarItem("Review Queue", "/teaching", "queue", icon="📥"),
    SidebarItem("Approved", "/teaching/approved", "approved", icon="✅"),
]


# ============================================================================
# HELPERS
# ============================================================================


def _status_badge(status: str) -> Span:
    """Render a DaisyUI badge for Ku status."""
    badge_classes = {
        "submitted": "badge-warning",
        "active": "badge-info",
        "completed": "badge-success",
        "revision_requested": "badge-error",
        "draft": "badge-ghost",
    }
    cls = badge_classes.get(status, "badge-ghost")
    label = status.replace("_", " ").title()
    return Span(label, cls=f"badge {cls}")


def _ku_type_badge(ku_type: str | None) -> Span:
    """Render a DaisyUI badge for Ku type."""
    if not ku_type:
        return Span()
    label = ku_type.replace("_", " ").title()
    return Span(label, cls="badge badge-outline badge-sm")


def _render_queue_item(item: dict[str, Any]) -> Div:
    """Render a single review queue item as a card."""
    title = item.get("title") or "Untitled"
    student_name = item.get("student_name") or item.get("student_uid") or "Unknown"
    status = item.get("status") or "unknown"
    ku_type = item.get("ku_type")
    project_name = item.get("project_name")
    ku_uid = item.get("ku_uid", "")

    subtitle_parts = [f"by {student_name}"]
    if project_name:
        subtitle_parts.append(f"for {project_name}")

    return Div(
        Div(
            Div(
                Div(
                    H4(title, cls="mb-0 font-semibold"),
                    P(" · ".join(subtitle_parts), cls="text-sm text-base-content/60 mb-0"),
                    cls="flex-1",
                ),
                Div(
                    _ku_type_badge(ku_type),
                    _status_badge(status),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                A(
                    "Review",
                    href=f"/teaching/review/{ku_uid}",
                    cls="btn btn-sm btn-primary",
                    **{"hx-boost": "false"},
                ),
                cls="flex justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def _render_queue_empty() -> Div:
    """Render empty state for review queue."""
    return Div(
        Div(
            H3("No submissions to review", cls="text-lg font-medium mb-2"),
            P(
                "When students submit work against your assignments, it will appear here.",
                cls="text-base-content/60",
            ),
            cls="text-center py-12",
        ),
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_teaching_ui_routes(
    _app: Any,
    rt: Any,
    teacher_review_service: "TeacherReviewOperations",
    user_service: Any,
) -> list[Any]:
    """
    Create teaching UI routes for teacher review workflow.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        teacher_review_service: TeacherReviewService instance
        user_service: UserService for role checks
    """

    def get_user_service() -> Any:
        return user_service

    @rt("/teaching")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_queue_page(request: Request, current_user: Any = None) -> Any:
        """Review queue — pending student submissions."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_review_queue(teacher_uid=user_uid)

        if result.is_error:
            queue_content: Any = Div(
                P("Failed to load review queue", cls="text-center text-error"),
            )
        elif not result.value:
            queue_content = _render_queue_empty()
        else:
            queue_content = Div(*[_render_queue_item(item) for item in result.value])

        content = Div(
            PageHeader("Review Queue", subtitle="Student submissions awaiting your review"),
            queue_content,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="queue",
            title="Teaching",
            subtitle="Review student work",
            storage_key="teaching-sidebar",
            page_title="Review Queue",
            request=request,
            active_page="teaching",
            title_href="/teaching",
        )

    @rt("/teaching/approved")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_approved_page(request: Request, current_user: Any = None) -> Any:
        """Approved submissions — completed reviews."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_review_queue(
            teacher_uid=user_uid, status_filter="completed"
        )

        if result.is_error:
            list_content: Any = Div(
                P("Failed to load approved submissions", cls="text-center text-error"),
            )
        elif not result.value:
            list_content = Div(
                P("No approved submissions yet.", cls="text-center text-base-content/60 py-8"),
            )
        else:
            list_content = Div(*[_render_queue_item(item) for item in result.value])

        content = Div(
            PageHeader("Approved", subtitle="Submissions you have reviewed and approved"),
            list_content,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="approved",
            title="Teaching",
            subtitle="Review student work",
            storage_key="teaching-sidebar",
            page_title="Approved Submissions",
            request=request,
            active_page="teaching",
            title_href="/teaching",
        )

    @rt("/teaching/review/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_review_detail(request: Request, uid: str, current_user: Any = None) -> Any:
        """Review detail page — feedback form + action buttons."""
        content = Div(
            PageHeader("Review Submission"),
            # Feedback form
            Div(
                Div(
                    Form(
                        Div(
                            Textarea(
                                name="feedback",
                                placeholder="Write your feedback here...",
                                cls="textarea textarea-bordered w-full h-32",
                                required=True,
                            ),
                            cls="mb-4",
                        ),
                        Div(
                            Button(
                                "Submit Feedback",
                                variant=ButtonT.primary,
                                type="submit",
                            ),
                            cls="mb-2",
                        ),
                        **{
                            "hx-post": f"/api/teaching/review/{uid}/feedback",
                            "hx-target": "#review-result",
                            "hx-swap": "innerHTML",
                        },
                        id="feedback-form",
                    ),
                    Div(
                        Div(
                            Button(
                                "Request Revision",
                                variant=ButtonT.warning,
                                type="button",
                                **{
                                    "hx-post": f"/api/teaching/review/{uid}/revision",
                                    "hx-target": "#review-result",
                                    "hx-swap": "innerHTML",
                                    "hx-include": "#feedback-form",
                                    "hx-vals": '{"notes": ""}',
                                },
                            ),
                            Button(
                                "Approve",
                                variant=ButtonT.success,
                                type="button",
                                **{
                                    "hx-post": f"/api/teaching/review/{uid}/approve",
                                    "hx-target": "#review-result",
                                    "hx-swap": "innerHTML",
                                    "hx-confirm": "Approve this submission?",
                                },
                            ),
                            cls="flex gap-3",
                        ),
                        cls="mt-4",
                    ),
                    Div(id="review-result", cls="mt-4"),
                    cls="card-body",
                ),
                cls="card bg-base-100 shadow-sm",
            ),
            Div(
                A(
                    "Back to Queue",
                    href="/teaching",
                    cls="btn btn-ghost btn-sm mt-4",
                    **{"hx-boost": "false"},
                ),
            ),
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="queue",
            title="Teaching",
            subtitle="Review student work",
            storage_key="teaching-sidebar",
            page_title="Review Submission",
            request=request,
            active_page="teaching",
            title_href="/teaching",
        )

    logger.info("Teaching UI routes registered")
    return []
