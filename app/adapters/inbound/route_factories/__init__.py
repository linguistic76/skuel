"""
Routes Infrastructure
====================

Generic route factories for eliminating boilerplate in API routes.

Philosophy:
- **Ownership by default**: All factories use `verify_ownership=True` - returns 404 for
  entities the user doesn't own (IDOR protection). Disable only for shared content.
- **Result at boundaries**: Services return `Result[T]`; routes use `@boundary_handler`
  to convert to HTTP responses (200/201/404/500).
- **FastHTML conventions**: Query params over path params (`?uid=...`), POST for all
  mutations, type hints for automatic extraction.

Factories:
- CRUDRouteFactory: Standard CRUD operations (create, get, update, delete, list)
- StatusRouteFactory: Status change operations (activate, pause, complete, archive)
- CommonQueryRouteFactory: Common query patterns (by user, by status, by category)
- IntelligenceRouteFactory: AI/intelligence endpoints (analytics, recommendations)
"""

from adapters.inbound.route_factories.crud_route_factory import (
    CRUDOperations,
    CRUDRouteFactory,
)
from adapters.inbound.route_factories.domain_route_factory import (
    CRUDRouteConfig,
    DomainRouteConfig,
    IntelligenceRouteConfig,
    QueryRouteConfig,
    create_activity_domain_route_config,
    register_domain_routes,
)
from adapters.inbound.route_factories.intelligence_route_factory import (
    IntelligenceOperations,
    IntelligenceRouteFactory,
)
from adapters.inbound.route_factories.query_route_factory import CommonQueryRouteFactory
from adapters.inbound.route_factories.quick_add_factory import (
    QuickAddConfig,
    QuickAddRouteFactory,
)
from adapters.inbound.route_factories.route_helpers import (
    check_required_role,
    verify_entity_ownership,
)
from adapters.inbound.route_factories.status_route_factory import (
    StatusOperations,
    StatusRouteFactory,
    StatusTransition,
)

__all__ = [
    "CRUDOperations",
    "CRUDRouteFactory",
    "CommonQueryRouteFactory",
    # Domain route factory (January 2026)
    "CRUDRouteConfig",
    "DomainRouteConfig",
    "IntelligenceRouteConfig",
    "QueryRouteConfig",
    "create_activity_domain_route_config",
    "register_domain_routes",
    "IntelligenceOperations",
    "IntelligenceRouteFactory",
    # Quick-add form factory (January 2026)
    "QuickAddConfig",
    "QuickAddRouteFactory",
    # Shared route helpers
    "check_required_role",
    "verify_entity_ownership",
    # Status route factory (December 2025)
    "StatusOperations",
    "StatusRouteFactory",
    "StatusTransition",
]
