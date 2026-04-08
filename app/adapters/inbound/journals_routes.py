"""Journals Routes — Standalone Route Configuration for JE_INPUT + JE_OUTPUT
=========================================================================

Wires journal UI routes using DomainRouteConfig. Journals are a standalone domain
with their own services (JournalInputService, JournalOutputService) — no dependency
on SubmissionsService.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.journals_ui import create_journals_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.journals")


def _journals_noop_api_factory(_app: Any, _rt: Any, _primary: Any, **_kw: Any) -> list[Any]:
    """No-op — journals have no dedicated REST API routes yet (all interaction via UI)."""
    return []


JOURNALS_CONFIG = DomainRouteConfig(
    domain_name="journals",
    primary_service_attr="journal_orchestrator",
    api_factory=_journals_noop_api_factory,
    ui_factory=create_journals_ui_routes,
)


def create_journals_routes(app: FastHTMLApp, rt: RouteDecorator, services: Any) -> None:
    """Wire journal routes using configuration-driven registration.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container
    """
    register_domain_routes(app, rt, services, JOURNALS_CONFIG)
    logger.info("Journals routes registered (standalone domain)")


__all__ = ["create_journals_routes"]
