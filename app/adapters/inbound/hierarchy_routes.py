"""
Hierarchy Routes — Configuration-Driven Registration
=====================================================

Registers hierarchy routes for:
- Goals, Habits, Events, Choices, Principles, LP

Usage:
    from adapters.inbound.hierarchy_routes import create_hierarchy_routes

    hierarchy_routes = create_hierarchy_routes(app, rt, services)

See: /docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md
"""

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.hierarchy_route_factory import HierarchyRouteFactory
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes


def create_hierarchy_api_routes(
    app: FastHTMLApp, rt: RouteDecorator, _primary: Any, **kwargs: Any
) -> RouteList:
    """
    Register hierarchy routes for all hierarchical domains.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        _primary: Primary service (unused — hierarchy uses multiple services)
        **kwargs: All 6 domain services (goals, habits, events, choices, principles, lp)

    Returns:
        List of registered route functions
    """
    routes: RouteList = []

    # Activity domains (5)
    domain_configs = [
        ("goals", kwargs.get("goals"), "Goal"),
        ("habits", kwargs.get("habits"), "Habit"),
        ("events", kwargs.get("events"), "Event"),
        ("choices", kwargs.get("choices"), "Choice"),
        ("principles", kwargs.get("principles"), "Principle"),
    ]

    for domain, service, entity_name in domain_configs:
        if not service:
            continue
        factory = HierarchyRouteFactory(
            app=app,
            rt=rt,
            domain=domain,
            service=service,
            entity_name=entity_name,
        )
        routes.extend(factory.create_routes())

    # LP (special case - uses "steps" instead of "subpaths")
    lp_service = kwargs.get("lp")
    if lp_service:
        lp_factory = HierarchyRouteFactory(
            app=app,
            rt=rt,
            domain="lp",
            service=lp_service,
            entity_name="Learning Path",
            get_children_method="get_steps",
            create_relationship_method="create_step_relationship",
            remove_relationship_method="remove_step_relationship",
            get_parent_method="get_parent_path",
        )
        routes.extend(lp_factory.create_routes())

    return routes


HIERARCHY_CONFIG = DomainRouteConfig(
    domain_name="hierarchy",
    primary_service_attr="goals",
    api_factory=create_hierarchy_api_routes,
    api_related_services={
        "goals": "goals",
        "habits": "habits",
        "events": "events",
        "choices": "choices",
        "principles": "principles",
        "lp": "lp",
    },
)


def create_hierarchy_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> RouteList:
    """Wire hierarchy routes via DomainRouteConfig."""
    return register_domain_routes(app, rt, services, HIERARCHY_CONFIG)
