"""
Lateral Relationship Routes — Configuration-Driven Registration
================================================================

Registers lateral relationship routes for all 9 hierarchical domains:
- Activity Domains (6): Tasks, Goals, Habits, Events, Choices, Principles
- Curriculum Domains (3): KU, LS, LP

Each domain gets a full set of lateral relationship endpoints via LateralRouteFactory.
Domain-specific routes (habit stacking, event conflicts, KU enables) use shared
helpers to eliminate per-domain boilerplate.

See: /docs/architecture/LATERAL_RELATIONSHIPS_CORE.md
"""

from typing import Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.route_factories.lateral_route_factory import LateralRouteFactory
from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)

# Domain configs: (domain, entity_name, service_attr or None for curriculum)
_LATERAL_DOMAINS: list[tuple[str, str, str | None]] = [
    ("tasks", "Task", "tasks"),
    ("goals", "Goal", "goals"),
    ("habits", "Habit", "habits"),
    ("events", "Event", "events"),
    ("choices", "Choice", "choices"),
    ("principles", "Principle", "principles"),
    ("ku", "Knowledge Unit", None),
    ("ls", "Learning Step", None),
    ("lp", "Learning Path", None),
]


# ============================================================================
# Shared helpers for domain-specific lateral routes
# ============================================================================


async def _create_relationship(
    request: Request,
    lateral_service: Any,
    uid: str,
    target_uid: str,
    relationship_type: RelationshipName,
    domain: str,
    metadata: dict[str, Any],
    message: str,
    response_extra: dict[str, Any],
    domain_service: Any | None = None,
) -> Result[dict[str, Any]]:
    """Create a domain-specific lateral relationship with auth and ownership."""
    user_uid = require_authenticated_user(request)
    full_metadata: dict[str, Any] = {**metadata, "domain": domain}

    create_kwargs: dict[str, Any] = {
        "source_uid": uid,
        "target_uid": target_uid,
        "relationship_type": relationship_type,
        "metadata": full_metadata,
    }
    if domain_service:
        full_metadata["created_by"] = user_uid
        create_kwargs["user_uid"] = user_uid
        create_kwargs["domain_service"] = domain_service

    result = await lateral_service.create_lateral_relationship(**create_kwargs)
    if result.is_error:
        return Result.fail(result)
    return Result.ok({"message": message, **response_extra})


async def _get_relationships(
    request: Request,
    lateral_service: Any,
    uid: str,
    relationship_type: RelationshipName,
    direction: str,
    response_key: str,
    domain_service: Any | None = None,
) -> Result[dict[str, Any]]:
    """Get domain-specific lateral relationships with auth and ownership."""
    user_uid = require_authenticated_user(request)

    get_kwargs: dict[str, Any] = {
        "entity_uid": uid,
        "relationship_types": [relationship_type],
        "direction": direction,
    }
    if domain_service:
        get_kwargs["user_uid"] = user_uid
        get_kwargs["domain_service"] = domain_service

    result = await lateral_service.get_lateral_relationships(**get_kwargs)
    if result.is_error:
        return Result.fail(result)
    return Result.ok({response_key: result.value, "count": len(result.value)})


# ============================================================================
# API Factory
# ============================================================================


