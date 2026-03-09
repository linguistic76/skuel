"""
Exercise Routes - Configuration-Driven Registration
======================================================

Wires Exercise API and UI routes using DomainRouteConfig.
Exercises provide reusable LLM instruction templates for any submission type.

Formerly assignments_routes.py — renamed per of Ku hierarchy refactoring.
"""

from adapters.inbound.exercises_api import create_exercises_api_routes
from adapters.inbound.exercises_ui import create_exercises_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

EXERCISES_CONFIG = DomainRouteConfig(
    domain_name="exercises",
    primary_service_attr="exercises",
    api_factory=create_exercises_api_routes,
    ui_factory=create_exercises_ui_routes,
    api_related_services={
        "transcript_service": "content_enrichment",
        "report_feedback_service": "submission_report",
        "user_service": "user_service",
    },
    ui_related_services={
        "transcript_service": "content_enrichment",
        "user_service": "user_service",
    },
)


def create_exercises_routes(app, rt, services, _sync_service=None):
    """Wire exercise API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, EXERCISES_CONFIG)


__all__ = ["create_exercises_routes"]
