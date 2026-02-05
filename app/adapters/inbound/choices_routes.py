"""
Choices Routes - Config-Driven Registration
============================================

Activity Domain: CRUD, Query, and Intelligence factories declared in config.
No Status or Analytics factories — all remaining routes are manual.
"""

from adapters.inbound.choice_ui import create_choice_ui_routes
from adapters.inbound.choices_api import create_choices_api_routes
from core.infrastructure.routes import create_activity_domain_route_config, register_domain_routes
from core.models.choice.choice_request import ChoiceCreateRequest, ChoiceUpdateRequest

CHOICES_CONFIG = create_activity_domain_route_config(
    domain_name="choices",
    primary_service_attr="choices",
    api_factory=create_choices_api_routes,
    ui_factory=create_choice_ui_routes,
    create_schema=ChoiceCreateRequest,
    update_schema=ChoiceUpdateRequest,
    uid_prefix="choice",
    supports_goal_filter=True,
    supports_habit_filter=False,
    api_related_services={
        "user_service": "user_service",
        "goals_service": "goals",
    },
)


def create_choices_routes(app, rt, services, _sync_service=None):
    """Wire choices API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, CHOICES_CONFIG)


__all__ = ["create_choices_routes"]
