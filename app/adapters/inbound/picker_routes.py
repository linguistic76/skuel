"""
Picker Routes — searchable cross-domain entity dropdown
========================================================

Backend for ``ui/patterns/entity_picker.py``. One HTML-fragment endpoint
that the picker hits via HTMX:

    GET /api/picker/search?type={goal|habit|task|event|choice|principle}
                          &q=<text>
                          &exclude_uid=<uid>
                          &exclude_descendants_of=<uid>

Returns a list of ``<li role="option">`` elements with ``data-uid`` /
``data-title`` attributes so the Alpine ``entityPicker`` component can
copy the selection into the parent form's hidden input on click.

Empty ``q`` → user's 10 most-recently-updated entities of the requested
type. Non-empty ``q`` → title/description text search scoped to the
authenticated user.

Routes are registered as Pattern C (manual ``@rt()``) per CLAUDE.md
because this endpoint serves multiple domains and doesn't fit
``DomainRouteConfig``'s single-domain shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Li

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.models.protocols import DomainModelProtocol
    from core.ports.search_protocols import DomainSearchOperations
    from services_bootstrap import Services

logger = get_logger("skuel.routes.picker")


_SUPPORTED_TYPES = ("goal", "habit", "task", "event", "choice", "principle")


def create_picker_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Services, _sync_service: Any = None
) -> None:
    """Register the entity-picker search endpoint."""

    @rt("/api/picker/search")
    async def picker_search(
        request: Request,
        type: str = "",
        q: str = "",
        exclude_uid: str = "",
        exclude_descendants_of: str = "",
    ) -> Any:
        """Return a fragment of <li> options for the picker dropdown."""
        user_uid = require_authenticated_user(request)

        if type not in _SUPPORTED_TYPES:
            logger.warning("picker.search rejected unknown type=%r", type)
            return _empty_results(message=f"Unsupported picker type: {type!r}")

        search_service = _resolve_search_service(services, type)
        if search_service is None:
            logger.error("picker.search has no service wired for type=%r", type)
            return _empty_results(message="Picker service unavailable")

        excluded = await _build_exclusion_set(
            search_service, exclude_uid or None, exclude_descendants_of or None
        )

        query = q.strip()
        if query:
            result = await search_service.search_for_user(
                query=query, user_uid=user_uid, limit=10, exclude=excluded
            )
        else:
            result = await search_service.list_recent_for_user(
                user_uid=user_uid, limit=10, exclude=excluded
            )

        if result.is_error:
            logger.warning("picker.search backend error: %s", result.expect_error())
            return _empty_results(message="Search failed")

        return _render_results(result.value)


def _resolve_search_service(
    services: Services, target_type: str
) -> DomainSearchOperations[Any] | None:
    """Map ``target_type`` to the correct activity-domain search service."""
    facade = {
        "task": services.tasks,
        "goal": services.goals,
        "habit": services.habits,
        "event": services.events,
        "choice": services.choices,
        "principle": services.principles,
    }.get(target_type)
    if facade is None:
        return None
    return facade.search


async def _build_exclusion_set(
    search_service: DomainSearchOperations[Any],
    exclude_uid: str | None,
    exclude_descendants_of: str | None,
) -> set[str]:
    """Resolve ``exclude_uid`` and ``exclude_descendants_of`` into one UID set.

    For self-referential pickers (e.g., Task ``parent_uid`` editing an existing
    task), the descendants-of UID itself plus the full subtree must be filtered
    so the user can't pick a cycle-inducing parent.
    """
    excluded: set[str] = set()
    if exclude_uid:
        excluded.add(exclude_uid)
    if exclude_descendants_of:
        excluded.add(exclude_descendants_of)
        backend = getattr(search_service, "backend", None)
        if backend is None:
            logger.debug("search service has no .backend attribute; skipping descendants")
            return excluded
        result = await backend.get_descendant_uids(exclude_descendants_of)
        if result.is_ok:
            excluded.update(result.value)
        else:
            logger.warning(
                "picker.search descendants lookup failed for %s: %s",
                exclude_descendants_of,
                result.expect_error(),
            )
    return excluded


def _render_results(entities: list[DomainModelProtocol]) -> Any:
    """Render entities as a Ul of selectable Li options."""
    items = [
        Li(
            getattr(entity, "title", "") or entity.uid,
            **{
                "data-uid": entity.uid,
                "data-title": getattr(entity, "title", "") or entity.uid,
                "role": "option",
                "tabindex": "-1",
                "cls": "px-3 py-2 cursor-pointer hover:bg-accent",
            },
        )
        for entity in entities
    ]
    if not items:
        items = [
            Li(
                "No matches",
                **{
                    "role": "option",
                    "aria-disabled": "true",
                    "cls": "px-3 py-2 text-muted-foreground",
                },
            )
        ]
    # The OOB-replace target is the inner <ul>; HTMX swaps innerHTML by default.
    # We return the bare <li> list so it slots cleanly into the existing <ul>.
    return tuple(items)


def _empty_results(*, message: str) -> Any:
    """Return a single disabled-option fragment for error / unsupported states."""
    return (
        Li(
            message,
            **{
                "role": "option",
                "aria-disabled": "true",
                "cls": "px-3 py-2 text-muted-foreground",
            },
        ),
    )


__all__ = ["create_picker_routes"]
