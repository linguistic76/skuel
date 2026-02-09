"""
Lateral Relationship Routes - API Endpoints for All Domains
============================================================

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

from core.auth import require_authenticated_user
from core.infrastructure.routes.lateral_route_factory import LateralRouteFactory
from core.models.relationship_names import RelationshipName
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


def create_lateral_routes(app: Any, rt: Any, services: Any) -> list[Any]:
    """
    Register lateral relationship routes for all 9 domains.

    Uses one core LateralRelationshipService with domain_service for ownership.
    """
    all_routes = []
    lateral = services.lateral  # Core LateralRelationshipService

    # ========================================================================
    # ACTIVITY DOMAINS (6) — pass domain_service for ownership verification
    # ========================================================================

    # Tasks lateral routes
    tasks_factory = LateralRouteFactory(
        domain="tasks",
        lateral_service=lateral,
        entity_name="Task",
        domain_service=services.tasks,
    )
    all_routes.extend(tasks_factory.register_routes(app, rt))
    logger.info("✅ Tasks lateral routes registered")

    # Goals lateral routes
    goals_factory = LateralRouteFactory(
        domain="goals",
        lateral_service=lateral,
        entity_name="Goal",
        domain_service=services.goals,
    )
    all_routes.extend(goals_factory.register_routes(app, rt))
    logger.info("✅ Goals lateral routes registered")

    # Habits lateral routes
    habits_factory = LateralRouteFactory(
        domain="habits",
        lateral_service=lateral,
        entity_name="Habit",
        domain_service=services.habits,
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

        result = await lateral.create_lateral_relationship(
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
            domain_service=services.habits,
        )

        if result.is_error:
            return result

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

        result = await lateral.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.STACKS_WITH],
            direction="both",
            user_uid=user_uid,
            domain_service=services.habits,
        )

        if result.is_error:
            return result

        return Result.ok(
            {
                "stack": result.value,
                "count": len(result.value),
            }
        )

    all_routes.extend([create_habit_stack, get_habit_stack])
    logger.info("✅ Habits lateral routes registered (including habit stacking)")

    # Events lateral routes
    events_factory = LateralRouteFactory(
        domain="events",
        lateral_service=lateral,
        entity_name="Event",
        domain_service=services.events,
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

        result = await lateral.create_lateral_relationship(
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
            domain_service=services.events,
        )

        if result.is_error:
            return result

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

        result = await lateral.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.CONFLICTS_WITH],
            direction="both",
            user_uid=user_uid,
            domain_service=services.events,
        )

        if result.is_error:
            return result

        return Result.ok(
            {
                "conflicts": result.value,
                "count": len(result.value),
            }
        )

    all_routes.extend([create_event_conflict, get_event_conflicts])
    logger.info("✅ Events lateral routes registered (including scheduling conflicts)")

    # Choices lateral routes
    choices_factory = LateralRouteFactory(
        domain="choices",
        lateral_service=lateral,
        entity_name="Choice",
        domain_service=services.choices,
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

        result = await lateral.create_lateral_relationship(
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
            domain_service=services.choices,
        )

        if result.is_error:
            return result

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

        result = await lateral.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.CONFLICTS_WITH],
            direction="both",
            user_uid=user_uid,
            domain_service=services.choices,
        )

        if result.is_error:
            return result

        return Result.ok(
            {
                "conflicts": result.value,
                "count": len(result.value),
            }
        )

    all_routes.extend([create_choice_conflict, get_choice_conflicts])
    logger.info("✅ Choices lateral routes registered (including value conflicts)")

    # Principles lateral routes
    principles_factory = LateralRouteFactory(
        domain="principles",
        lateral_service=lateral,
        entity_name="Principle",
        domain_service=services.principles,
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

        result = await lateral.create_lateral_relationship(
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
            domain_service=services.principles,
        )

        if result.is_error:
            return result

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

        result = await lateral.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.CONFLICTS_WITH],
            direction="both",
            user_uid=user_uid,
            domain_service=services.principles,
        )

        if result.is_error:
            return result

        return Result.ok(
            {
                "conflicts": result.value,
                "count": len(result.value),
            }
        )

    all_routes.extend([create_principle_conflict, get_principle_conflicts])
    logger.info("✅ Principles lateral routes registered (including value tensions)")

    # ========================================================================
    # CURRICULUM DOMAINS (3) — no ownership (shared content)
    # ========================================================================

    # KU lateral routes
    ku_factory = LateralRouteFactory(
        domain="ku",
        lateral_service=lateral,
        entity_name="Knowledge Unit",
    )
    all_routes.extend(ku_factory.register_routes(app, rt))

    # KU-specific: ENABLES relationship
    @rt("/api/ku/{uid}/lateral/enables", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_ku_enables(
        request: Request,
        uid: str,
        target_uid: str,
        confidence: float = 0.8,
        topic_domain: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create LATERAL_ENABLES relationship (learning A unlocks B)."""
        require_authenticated_user(request)

        result = await lateral.create_lateral_relationship(
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
            return result

        return Result.ok(
            {
                "message": "KU enables relationship created",
                "enabler_uid": uid,
                "enabled_uid": target_uid,
            }
        )

    @rt("/api/ku/{uid}/lateral/enables", methods=["GET"])
    @boundary_handler()
    async def get_ku_enables(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get knowledge units that this KU enables."""
        require_authenticated_user(request)

        result = await lateral.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.LATERAL_ENABLES],
            direction="outgoing",
        )

        if result.is_error:
            return result

        return Result.ok(
            {
                "enables": result.value,
                "count": len(result.value),
            }
        )

    @rt("/api/ku/{uid}/lateral/enabled-by", methods=["GET"])
    @boundary_handler()
    async def get_ku_enabled_by(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get knowledge units that enable this KU."""
        require_authenticated_user(request)

        result = await lateral.get_lateral_relationships(
            entity_uid=uid,
            relationship_types=[RelationshipName.LATERAL_ENABLED_BY],
            direction="incoming",
        )

        if result.is_error:
            return result

        return Result.ok(
            {
                "enabled_by": result.value,
                "count": len(result.value),
            }
        )

    all_routes.extend([create_ku_enables, get_ku_enables, get_ku_enabled_by])
    logger.info("✅ KU lateral routes registered (including ENABLES relationships)")

    # LS lateral routes
    ls_factory = LateralRouteFactory(
        domain="ls",
        lateral_service=lateral,
        entity_name="Learning Step",
    )
    all_routes.extend(ls_factory.register_routes(app, rt))
    logger.info("✅ LS lateral routes registered")

    # LP lateral routes
    lp_factory = LateralRouteFactory(
        domain="lp",
        lateral_service=lateral,
        entity_name="Learning Path",
    )
    all_routes.extend(lp_factory.register_routes(app, rt))
    logger.info("✅ LP lateral routes registered")

    logger.info(f"✅ Lateral relationship routes registered: {len(all_routes)} total routes")
    logger.info(
        "   Activity Domains: Tasks, Goals, Habits, Events, Choices, Principles (6 domains)"
    )
    logger.info("   Curriculum Domains: KU, LS, LP (3 domains)")

    return all_routes


__all__ = ["create_lateral_routes"]
