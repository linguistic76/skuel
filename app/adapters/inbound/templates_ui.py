"""
Activity Template panel route (teacher-only, read-only).

Templates are authored as ``_tmpl.md`` files in the content vault and attached
to a PathStep by its ``{domain}_template_uids:`` frontmatter. SKUEL surfaces
them; it does not author them.

- Panel fragment on the PS detail page (HTMX-loaded, TEACHER+):
  ``GET /teaching/ps/{ps_uid}/templates`` — the templates attached to the PS,
  grouped by Activity Domain.

The create/edit/detach web forms were deleted with the arc's PR-3, the same
trade the 6 Activity instances made in March 2026: the vault becomes the
authoring layer, the service facades and JSON CRUD stay.

See: /docs/guides/ACTIVITY_TEMPLATE_AUTHORING.md
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from adapters.inbound.auth import make_service_getter, require_authenticated_user
from adapters.inbound.auth.roles import UserRole, require_role
from adapters.inbound.fasthtml_types import Request
from core.ports import ActivityTemplateOperations
from core.utils.logging import get_logger
from ui.teaching.templates_panel import PANEL_DOMAINS, render_templates_panel

if TYPE_CHECKING:
    from services_bootstrap import Services

logger = get_logger("skuel.routes.templates_ui")


# ----------------------------------------------------------------------------
# Service mapping
# ----------------------------------------------------------------------------
# Maps the URL ``{domain}`` segment to the Services attribute holding the
# matching template service. Kept here (not in the panel file) so the UI module
# doesn't depend on the bootstrap container.

_DOMAIN_TO_SERVICE_ATTR: dict[str, str] = {
    "task": "task_templates",
    "goal": "goal_templates",
    "habit": "habit_templates",
    "event": "event_templates",
    "choice": "choice_templates",
    "principle": "principle_templates",
}


def create_templates_ui_routes(
    _app: Any,
    rt: Any,
    services: Services | None,
    _sync_service: Any = None,
) -> None:
    """Register the teacher-facing template panel route.

    No-op (with a warning) if any of the 6 template services is missing —
    bootstrap may run in a partial mode that omits the template subsystem.
    """
    if services is None:
        logger.warning("Template UI routes registered without services")
        return

    raw_services = {
        domain: getattr(services, attr, None) for domain, attr in _DOMAIN_TO_SERVICE_ATTR.items()
    }
    if any(s is None for s in raw_services.values()):
        logger.warning(
            "Template UI routes registered, but one or more template services is None "
            "— skipping registration"
        )
        return
    template_services: dict[str, ActivityTemplateOperations] = cast(
        "dict[str, ActivityTemplateOperations]", dict(raw_services)
    )

    user_service = getattr(services, "user", None)
    get_user_service = make_service_getter(user_service)

    async def _gather_attached(ps_uid: str) -> dict[str, list[dict[str, Any]]]:
        """Fetch the property-dict list of templates attached to ``ps_uid``.

        Six independent reads, one per Activity Domain — fanned out rather than
        awaited in turn, because this runs on every TEACHER+ PS detail page
        load and each is its own graph round-trip.
        """
        domains = list(template_services)
        results = await asyncio.gather(
            *(template_services[domain].list_for_pathstep(ps_uid) for domain in domains)
        )
        return {
            domain: result.value if result.is_ok else []
            for domain, result in zip(domains, results, strict=True)
        }

    # ------------------------------------------------------------------
    # GET /teaching/ps/{ps_uid}/templates  — panel fragment
    # ------------------------------------------------------------------

    @rt("/teaching/ps/{ps_uid}/templates")
    @require_role(UserRole.TEACHER, get_user_service)
    async def templates_panel_fragment(
        request: Request, ps_uid: str, current_user: Any = None
    ) -> Any:
        require_authenticated_user(request)
        attached = await _gather_attached(ps_uid)
        return render_templates_panel(ps_uid, attached)

    logger.info(
        "Templates UI routes registered (read-only panel fragment for %d domains)",
        len(PANEL_DOMAINS),
    )


__all__ = ["create_templates_ui_routes"]
