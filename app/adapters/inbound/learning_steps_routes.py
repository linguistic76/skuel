"""
Learning Steps Routes - Configuration-Driven Registration
=========================================================

Standalone DomainRouteConfig for Learning Steps (LS).
Called from pathways_routes.py since LS lives under the Pathways umbrella.

Version: 3.0 (Migrated to DomainRouteConfig pattern)
"""

from adapters.inbound.learning_steps_api import create_learning_steps_api_routes
from adapters.inbound.route_factories import (
    CRUDRouteConfig,
    DomainRouteConfig,
    IntelligenceRouteConfig,
)
from core.models.entity_requests import EntityUpdateRequest as KuStepUpdateRequest
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.pathways.pathways_request import LearningStepCreateRequest

LS_CONFIG = DomainRouteConfig(
    domain_name="learning-steps",
    primary_service_attr="ls",  # services.ls
    api_factory=create_learning_steps_api_routes,
    api_related_services={
        "user_service": "user_service",
    },
    crud=CRUDRouteConfig(
        create_schema=LearningStepCreateRequest,
        update_schema=KuStepUpdateRequest,
        uid_prefix="ls",
        scope=ContentScope.SHARED,
        require_role=UserRole.ADMIN,
        user_service_attr="user_service",
    ),
    intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED),
)

__all__ = ["LS_CONFIG"]
