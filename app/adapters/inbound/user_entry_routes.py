"""
UserEntry Routes (ADR-054 Step 7)
==================================

Wires ``user_entry_api`` via ``DomainRouteConfig``. Additive through
Step 13 — legacy ``submissions_routes`` and ``journals_routes`` stay
registered in parallel until the final cleanup step.

See: /home/mike/.claude/plans/woolly-weaving-hejlsberg.md
     /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.user_entry_api import create_user_entry_api_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.user_entry")

USER_ENTRY_CONFIG = DomainRouteConfig(
    domain_name="user_entry",
    primary_service_attr="user_entry",
    api_factory=create_user_entry_api_routes,
    api_related_services={
        "processing_service": "user_entry_processor",
    },
)


def create_user_entry_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> None:
    """Register the UserEntry REST API routes."""
    register_domain_routes(app, rt, services, USER_ENTRY_CONFIG)


__all__ = ["USER_ENTRY_CONFIG", "create_user_entry_routes"]
