"""Groups hub routes — student-facing tabbed view of group-shared content.

Routes:
- GET /groups                                       — tabbed hub (one tab per group)
- GET /groups/{group_uid}                           — full list for one group
- GET /api/groups/{group_uid}/shared/preview        — HTMX fragment of peer UserEntries

The lists are the *Shared with you* read narrowed to one group
(``get_shared_with_me(via=group_uid)``): the same reader the Shared page
uses, gated by the one audience fragment (ADR-088 §5), so a non-member gets
an empty list, never an error that leaks existence — and a listed entry opens
at ``/gradebook/{entry_uid}`` for the same viewer (the recipient card).
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.services.groups.group_service import MAX_STUDENT_GROUPS

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services


def create_groups_hub_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
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
            # Student hub: only count student-role memberships against the cap.
            # A user who is a teaching-assistant (MEMBER_OF {role: "teacher"})
            # in several groups would otherwise starve their student tabs.
            groups_result = await services.groups.get_user_groups(user_uid, role="student")
            if not groups_result.is_error:
                groups_list = (groups_result.value or [])[:MAX_STUDENT_GROUPS]

        active = (
            group
            if group and any(g.uid == group for g in groups_list)
            else (groups_list[0].uid if groups_list else None)
        )

        return BasePage(
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

        result = await services.sharing.get_shared_with_me(
            user_uid=user_uid, limit=12, via=group_uid
        )
        records = [] if result.is_error else (result.value or [])
        if not records:
            return HubPreviewEmpty("shared entries")
        return GroupSharedPreviewList(records)

    @rt("/groups/{group_uid}")
    async def group_shares_page(request: Request, group_uid: str) -> Any:
        """Full list of peer UserEntries shared with one group."""
        user_uid = require_authenticated_user(request)
        from ui.groups.group_page import GroupSharesNotAvailable, GroupSharesPage
        from ui.layouts.base_page import BasePage

        group_name: str | None = None
        if services.groups is not None:
            groups_result = await services.groups.get_user_groups(user_uid, role="student")
            if not groups_result.is_error:
                for g in groups_result.value or []:
                    if g.uid == group_uid:
                        group_name = g.name
                        break

        if group_name is None or services.sharing is None:
            return BasePage(
                content=GroupSharesNotAvailable(),
                title="Group not available",
                request=request,
                active_page="groups",
            )

        result = await services.sharing.get_shared_with_me(
            user_uid=user_uid, limit=100, via=group_uid
        )
        records = [] if result.is_error else (result.value or [])

        return BasePage(
            content=GroupSharesPage(group_name=group_name, records=records, group_uid=group_uid),
            title=group_name,
            request=request,
            active_page="groups",
        )


__all__ = ["create_groups_hub_routes"]
