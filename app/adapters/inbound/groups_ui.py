"""
Groups UI Routes
=================

UI pages for group management.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import Any

from fasthtml.common import H1, H2, Div, Li, P, Request, Ul

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger

logger = get_logger(__name__)


def create_groups_ui_routes(
    app: Any,
    rt: Any,
    group_service: Any,
) -> list[Any]:
    """
    Create group UI routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        group_service: GroupService instance
    """

    @rt("/groups")
    async def groups_page(request: Request) -> Any:
        """Groups management page."""
        user_uid = require_authenticated_user(request)

        # Get groups where user is owner
        teacher_groups = await group_service.list_teacher_groups(user_uid)
        # Get groups where user is member
        member_groups = await group_service.get_user_groups(user_uid)

        teacher_list = teacher_groups.value if teacher_groups.is_ok else []
        member_list = member_groups.value if member_groups.is_ok else []

        return Div(
            H1("Groups"),
            Div(
                H2("My Groups (Teacher)"),
                _render_group_list(teacher_list) if teacher_list else P("No groups created yet."),
                cls="mb-8",
            )
            if teacher_list
            else None,
            Div(
                H2("My Groups (Member)"),
                _render_group_list(member_list)
                if member_list
                else P("Not a member of any groups."),
            ),
            cls="container mx-auto p-4",
        )

    logger.info("✅ Groups UI routes registered")
    return []


def _render_group_list(groups: list[Any]) -> Any:
    """Render a list of groups."""
    return Ul(
        *[
            Li(
                f"{group.name} - {group.get_summary()}",
                cls="py-2",
            )
            for group in groups
        ],
        cls="list-disc pl-4",
    )
