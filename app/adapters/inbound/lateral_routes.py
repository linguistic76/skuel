"""
Lateral Relationship Routes — Configuration-Driven Registration
================================================================

Registers lateral relationship routes for all 9 hierarchical domains:
- Activity Domains (6): Tasks, Goals, Habits, Events, Choices, Principles
- Curriculum Domains (3): KU, PS, LP

Each domain gets a full set of lateral relationship endpoints via LateralRouteFactory.
Domain-specific routes (habit stacking, event conflicts, KU enables) delegate to
LateralRelationshipsOrchestrator, which holds all required services.

See: /docs/architecture/RELATIONSHIPS_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories.lateral_route_factory import LateralRouteFactory
from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.orchestrator.lateral_relationships_orchestrator import (
        LateralRelationshipsOrchestrator,
    )

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
    ("ps", "Path Step", None),
    ("lp", "Learning Path", None),
]


# ============================================================================
# API Factory
# ============================================================================


def create_lateral_api_routes(
    app: FastHTMLApp, rt: RouteDecorator, orchestrator: "LateralRelationshipsOrchestrator"
) -> list[Any]:
    """Register lateral relationship routes for all 9 domains."""
    all_routes: list[Any] = []

    # Register standard lateral routes for all 9 domains
    for domain, entity_name, service_attr in _LATERAL_DOMAINS:
        domain_service = orchestrator.get_domain_service(service_attr) if service_attr else None
        factory = LateralRouteFactory(
            domain=domain,
            lateral_service=orchestrator.lateral_service,
            entity_name=entity_name,
            domain_service=domain_service,
        )
        all_routes.extend(factory.register_routes(app, rt))

    logger.info("Standard lateral routes registered for all 9 domains")

    # ========================================================================
    # Domain-specific routes
    # ========================================================================

    # --- Habits: Stacking ---

    @rt("/api/habits/{uid}/lateral/stacks", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=201)
    async def create_habit_stack(
        request: Request,
        uid: str,
        target_uid: str,
        trigger: str = "after",
        strength: float = 0.8,
    ) -> Result[dict[str, Any]]:
        """Create STACKS_WITH relationship for habit chaining."""
        user_uid = require_authenticated_user(request)
        return await orchestrator.create_relationship(
            user_uid=user_uid,
            uid=uid,
            target_uid=target_uid,
            relationship_type=RelationshipName.STACKS_WITH,
            domain="habits",
            metadata={"trigger": trigger, "strength": strength},
            message="Habit stacking relationship created",
            response_extra={
                "first_habit_uid": uid,
                "second_habit_uid": target_uid,
                "trigger": trigger,
            },
            domain_service=orchestrator.get_domain_service("habits"),
        )

    @rt("/api/habits/{uid}/lateral/stack", methods=["GET"])
    @boundary_handler()
    async def get_habit_stack(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get all habits in the stacking chain."""
        user_uid = require_authenticated_user(request)
        return await orchestrator.get_relationships(
            user_uid=user_uid,
            uid=uid,
            relationship_type=RelationshipName.STACKS_WITH,
            direction="both",
            response_key="stack",
            domain_service=orchestrator.get_domain_service("habits"),
        )

    all_routes.extend([create_habit_stack, get_habit_stack])

    # --- Events: Scheduling Conflicts ---

    @rt("/api/events/{uid}/lateral/conflicts", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=201)
    async def create_event_conflict(
        request: Request,
        uid: str,
        target_uid: str,
        conflict_type: str,
        severity: str = "hard",
    ) -> Result[dict[str, Any]]:
        """Create CONFLICTS_WITH relationship for scheduling conflicts."""
        user_uid = require_authenticated_user(request)
        return await orchestrator.create_relationship(
            user_uid=user_uid,
            uid=uid,
            target_uid=target_uid,
            relationship_type=RelationshipName.CONFLICTS_WITH,
            domain="events",
            metadata={"conflict_type": conflict_type, "severity": severity},
            message="Event conflict relationship created",
            response_extra={
                "event_a_uid": uid,
                "event_b_uid": target_uid,
                "conflict_type": conflict_type,
            },
            domain_service=orchestrator.get_domain_service("events"),
        )

    @rt("/api/events/{uid}/lateral/conflicts", methods=["GET"])
    @boundary_handler()
    async def get_event_conflicts(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get events that conflict with this event."""
        user_uid = require_authenticated_user(request)
        return await orchestrator.get_relationships(
            user_uid=user_uid,
            uid=uid,
            relationship_type=RelationshipName.CONFLICTS_WITH,
            direction="both",
            response_key="conflicts",
            domain_service=orchestrator.get_domain_service("events"),
        )

    all_routes.extend([create_event_conflict, get_event_conflicts])

    # --- Choices: Value Conflicts ---

    @rt("/api/choices/{uid}/lateral/conflicts", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=201)
    async def create_choice_conflict(
        request: Request,
        uid: str,
        target_uid: str,
        conflict_type: str,
        severity: str = "moderate",
    ) -> Result[dict[str, Any]]:
        """Create CONFLICTS_WITH relationship for incompatible choices."""
        user_uid = require_authenticated_user(request)
        return await orchestrator.create_relationship(
            user_uid=user_uid,
            uid=uid,
            target_uid=target_uid,
            relationship_type=RelationshipName.CONFLICTS_WITH,
            domain="choices",
            metadata={"conflict_type": conflict_type, "severity": severity},
            message="Choice conflict relationship created",
            response_extra={
                "choice_a_uid": uid,
                "choice_b_uid": target_uid,
                "conflict_type": conflict_type,
            },
            domain_service=orchestrator.get_domain_service("choices"),
        )

    @rt("/api/choices/{uid}/lateral/conflicts", methods=["GET"])
    @boundary_handler()
    async def get_choice_conflicts(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get choices that conflict with this choice."""
        user_uid = require_authenticated_user(request)
        return await orchestrator.get_relationships(
            user_uid=user_uid,
            uid=uid,
            relationship_type=RelationshipName.CONFLICTS_WITH,
            direction="both",
            response_key="conflicts",
            domain_service=orchestrator.get_domain_service("choices"),
        )

    all_routes.extend([create_choice_conflict, get_choice_conflicts])

    # --- Principles: Value Tensions ---

    @rt("/api/principles/{uid}/lateral/conflicts", methods=["POST"])
    @csrf_protected
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
        user_uid = require_authenticated_user(request)
        return await orchestrator.create_relationship(
            user_uid=user_uid,
            uid=uid,
            target_uid=target_uid,
            relationship_type=RelationshipName.CONFLICTS_WITH,
            domain="principles",
            metadata={
                "conflict_type": conflict_type,
                "tension_description": tension_description,
                "severity": severity,
            },
            message="Principle conflict relationship created",
            response_extra={
                "principle_a_uid": uid,
                "principle_b_uid": target_uid,
                "conflict_type": conflict_type,
            },
            domain_service=orchestrator.get_domain_service("principles"),
        )

    @rt("/api/principles/{uid}/lateral/conflicts", methods=["GET"])
    @boundary_handler()
    async def get_principle_conflicts(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get principles that conflict with this principle (value tensions)."""
        user_uid = require_authenticated_user(request)
        return await orchestrator.get_relationships(
            user_uid=user_uid,
            uid=uid,
            relationship_type=RelationshipName.CONFLICTS_WITH,
            direction="both",
            response_key="conflicts",
            domain_service=orchestrator.get_domain_service("principles"),
        )

    all_routes.extend([create_principle_conflict, get_principle_conflicts])

    # --- KU: ENABLES Relationships ---

    @rt("/api/ku/{uid}/lateral/enables", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=201)
    async def create_entity_enables(
        request: Request,
        uid: str,
        target_uid: str,
        confidence: float = 0.8,
        topic_domain: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create LATERAL_ENABLES relationship (learning A unlocks B)."""
        user_uid = require_authenticated_user(request)
        return await orchestrator.create_relationship(
            user_uid=user_uid,
            uid=uid,
            target_uid=target_uid,
            relationship_type=RelationshipName.LATERAL_ENABLES,
            domain="ku",
            metadata={"confidence": confidence, "topic_domain": topic_domain},
            message="KU enables relationship created",
            response_extra={"enabler_uid": uid, "enabled_uid": target_uid},
        )

    @rt("/api/ku/{uid}/lateral/enables", methods=["GET"])
    @boundary_handler()
    async def get_entity_enables(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get knowledge units that this KU enables."""
        user_uid = require_authenticated_user(request)
        return await orchestrator.get_relationships(
            user_uid=user_uid,
            uid=uid,
            relationship_type=RelationshipName.LATERAL_ENABLES,
            direction="outgoing",
            response_key="enables",
        )

    @rt("/api/ku/{uid}/lateral/enabled-by", methods=["GET"])
    @boundary_handler()
    async def get_entity_enabled_by(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get knowledge units that enable this KU."""
        user_uid = require_authenticated_user(request)
        return await orchestrator.get_relationships(
            user_uid=user_uid,
            uid=uid,
            relationship_type=RelationshipName.LATERAL_ENABLED_BY,
            direction="incoming",
            response_key="enabled_by",
        )

    all_routes.extend([create_entity_enables, get_entity_enables, get_entity_enabled_by])

    logger.info(f"Lateral relationship routes registered: {len(all_routes)} total routes")
    return all_routes


# ============================================================================
# Route registration
# ============================================================================


def create_lateral_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> None:
    """Wire lateral relationship routes via LateralRelationshipsOrchestrator."""
    if not services or not services.lateral_orchestrator:
        logger.warning("LateralRelationshipsOrchestrator not available — lateral routes skipped")
        return
    create_lateral_api_routes(app, rt, orchestrator=services.lateral_orchestrator)


__all__ = ["create_lateral_routes"]
