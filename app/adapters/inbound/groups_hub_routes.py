"""Groups hub routes — student-facing tabbed view of group-shared content.

Routes:
- GET /groups                                — tabbed hub (one tab per group)
- GET /api/groups/{group_uid}/shared/preview — HTMX fragment of peer UserEntries

The preview endpoint's backend query uses the user's MEMBER_OF edge to the
target group as the access guard — non-members get an empty list, not an
error.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.services.groups.group_service import MAX_STUDENT_GROUPS

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services


def create_groups_hub_routes(
    app: "FastHTMLApp",
    rt: "RouteDecorator",
    services: "Services",
) -> None:
    """Register the /groups hub page and its HTMX preview endpoint."""

    @rt("/groups")
    async def groups_hub(request: Request, group: str | None = None) -> Any:
        """Tabbed hub showing content shared with each of a student's groups."""
        user_uid = require_authenticated_user(request)
        from ui.groups.hub import GroupsHub
        from ui.layouts.base_page import BasePage

        groups_list: list[Any] = []
        if services.groups is not None:
            groups_result = await services.groups.get_user_groups(user_uid)
            if not groups_result.is_error:
                groups_list = (groups_result.value or [])[:MAX_STUDENT_GROUPS]

        active = (
            group
            if group and any(g.uid == group for g in groups_list)
            else (groups_list[0].uid if groups_list else None)
        )

        return await BasePage(
            content=GroupsHub(groups=groups_list, active_group_uid=active),
            title="Groups",
            request=request,
            active_page="groups",
        )

    @rt("/api/groups/{group_uid}/shared/preview")
    async def groups_shared_preview(request: Request, group_uid: str) -> Any:
        """HTMX fragment: peer UserEntries shared with one group."""
        user_uid = require_authenticated_user(request)
        from ui.groups.shared_preview import GroupSharedPreviewList
        from ui.patterns.hub import HubPreviewEmpty

        if services.sharing is None:
            return HubPreviewEmpty("shared entries")

        result = await services.sharing.get_user_entries_shared_with_group(
            user_uid=user_uid, group_uid=group_uid, limit=12
        )
        records = [] if result.is_error else (result.value or [])
        if not records:
            return HubPreviewEmpty("shared entries")
        return GroupSharedPreviewList(records)


__all__ = ["create_groups_hub_routes"]
