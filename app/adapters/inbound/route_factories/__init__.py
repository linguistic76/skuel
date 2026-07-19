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
- OwnershipRouteFactory: Ownership-verified domain-specific routes
"""

from adapters.inbound.route_factories.activity_field_api_factory import (
    PRIORITY_VALUES,
    ActivityFieldApiConfig,
    FieldUpdateSpec,
    create_activity_field_api_routes,
)
from adapters.inbound.route_factories.activity_link_api_factory import (
    CrossDomainLinkSpec,
    LinkTargetSpec,
    create_activity_link_api_routes,
    create_knowledge_patterns_api_route,
)
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
from adapters.inbound.route_factories.hierarchy_api_factory import (
    ActivityHierarchyApiConfig,
    create_activity_hierarchy_api_routes,
)
from adapters.inbound.route_factories.intelligence_route_factory import (
    IntelligenceOperations,
    IntelligenceRouteFactory,
)
from adapters.inbound.route_factories.ownership_route_factory import (
    OwnershipOperations,
    OwnershipRoute,
    OwnershipRouteFactory,
)
from adapters.inbound.route_factories.query_route_factory import CommonQueryRouteFactory
from adapters.inbound.route_factories.route_helpers import (
    DateRangeParams,
    PaginationParams,
    check_required_role,
    parse_bool_query_param,
    parse_csv_query_param,
    parse_date_param_strict,
    parse_date_query_param,
    parse_date_range_params,
    parse_float_query_param,
    parse_int_param_strict,
    parse_int_query_param,
    parse_pagination_params,
    require_owned_entity,
    split_csv,
    verify_entity_ownership,
)
from adapters.inbound.route_factories.status_route_factory import (
    StatusOperations,
    StatusRouteFactory,
    StatusTransition,
)

__all__ = [
    # Activity Domain HTMX inline field-update endpoint factory
    "PRIORITY_VALUES",
    "ActivityFieldApiConfig",
    "FieldUpdateSpec",
    "create_activity_field_api_routes",
    # Activity Domain hierarchy endpoint factory (July 2026)
    "ActivityHierarchyApiConfig",
    "create_activity_hierarchy_api_routes",
    # Activity Domain cross-domain link + knowledge-pattern factory (July 2026)
    "CrossDomainLinkSpec",
    "LinkTargetSpec",
    "create_activity_link_api_routes",
    "create_knowledge_patterns_api_route",
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
    # Ownership route factory (March 2026)
    "OwnershipOperations",
    "OwnershipRoute",
    "OwnershipRouteFactory",
    # Shared route helpers
    "DateRangeParams",
    "PaginationParams",
    "check_required_role",
    "parse_bool_query_param",
    "parse_csv_query_param",
    "parse_date_param_strict",
    "parse_date_query_param",
    "parse_date_range_params",
    "parse_int_param_strict",
    "parse_float_query_param",
    "parse_int_query_param",
    "parse_pagination_params",
    "require_owned_entity",
    "split_csv",
    "verify_entity_ownership",
    # Status route factory (December 2025)
    "StatusOperations",
    "StatusRouteFactory",
    "StatusTransition",
]
