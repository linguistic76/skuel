"""
Activity Template panel route (teacher-only, read-only).

Templates are authored as ``_tmpl.md`` files in the content vault and attached
to a PathStep by its ``{domain}_template_uids:`` frontmatter. SKUEL surfaces
them; it does not author them.

- Panel fragment on the PS detail page (HTMX-loaded, TEACHER+):
  ``GET /teaching/ps/{ps_uid}/templates`` — the templates attached to the PS,
  grouped by Activity Domain.

The app has no template write door of any kind (ADR-091 S8): the vault is the
one author of templates and of their attachment to a PathStep.

See: /docs/guides/ACTIVITY_TEMPLATE_AUTHORING.md
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import make_service_getter
from adapters.inbound.auth.roles import UserRole, require_role
from adapters.inbound.fasthtml_types import Request
from core.ports import ActivityTemplateOperations
from core.utils.logging import get_logger
from ui.teaching.templates_panel import PANEL_DOMAINS, render_templates_panel

if TYPE_CHECKING:
    from services_bootstrap import Services

logger = get_logger("skuel.routes.templates_ui")


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

    # The URL-facing domain name → its template service, read-only by type.
    raw_services: dict[str, ActivityTemplateOperations | None] = {
        "task": services.task_templates,
        "goal": services.goal_templates,
        "habit": services.habit_templates,
        "event": services.event_templates,
        "choice": services.choice_templates,
        "principle": services.principle_templates,
    }
    template_services = {
        domain: service for domain, service in raw_services.items() if service is not None
    }
    if len(template_services) != len(raw_services):
        logger.warning(
            "Template UI routes registered, but one or more template services is None "
            "— skipping registration"
        )
        return

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
        attached = await _gather_attached(ps_uid)
        return render_templates_panel(ps_uid, attached)

    logger.info(
        "Templates UI routes registered (read-only panel fragment for %d domains)",
        len(PANEL_DOMAINS),
    )


__all__ = ["create_templates_ui_routes"]