def create_lateral_api_routes(
    app: FastHTMLApp, rt: RouteDecorator, lateral_service: Any, **kwargs: Any
) -> RouteList:
    """Register lateral relationship routes for all 9 domains."""
    all_routes: RouteList = []

    # Resolve domain services from kwargs
    domain_services: dict[str, Any] = {
        attr: kwargs.get(attr) for _, _, attr in _LATERAL_DOMAINS if attr
    }

    # Register standard lateral routes for all 9 domains
    for domain, entity_name, service_attr in _LATERAL_DOMAINS:
        domain_service = domain_services.get(service_attr) if service_attr else None
        factory = LateralRouteFactory(
            domain=domain,
            lateral_service=lateral_service,
            entity_name=entity_name,
            domain_service=domain_service,
        )
        all_routes.extend(factory.register_routes(app, rt))

    logger.info("Standard lateral routes registered for all 9 domains")

    # ========================================================================
    # Domain-specific routes
    # ========================================================================

    habits_service = domain_services.get("habits")
    events_service = domain_services.get("events")
    choices_service = domain_services.get("choices")
    principles_service = domain_services.get("principles")

    # --- Habits: Stacking ---

    @rt("/api/habits/{uid}/lateral/stacks", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_habit_stack(
        request: Request,
        uid: str,
        target_uid: str,
        trigger: str = "after",
        strength: float = 0.8,
    ) -> Result[dict[str, Any]]:
        """Create STACKS_WITH relationship for habit chaining."""
        return await _create_relationship(
            request,
            lateral_service,
            uid,
            target_uid,
            RelationshipName.STACKS_WITH,
            "habits",
            {"trigger": trigger, "strength": strength},
            "Habit stacking relationship created",
            {"first_habit_uid": uid, "second_habit_uid": target_uid, "trigger": trigger},
            domain_service=habits_service,
        )

    @rt("/api/habits/{uid}/lateral/stack", methods=["GET"])
    @boundary_handler()
    async def get_habit_stack(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get all habits in the stacking chain."""
        return await _get_relationships(
            request,
            lateral_service,
            uid,
            RelationshipName.STACKS_WITH,
            "both",
            "stack",
            domain_service=habits_service,
        )

    all_routes.extend([create_habit_stack, get_habit_stack])

    # --- Events: Scheduling Conflicts ---

    @rt("/api/events/{uid}/lateral/conflicts", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_event_conflict(
        request: Request,
        uid: str,
        target_uid: str,
        conflict_type: str,
        severity: str = "hard",
    ) -> Result[dict[str, Any]]:
        """Create CONFLICTS_WITH relationship for scheduling conflicts."""
        return await _create_relationship(
            request,
            lateral_service,
            uid,
            target_uid,
            RelationshipName.CONFLICTS_WITH,
            "events",
            {"conflict_type": conflict_type, "severity": severity},
            "Event conflict relationship created",
            {"event_a_uid": uid, "event_b_uid": target_uid, "conflict_type": conflict_type},
            domain_service=events_service,
        )

    @rt("/api/events/{uid}/lateral/conflicts", methods=["GET"])
    @boundary_handler()
    async def get_event_conflicts(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get events that conflict with this event."""
        return await _get_relationships(
            request,
            lateral_service,
            uid,
            RelationshipName.CONFLICTS_WITH,
            "both",
            "conflicts",
            domain_service=events_service,
        )

    all_routes.extend([create_event_conflict, get_event_conflicts])

    # --- Choices: Value Conflicts ---

    @rt("/api/choices/{uid}/lateral/conflicts", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_choice_conflict(
        request: Request,
        uid: str,
        target_uid: str,
        conflict_type: str,
        severity: str = "moderate",
    ) -> Result[dict[str, Any]]:
        """Create CONFLICTS_WITH relationship for incompatible choices."""
        return await _create_relationship(
            request,
            lateral_service,
            uid,
            target_uid,
            RelationshipName.CONFLICTS_WITH,
            "choices",
            {"conflict_type": conflict_type, "severity": severity},
            "Choice conflict relationship created",
            {"choice_a_uid": uid, "choice_b_uid": target_uid, "conflict_type": conflict_type},
            domain_service=choices_service,
        )

    @rt("/api/choices/{uid}/lateral/conflicts", methods=["GET"])
    @boundary_handler()
    async def get_choice_conflicts(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get choices that conflict with this choice."""
        return await _get_relationships(
            request,
            lateral_service,
            uid,
            RelationshipName.CONFLICTS_WITH,
            "both",
            "conflicts",
            domain_service=choices_service,
        )

    all_routes.extend([create_choice_conflict, get_choice_conflicts])

    # --- Principles: Value Tensions ---

    @rt("/api/principles/{uid}/lateral/conflicts", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_principle_conflict(
        request: Request,
        uid: str,
        target_uid: str,
        conflict_type: str,
        tension_description: str,
        severity: str = "moderate",
    ) -> Result[dict[str, Any]]:
        """Create CONFLICTS_WITH relationship for contradictory principles."""
        return await _create_relationship(
            request,
            lateral_service,
            uid,
            target_uid,
            RelationshipName.CONFLICTS_WITH,
            "principles",
            {
                "conflict_type": conflict_type,
                "tension_description": tension_description,
                "severity": severity,
            },
            "Principle conflict relationship created",
            {"principle_a_uid": uid, "principle_b_uid": target_uid, "conflict_type": conflict_type},
            domain_service=principles_service,
        )

    @rt("/api/principles/{uid}/lateral/conflicts", methods=["GET"])
    @boundary_handler()
    async def get_principle_conflicts(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get principles that conflict with this principle (value tensions)."""
        return await _get_relationships(
            request,
            lateral_service,
            uid,
            RelationshipName.CONFLICTS_WITH,
            "both",
            "conflicts",
            domain_service=principles_service,
        )

    all_routes.extend([create_principle_conflict, get_principle_conflicts])

    # --- KU: ENABLES Relationships ---

    @rt("/api/lesson/{uid}/lateral/enables", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_entity_enables(
        request: Request,
        uid: str,
        target_uid: str,
        confidence: float = 0.8,
        topic_domain: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create LATERAL_ENABLES relationship (learning A unlocks B)."""
        return await _create_relationship(
            request,
            lateral_service,
            uid,
            target_uid,
            RelationshipName.LATERAL_ENABLES,
            "ku",
            {"confidence": confidence, "topic_domain": topic_domain},
            "KU enables relationship created",
            {"enabler_uid": uid, "enabled_uid": target_uid},
        )

    @rt("/api/lesson/{uid}/lateral/enables", methods=["GET"])
    @boundary_handler()
    async def get_entity_enables(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get knowledge units that this KU enables."""
        return await _get_relationships(
            request,
            lateral_service,
            uid,
            RelationshipName.LATERAL_ENABLES,
            "outgoing",
            "enables",
        )

    @rt("/api/lesson/{uid}/lateral/enabled-by", methods=["GET"])
    @boundary_handler()
    async def get_entity_enabled_by(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get knowledge units that enable this KU."""
        return await _get_relationships(
            request,
            lateral_service,
            uid,
            RelationshipName.LATERAL_ENABLED_BY,
            "incoming",
            "enabled_by",
        )

    all_routes.extend([create_entity_enables, get_entity_enables, get_entity_enabled_by])

    logger.info(f"Lateral relationship routes registered: {len(all_routes)} total routes")
    return all_routes


# ============================================================================
# DomainRouteConfig wiring
# ============================================================================

LATERAL_CONFIG = DomainRouteConfig(
    domain_name="lateral",
    primary_service_attr="lateral",
    api_factory=create_lateral_api_routes,
    api_related_services={
        "tasks": "tasks",
        "goals": "goals",
        "habits": "habits",
        "events": "events",
        "choices": "choices",
        "principles": "principles",
    },
)


def create_lateral_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> RouteList:
    """Wire lateral relationship routes via DomainRouteConfig."""
    return register_domain_routes(app, rt, services, LATERAL_CONFIG)


__all__ = ["create_lateral_routes"]
