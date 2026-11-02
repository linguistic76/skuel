"""
Hierarchy Routes — Configuration-Driven Registration
=====================================================

Registers hierarchy routes for:
- Goals, Habits, Events, Choices, Principles

Usage:
    from adapters.inbound.hierarchy_routes import create_hierarchy_routes

    create_hierarchy_routes(rt, services)

See: /docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import RouteDecorator
from adapters.inbound.hierarchy_route_factory import HierarchyRouteFactory
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.models.choice.choice_request import ChoiceUpdateRequest
from core.models.event.event_request import EventUpdateRequest
from core.models.goal.goal_request import GoalUpdateRequest
from core.models.habit.habit_request import HabitUpdateRequest
from core.models.principle.principle_request import PrincipleUpdateRequest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.principles_service import PrinciplesService
    from services_bootstrap import Services


def create_hierarchy_api_routes(
    rt: RouteDecorator,
    _primary: GoalsService,
    *,
    goals_service: GoalsService | None,
    habits_service: HabitsService | None,
    events_service: EventsService | None,
    choices_service: ChoicesService | None,
    principles_service: PrinciplesService | None,
) -> None:
    """
    Register hierarchy routes for all hierarchical domains.

    A domain whose service is absent from the container registers nothing.

    Args:
        rt: FastHTML route decorator
        _primary: Primary service (unused — hierarchy uses the five below)
        goals_service: GoalsService
        habits_service: HabitsService
        events_service: EventsService
        choices_service: ChoicesService
        principles_service: PrinciplesService
    """

    # Activity domains (5) — each carries its *UpdateRequest so inline title edits build
    # the typed *UpdateIntent (ADR-066), not a plain dict the facade can no longer accept.
    # Their GET /{uid}/children fragment comes from create_activity_hierarchy_api_routes
    # (registered per domain in *_api.py), NOT from this factory — One Path Forward.
    domain_configs: list[tuple[str, Any, str, type[BaseModel]]] = [
        ("goals", goals_service, "Goal", GoalUpdateRequest),
        ("habits", habits_service, "Habit", HabitUpdateRequest),
        ("events", events_service, "Event", EventUpdateRequest),
        ("choices", choices_service, "Choice", ChoiceUpdateRequest),
        ("principles", principles_service, "Principle", PrincipleUpdateRequest),
    ]

    for domain, service, entity_name, update_schema in domain_configs:
        if not service:
            continue
        factory = HierarchyRouteFactory(
            rt=rt,
            domain=domain,
            service=service,
            entity_name=entity_name,
            update_schema=update_schema,
        )
        factory.create_routes()


HIERARCHY_CONFIG = DomainRouteConfig(
    domain_name="hierarchy",
    primary_service_attr="goals",
    api_factory=create_hierarchy_api_routes,
    api_related_services={
        "goals_service": "goals",
        "habits_service": "habits",
        "events_service": "events",
        "choices_service": "choices",
        "principles_service": "principles",
    },
)


def create_hierarchy_routes(rt: RouteDecorator, services: Services) -> None:
    """Wire hierarchy routes via DomainRouteConfig."""
    register_domain_routes(rt, services, HIERARCHY_CONFIG)
