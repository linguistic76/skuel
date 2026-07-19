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

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.hierarchy_route_factory import HierarchyRouteFactory
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.models.choice.choice_request import ChoiceUpdateRequest
from core.models.event.event_request import EventUpdateRequest
from core.models.goal.goal_request import GoalUpdateRequest
from core.models.habit.habit_request import HabitUpdateRequest
from core.models.principle.principle_request import PrincipleUpdateRequest

if TYPE_CHECKING:
    from pydantic import BaseModel


def create_hierarchy_api_routes(
    app: FastHTMLApp, rt: RouteDecorator, _primary: Any, **kwargs: Any
) -> list[Any]:
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
    routes: list[Any] = []

    # Activity domains (5) — each carries its *UpdateRequest so inline title edits build
    # the typed *UpdateIntent (ADR-066), not a plain dict the facade can no longer accept.
    # Their GET /{uid}/children fragment comes from create_activity_hierarchy_api_routes
    # (registered per domain in *_api.py), NOT from this factory — One Path Forward.
    domain_configs: list[tuple[str, Any, str, type[BaseModel]]] = [
        ("goals", kwargs.get("goals"), "Goal", GoalUpdateRequest),
        ("habits", kwargs.get("habits"), "Habit", HabitUpdateRequest),
        ("events", kwargs.get("events"), "Event", EventUpdateRequest),
        ("choices", kwargs.get("choices"), "Choice", ChoiceUpdateRequest),
        ("principles", kwargs.get("principles"), "Principle", PrincipleUpdateRequest),
    ]

    for domain, service, entity_name, update_schema in domain_configs:
        if not service:
            continue
        factory = HierarchyRouteFactory(
            app=app,
            rt=rt,
            domain=domain,
            service=service,
            entity_name=entity_name,
            update_schema=update_schema,
        )
        routes.extend(factory.create_routes())

    # LP (special case - uses "steps" instead of "subpaths"; SHARED content, so its
    # children fragment stays on this factory rather than the activity hierarchy factory)
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
            register_children_route=True,
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
) -> None:
    """Wire hierarchy routes via DomainRouteConfig."""
    register_domain_routes(app, rt, services, HIERARCHY_CONFIG)
