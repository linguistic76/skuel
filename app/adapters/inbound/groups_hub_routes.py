"""Groups hub routes — student-facing tabbed view of group-shared content.

Routes:
- GET /groups                                       — tabbed hub (one tab per group)
- GET /groups/{group_uid}                           — full list for one group
- GET /groups/{group_uid}/entries/{entry_uid}       — peer UserEntry detail
- GET /api/groups/{group_uid}/shared/preview        — HTMX fragment of peer UserEntries

All four endpoints use the viewer's MEMBER_OF edge as the Cypher-level
access guard — non-members get an empty/404 response, never an error that
leaks existence.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.models.type_hints import EntityUID
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

        result = await services.sharing.get_user_entries_shared_with_group(
            user_uid=user_uid, group_uid=group_uid, limit=12
        )
        records = [] if result.is_error else (result.value or [])
        if not records:
            return HubPreviewEmpty("shared entries")
        return GroupSharedPreviewList(records, group_uid=group_uid)

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

        result = await services.sharing.get_user_entries_shared_with_group(
            user_uid=user_uid, group_uid=group_uid, limit=100
        )
        records = [] if result.is_error else (result.value or [])

        return BasePage(
            content=GroupSharesPage(group_name=group_name, records=records, group_uid=group_uid),
            title=group_name,
            request=request,
            active_page="groups",
        )

    @rt("/groups/{group_uid}/entries/{entry_uid}")
    async def peer_entry_detail(request: Request, group_uid: str, entry_uid: str) -> Any:
        """Read-only detail page for a peer UserEntry shared with a group."""
        user_uid = require_authenticated_user(request)
        from ui.groups.peer_entry import PeerEntryNotFound, PeerEntryView
        from ui.layouts.base_page import BasePage

        payload: dict[str, Any] | None = None
        if services.sharing is not None:
            result = await services.sharing.get_user_entry_shared_with_group(
                user_uid=user_uid, group_uid=group_uid, entry_uid=EntityUID(entry_uid)
            )
            if not result.is_error:
                payload = result.value

        if payload is None:
            title = "Entry not available"
            content = PeerEntryNotFound()
        else:
            title = (payload.get("entity") or {}).get("title") or "Shared entry"
            content = PeerEntryView(payload, group_uid=group_uid)

        return BasePage(
            content=content,
            title=title,
            request=request,
            active_page="groups",
        )


__all__ = ["create_groups_hub_routes"]
