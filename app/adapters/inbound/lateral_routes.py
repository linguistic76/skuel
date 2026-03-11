"""
Lateral Relationship Routes — Configuration-Driven Registration
================================================================

Registers lateral relationship routes for all 9 hierarchical domains:
- Activity Domains (6): Tasks, Goals, Habits, Events, Choices, Principles
- Curriculum Domains (3): KU, LS, LP

Each domain gets a full set of lateral relationship endpoints via LateralRouteFactory.
Domain-specific routes (habit stacking, event conflicts, KU enables) are registered
separately using the core LateralRelationshipService directly.

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


def create_lateral_api_routes(
    app: FastHTMLApp, rt: RouteDecorator, lateral_service: Any, **kwargs: Any
) -> RouteList:
    """
    Register lateral relationship routes for all 9 domains.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        lateral_service: Core LateralRelationshipService
        **kwargs: Domain services (tasks, goals, habits, events, choices, principles)
    """
    all_routes: RouteList = []

    tasks_service = kwargs.get("tasks")
    goals_service = kwargs.get("goals")
    habits_service = kwargs.get("habits")
    events_service = kwargs.get("events")
    choices_service = kwargs.get("choices")
    principles_service = kwargs.get("principles")

    # ========================================================================
    # ACTIVITY DOMAINS (6) — pass domain_service for ownership verification
    # ========================================================================

    # Tasks lateral routes
    tasks_factory = LateralRouteFactory(
        domain="tasks",
        lateral_service=lateral_service,
        entity_name="Task",
        domain_service=tasks_service,
    )
    all_routes.extend(tasks_factory.register_routes(app, rt))
    logger.info("Tasks lateral routes registered")

    # Goals lateral routes
    goals_factory = LateralRouteFactory(
        domain="goals",
        lateral_service=lateral_service,
        entity_name="Goal",
        domain_service=goals_service,
    )
    all_routes.extend(goals_factory.register_routes(app, rt))
    logger.info("Goals lateral routes registered")

    # Habits lateral routes
    habits_factory = LateralRouteFactory(
        domain="habits",
        lateral_service=lateral_service,
        entity_name="Habit",
        domain_service=habits_service,
    )
    all_routes.extend(habits_factory.register_routes(app, rt))

    # Habits-specific: Habit stacking
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
        user_uid = require_authenticated_user(request)

        result = await lateral_service.create_lateral_relationship(
            source_uid=uid,
            target_uid=target_uid,
            relationship_type=RelationshipName.STACKS_WITH,
            metadata={
                "trigger": trigger,
                "strength": strength,
                "domain": "habits",
                "created_by": user_uid,
            },
            user_uid=user_uid,
            domain_service=habits_service,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "message": "Habit stacking relationship created",
                "first_habit_uid": uid,
                "second_habit_uid": target_uid,
                "trigger": trigger,
            }
        )

    @rt("/api/habits/{uid}/lateral/stack", methods=["GET"])
    @boundary_handler()
    async def get_habit_stack(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get all habits in the stacking chain."""
        user_uid = require_authenticated_user(request)

        result = await lateral_service.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.STACKS_WITH],
            direction="both",
            user_uid=user_uid,
            domain_service=habits_service,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "stack": result.value,
                "count": len(result.value),
            }
        )

    all_routes.extend([create_habit_stack, get_habit_stack])
    logger.info("Habits lateral routes registered (including habit stacking)")

    # Events lateral routes
    events_factory = LateralRouteFactory(
        domain="events",
        lateral_service=lateral_service,
        entity_name="Event",
        domain_service=events_service,
    )
    all_routes.extend(events_factory.register_routes(app, rt))

    # Events-specific: Scheduling conflicts
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
        user_uid = require_authenticated_user(request)

        result = await lateral_service.create_lateral_relationship(
            source_uid=uid,
            target_uid=target_uid,
            relationship_type=RelationshipName.CONFLICTS_WITH,
            metadata={
                "conflict_type": conflict_type,
                "severity": severity,
                "domain": "events",
                "created_by": user_uid,
            },
            user_uid=user_uid,
            domain_service=events_service,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "message": "Event conflict relationship created",
                "event_a_uid": uid,
                "event_b_uid": target_uid,
                "conflict_type": conflict_type,
            }
        )

    @rt("/api/events/{uid}/lateral/conflicts", methods=["GET"])
    @boundary_handler()
    async def get_event_conflicts(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get events that conflict with this event."""
        user_uid = require_authenticated_user(request)

        result = await lateral_service.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.CONFLICTS_WITH],
            direction="both",
            user_uid=user_uid,
            domain_service=events_service,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "conflicts": result.value,
                "count": len(result.value),
            }
        )

    all_routes.extend([create_event_conflict, get_event_conflicts])
    logger.info("Events lateral routes registered (including scheduling conflicts)")

    # Choices lateral routes
    choices_factory = LateralRouteFactory(
        domain="choices",
        lateral_service=lateral_service,
        entity_name="Choice",
        domain_service=choices_service,
    )
    all_routes.extend(choices_factory.register_routes(app, rt))

    # Choices-specific: Value conflicts
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
        user_uid = require_authenticated_user(request)

        result = await lateral_service.create_lateral_relationship(
            source_uid=uid,
            target_uid=target_uid,
            relationship_type=RelationshipName.CONFLICTS_WITH,
            metadata={
                "conflict_type": conflict_type,
                "severity": severity,
                "domain": "choices",
                "created_by": user_uid,
            },
            user_uid=user_uid,
            domain_service=choices_service,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "message": "Choice conflict relationship created",
                "choice_a_uid": uid,
                "choice_b_uid": target_uid,
                "conflict_type": conflict_type,
            }
        )

    @rt("/api/choices/{uid}/lateral/conflicts", methods=["GET"])
    @boundary_handler()
    async def get_choice_conflicts(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get choices that conflict with this choice."""
        user_uid = require_authenticated_user(request)

        result = await lateral_service.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.CONFLICTS_WITH],
            direction="both",
            user_uid=user_uid,
            domain_service=choices_service,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "conflicts": result.value,
                "count": len(result.value),
            }
        )

    all_routes.extend([create_choice_conflict, get_choice_conflicts])
    logger.info("Choices lateral routes registered (including value conflicts)")

    # Principles lateral routes
    principles_factory = LateralRouteFactory(
        domain="principles",
        lateral_service=lateral_service,
        entity_name="Principle",
        domain_service=principles_service,
    )
    all_routes.extend(principles_factory.register_routes(app, rt))

    # Principles-specific: Value tensions
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
        user_uid = require_authenticated_user(request)

        result = await lateral_service.create_lateral_relationship(
            source_uid=uid,
            target_uid=target_uid,
            relationship_type=RelationshipName.CONFLICTS_WITH,
            metadata={
                "conflict_type": conflict_type,
                "tension_description": tension_description,
                "severity": severity,
                "domain": "principles",
                "created_by": user_uid,
            },
            user_uid=user_uid,
            domain_service=principles_service,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "message": "Principle conflict relationship created",
                "principle_a_uid": uid,
                "principle_b_uid": target_uid,
                "conflict_type": conflict_type,
            }
        )

    @rt("/api/principles/{uid}/lateral/conflicts", methods=["GET"])
    @boundary_handler()
    async def get_principle_conflicts(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get principles that conflict with this principle (value tensions)."""
        user_uid = require_authenticated_user(request)

        result = await lateral_service.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.CONFLICTS_WITH],
            direction="both",
            user_uid=user_uid,
            domain_service=principles_service,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "conflicts": result.value,
                "count": len(result.value),
            }
        )

    all_routes.extend([create_principle_conflict, get_principle_conflicts])
    logger.info("Principles lateral routes registered (including value tensions)")

    # ========================================================================
    # CURRICULUM DOMAINS (3) — no ownership (shared content)
    # ========================================================================

    # KU lateral routes
    ku_factory = LateralRouteFactory(
        domain="ku",
        lateral_service=lateral_service,
        entity_name="Knowledge Unit",
    )
    all_routes.extend(ku_factory.register_routes(app, rt))

    # KU-specific: ENABLES relationship
    @rt("/api/article/{uid}/lateral/enables", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_entity_enables(
        request: Request,
        uid: str,
        target_uid: str,
        confidence: float = 0.8,
        topic_domain: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create LATERAL_ENABLES relationship (learning A unlocks B)."""
        require_authenticated_user(request)

        result = await lateral_service.create_lateral_relationship(
            source_uid=uid,
            target_uid=target_uid,
            relationship_type=RelationshipName.LATERAL_ENABLES,
            metadata={
                "confidence": confidence,
                "topic_domain": topic_domain,
                "domain": "ku",
            },
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "message": "KU enables relationship created",
                "enabler_uid": uid,
                "enabled_uid": target_uid,
            }
        )

    @rt("/api/article/{uid}/lateral/enables", methods=["GET"])
    @boundary_handler()
    async def get_entity_enables(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get knowledge units that this KU enables."""
        require_authenticated_user(request)

        result = await lateral_service.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.LATERAL_ENABLES],
            direction="outgoing",
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "enables": result.value,
                "count": len(result.value),
            }
        )

    @rt("/api/article/{uid}/lateral/enabled-by", methods=["GET"])
    @boundary_handler()
    async def get_entity_enabled_by(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get knowledge units that enable this KU."""
        require_authenticated_user(request)

        result = await lateral_service.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.LATERAL_ENABLED_BY],
            direction="incoming",
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "enabled_by": result.value,
                "count": len(result.value),
            }
        )

    all_routes.extend([create_entity_enables, get_entity_enables, get_entity_enabled_by])
    logger.info("KU lateral routes registered (including ENABLES relationships)")

    # LS lateral routes
    ls_factory = LateralRouteFactory(
        domain="ls",
        lateral_service=lateral_service,
        entity_name="Learning Step",
    )
    all_routes.extend(ls_factory.register_routes(app, rt))
    logger.info("LS lateral routes registered")

    # LP lateral routes
    lp_factory = LateralRouteFactory(
        domain="lp",
        lateral_service=lateral_service,
        entity_name="Learning Path",
    )
    all_routes.extend(lp_factory.register_routes(app, rt))
    logger.info("LP lateral routes registered")

    logger.info(f"Lateral relationship routes registered: {len(all_routes)} total routes")

    return all_routes


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
