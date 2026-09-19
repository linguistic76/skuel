"""Shared With Me — the reviewing inbox under the ``/profile`` prefix.

Routes:
- GET /profile/shared — Shared With Me inbox (SHARES_WITH entities, type-aware cards)
- GET /profile/shared/list-fragment — the filtered card grid for a FilterBar change

The ``/profile`` hub itself is retired (no route, no redirect): its tabs live
where their content lives — Tasks+ (``/today``), Library (``/library``),
Submissions (``/submissions``) and the GradeBook (``/gradebook``). The inbox
keeps its URL — the navbar's inbox icon is its door.
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
    SHARED_WITH_ME_SUBTITLE,
    SharedWithMeView,
    shared_items_content,
)

logger = get_logger("skuel.routes.user_profile")

_INBOX_LIMIT = 50


def setup_user_profile_routes(rt: Any, services: Services) -> None:
    """Register the Shared With Me inbox routes.

    Args:
        rt: FastHTML route decorator
        services: Services container — ``services.sharing`` is the one read
    """

    if services.sharing is None:
        raise RuntimeError("UnifiedSharingService is required for the shared-with-me routes")
    sharing_service = services.sharing

    @rt("/profile/shared")
    async def profile_shared(request: Request) -> Any:
        """Shared With Me — the reviewing inbox of SHARES_WITH entities.

        Type-aware inbox: ADR-040 auto-shared feedback (EntryReports,
        RevisedExercises) and manually shared FormSubmissions render the same
        card shape, narrowed by the Type · Shared-by FilterBar (arc 2 C4).
        Group shares surface on /groups, not here.
        """
        user_uid = require_authenticated_user(request)

        items_result = await sharing_service.get_shared_with_me(
            user_uid=user_uid,
            limit=_INBOX_LIMIT,
            entity_type=None,
            sharer_uid=None,
        )
        if items_result.is_error:
            # Outage ≠ empty: a failed read must never render as a blank inbox.
            logger.error(f"Failed to load shared-with-me items: {items_result.expect_error()}")
            content: Div = Div(
                PageHeader("Shared With Me", subtitle=SHARED_WITH_ME_SUBTITLE),
                render_error_banner("Could not load your shared items. Please try again."),
            )
        else:
            content = SharedWithMeView(items_result.value)

        return BasePage(
            content=content,
            title="Shared With Me",
            request=request,
            active_page="shared",
        )

    @rt("/profile/shared/list-fragment")
    async def profile_shared_list_fragment(
        request: Request, entity_type: str = "all", sharer: str = "all"
    ) -> FT:
        """HTMX fragment: the filtered card grid for a FilterBar change.

        Filter params are clamped, never 400'd (the gradebook convention):
        an unknown ``entity_type`` parses to ``None`` = All, and both values
        cross the service boundary typed (EntityType / UserUID) — the Cypher
        only ever sees driver parameters.
        """
        user_uid = require_authenticated_user(request)

        type_filter = EntityType.from_string(entity_type) if entity_type != "all" else None
        sharer_filter = UserUID(sharer) if sharer != "all" else None

        items_result = await sharing_service.get_shared_with_me(
            user_uid=user_uid,
            limit=_INBOX_LIMIT,
            entity_type=type_filter,
            sharer_uid=sharer_filter,
        )
        if items_result.is_error:
            logger.error(f"Failed to load shared-with-me items: {items_result.expect_error()}")
            return render_error_banner("Could not load your shared items. Please try again.")

        return shared_items_content(
            items_result.value,
            filtered=type_filter is not None or sharer_filter is not None,
        )

    logger.info(
        "✅ Shared With Me routes registered (/profile/shared, /profile/shared/list-fragment)"
    )


__all__ = ["setup_user_profile_routes"]
