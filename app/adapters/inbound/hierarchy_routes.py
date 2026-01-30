"""
Hierarchy Routes - API Endpoints for All Domains
=================================================

Registers hierarchy routes for:
- Goals, Habits, Events, Choices, Principles, LP

Usage:
    from adapters.inbound.hierarchy_routes import create_hierarchy_routes

    hierarchy_routes = create_hierarchy_routes(app, rt, services)

See: /docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md
"""

from typing import Any

from core.infrastructure.routes.hierarchy_route_factory import HierarchyRouteFactory


def create_hierarchy_routes(app: Any, rt: Any, services: Any) -> list[Any]:
    """
    Register hierarchy routes for all hierarchical domains.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        services: ServiceContainer with all domain services

    Returns:
        List of registered route functions
    """
    routes = []

    # Activity domains (5)
    domain_configs = [
        ("goals", services.goals, "Goal"),
        ("habits", services.habits, "Habit"),
        ("events", services.events, "Event"),
        ("choices", services.choices, "Choice"),
        ("principles", services.principles, "Principle"),
    ]

    for domain, service, entity_name in domain_configs:
        factory = HierarchyRouteFactory(
            app=app,
            rt=rt,
            domain=domain,
            service=service,
            entity_name=entity_name,
        )
        routes.extend(factory.create_routes())

    # LP (special case - uses "steps" instead of "subpaths")
    lp_factory = HierarchyRouteFactory(
        app=app,
        rt=rt,
        domain="lp",
        service=services.lp,  # Consistent short name (ku, ls, lp)
        entity_name="Learning Path",
        get_children_method="get_steps",  # LP uses steps instead of sublps
        create_relationship_method="create_step_relationship",
        remove_relationship_method="remove_step_relationship",
        get_parent_method="get_parent_path",
    )
    routes.extend(lp_factory.create_routes())

    return routes
