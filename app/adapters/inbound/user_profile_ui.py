"""The Shared page at ``/profile/shared`` — two sides (Submit & Share arc R7).

Routes:
- GET /profile/shared — *Shared with you* (what the share links name the viewer
  for) + *Your wall* (what the viewer shared, with Stop sharing)
- GET /profile/shared/list-fragment — the filtered card grid for a FilterBar change

The navbar's inbox icon is the door. Nothing else answers under ``/profile``:
a user's activities, curriculum, submissions and reports each have their own
section (``/today``, ``/library``, ``/submissions``, ``/gradebook``). Stop
sharing posts to ``/api/user-entries/{uid}/unshare`` (``user_entry_api.py``).
"""

from typing import TYPE_CHECKING, Any

# FT imported at runtime: FastHTML resolves handler signature annotations at
# registration, so a TYPE_CHECKING-only import would kill bootstrap.
from fasthtml.common import FT, Div

from core.models.enums.entity_enums import EntityType
from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from services_bootstrap import Services

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.profile.shared_view import (
    SHARED_PAGE_TITLE,
    SHARED_WITH_YOU_SUBTITLE,
    SharedPage,
    shared_items_content,
)

logger = get_logger("skuel.routes.user_profile")

_INBOX_LIMIT = 50
_WALL_LIMIT = 100
_LOAD_FAILED = "Could not load your shared items. Please try again."


def setup_user_profile_routes(rt: Any, services: Services) -> None:
    """Register the Shared page routes.

    Args:
        rt: FastHTML route decorator
        services: Services container — ``services.sharing`` is the one read
    """

    if services.sharing is None:
        raise RuntimeError("UnifiedSharingService is required for the Shared page routes")
    sharing_service = services.sharing

    @rt("/profile/shared")
    async def profile_shared(request: Request) -> Any:
        """The Shared page: *Shared with you* and *Your wall*.

        Both sides are the share links' record (ADR-088 §3): the first lists
        UserEntries and FormSubmissions a person or group share names the
        viewer for, the second the viewer's own shared entries with their
        audience. Feedback never appears here (R3).
        """
        user_uid = require_authenticated_user(request)

        items_result = await sharing_service.get_shared_with_me(
            user_uid=user_uid, limit=_INBOX_LIMIT
        )
        wall_result = await sharing_service.get_shared_by_me(user_uid=user_uid, limit=_WALL_LIMIT)
        if items_result.is_error or wall_result.is_error:
            # Outage ≠ empty: a failed read must never render as a blank page.
            failed = items_result if items_result.is_error else wall_result
            logger.error(f"Failed to load the Shared page: {failed.expect_error()}")
            content: Div = Div(
                PageHeader(SHARED_PAGE_TITLE, subtitle=SHARED_WITH_YOU_SUBTITLE),
                render_error_banner(_LOAD_FAILED),
            )
        else:
            content = SharedPage(items_result.value, wall_result.value)

        return BasePage(
            content=content,
            title=SHARED_PAGE_TITLE,
            request=request,
            active_page="shared",
        )

    @rt("/profile/shared/list-fragment")
    async def profile_shared_list_fragment(
        request: Request, entity_type: str = "all", sharer: str = "all", via: str = "all"
    ) -> FT:
        """HTMX fragment: the filtered *Shared with you* grid for a FilterBar change.

        Filter params are clamped, never 400'd (the gradebook convention):
        an unknown ``entity_type`` parses to ``None`` = All, and every value
        crosses the service boundary typed (EntityType / UserUID / the via
        token) — the Cypher only ever sees driver parameters.
        """
        user_uid = require_authenticated_user(request)

        type_filter = EntityType.from_string(entity_type) if entity_type != "all" else None
        sharer_filter = UserUID(sharer) if sharer != "all" else None
        via_filter = via if via != "all" else None

        items_result = await sharing_service.get_shared_with_me(
            user_uid=user_uid,
            limit=_INBOX_LIMIT,
            entity_type=type_filter,
            sharer_uid=sharer_filter,
            via=via_filter,
        )
        if items_result.is_error:
            logger.error(f"Failed to load shared-with-you items: {items_result.expect_error()}")
            return render_error_banner(_LOAD_FAILED)

        return shared_items_content(
            items_result.value,
            filtered=type_filter is not None or sharer_filter is not None or via_filter is not None,
        )

    logger.info("✅ Shared page routes registered (/profile/shared, /profile/shared/list-fragment)")


__all__ = ["setup_user_profile_routes"]
