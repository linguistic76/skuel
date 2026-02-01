"""
Lateral Relationship Routes - API Endpoints for All Domains
============================================================

Registers lateral relationship routes for all 8 hierarchical domains:
- Activity Domains (6): Tasks, Goals, Habits, Events, Choices, Principles
- Curriculum Domains (3): KU, LS, LP

Each domain gets a full set of lateral relationship endpoints:
- POST /api/{domain}/{uid}/lateral/blocks - Create blocking
- GET /api/{domain}/{uid}/lateral/blocking - Get blocking relationships
- POST /api/{domain}/{uid}/lateral/prerequisites - Create prerequisite
- GET /api/{domain}/{uid}/lateral/prerequisites - Get prerequisites
- POST /api/{domain}/{uid}/lateral/alternatives - Create alternative
- GET /api/{domain}/{uid}/lateral/alternatives - Get alternatives
- POST /api/{domain}/{uid}/lateral/complementary - Create complementary
- GET /api/{domain}/{uid}/lateral/complementary - Get complementary
- GET /api/{domain}/{uid}/lateral/siblings - Get siblings (derived)
- DELETE /api/{domain}/{uid}/lateral/{type}/{target_uid} - Delete relationship

Domain-specific routes are added separately for unique relationship types.

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from fasthtml.common import Request

from core.auth import require_authenticated_user
from core.infrastructure.routes.lateral_route_factory import LateralRouteFactory
from core.utils.logging import get_logger

logger = get_logger(__name__)


def create_lateral_routes(app: Any, rt: Any, services: Any) -> list[Any]:
    """
    Register lateral relationship routes for all 8 domains.

    Args:
        app: FastHTML app
        rt: Route decorator
        services: Services container with lateral services

    Returns:
        List of all registered routes
    """
    all_routes = []

    # ========================================================================
    # ACTIVITY DOMAINS (6)
    # ========================================================================

    # Tasks lateral routes
    tasks_factory = LateralRouteFactory(
        app=app,
        rt=rt,
        domain="tasks",
        lateral_service=services.tasks_lateral,
        entity_name="Task",
    )
    all_routes.extend(tasks_factory.create_routes())
    logger.info("✅ Tasks lateral routes registered")

    # Goals lateral routes
    goals_factory = LateralRouteFactory(
        app=app,
        rt=rt,
        domain="goals",
        lateral_service=services.goals_lateral,
        entity_name="Goal",
    )
    all_routes.extend(goals_factory.create_routes())
    logger.info("✅ Goals lateral routes registered")

    # Habits lateral routes
    habits_factory = LateralRouteFactory(
        app=app,
        rt=rt,
        domain="habits",
        lateral_service=services.habits_lateral,
        entity_name="Habit",
    )
    all_routes.extend(habits_factory.create_routes())

    # Habits-specific: Habit stacking
    @rt("/api/habits/{uid}/lateral/stacks", methods=["POST"])
    async def create_habit_stack(
        request: Request,
        uid: str,
        target_uid: str,
        trigger: str = "after",
        strength: float = 0.8,
    ) -> dict[str, Any]:
        """Create STACKS_WITH relationship for habit chaining."""
        user_uid = require_authenticated_user(request)

        result = await services.habits_lateral.create_stacking_relationship(
            first_habit_uid=uid,
            second_habit_uid=target_uid,
            trigger=trigger,
            strength=strength,
            user_uid=user_uid,
        )

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "message": "Habit stacking relationship created",
            "first_habit_uid": uid,
            "second_habit_uid": target_uid,
            "trigger": trigger,
        }

    @rt("/api/habits/{uid}/lateral/stack", methods=["GET"])
    async def get_habit_stack(request: Request, uid: str) -> dict[str, Any]:
        """Get all habits in the stacking chain."""
        user_uid = require_authenticated_user(request)

        result = await services.habits_lateral.get_habit_stack(uid, user_uid=user_uid)

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "stack": result.value,
            "count": len(result.value),
        }

    all_routes.extend([create_habit_stack, get_habit_stack])
    logger.info("✅ Habits lateral routes registered (including habit stacking)")

    # Events lateral routes
    events_factory = LateralRouteFactory(
        app=app,
        rt=rt,
        domain="events",
        lateral_service=services.events_lateral,
        entity_name="Event",
    )
    all_routes.extend(events_factory.create_routes())

    # Events-specific: Scheduling conflicts
    @rt("/api/events/{uid}/lateral/conflicts", methods=["POST"])
    async def create_event_conflict(
        request: Request,
        uid: str,
        target_uid: str,
        conflict_type: str,
        severity: str = "hard",
    ) -> dict[str, Any]:
        """Create CONFLICTS_WITH relationship for scheduling conflicts."""
        user_uid = require_authenticated_user(request)

        result = await services.events_lateral.create_conflict_relationship(
            event_a_uid=uid,
            event_b_uid=target_uid,
            conflict_type=conflict_type,
            severity=severity,
            user_uid=user_uid,
        )

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "message": "Event conflict relationship created",
            "event_a_uid": uid,
            "event_b_uid": target_uid,
            "conflict_type": conflict_type,
        }

    @rt("/api/events/{uid}/lateral/conflicts", methods=["GET"])
    async def get_event_conflicts(request: Request, uid: str) -> dict[str, Any]:
        """Get events that conflict with this event."""
        user_uid = require_authenticated_user(request)

        result = await services.events_lateral.get_conflicting_events(uid, user_uid=user_uid)

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "conflicts": result.value,
            "count": len(result.value),
        }

    all_routes.extend([create_event_conflict, get_event_conflicts])
    logger.info("✅ Events lateral routes registered (including scheduling conflicts)")

    # Choices lateral routes
    choices_factory = LateralRouteFactory(
        app=app,
        rt=rt,
        domain="choices",
        lateral_service=services.choices_lateral,
        entity_name="Choice",
    )
    all_routes.extend(choices_factory.create_routes())

    # Choices-specific: Value conflicts
    @rt("/api/choices/{uid}/lateral/conflicts", methods=["POST"])
    async def create_choice_conflict(
        request: Request,
        uid: str,
        target_uid: str,
        conflict_type: str,
        severity: str = "moderate",
    ) -> dict[str, Any]:
        """Create CONFLICTS_WITH relationship for incompatible choices."""
        user_uid = require_authenticated_user(request)

        result = await services.choices_lateral.create_conflict_relationship(
            choice_a_uid=uid,
            choice_b_uid=target_uid,
            conflict_type=conflict_type,
            severity=severity,
            user_uid=user_uid,
        )

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "message": "Choice conflict relationship created",
            "choice_a_uid": uid,
            "choice_b_uid": target_uid,
            "conflict_type": conflict_type,
        }

    @rt("/api/choices/{uid}/lateral/conflicts", methods=["GET"])
    async def get_choice_conflicts(request: Request, uid: str) -> dict[str, Any]:
        """Get choices that conflict with this choice."""
        user_uid = require_authenticated_user(request)

        result = await services.choices_lateral.get_conflicting_choices(uid, user_uid=user_uid)

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "conflicts": result.value,
            "count": len(result.value),
        }

    all_routes.extend([create_choice_conflict, get_choice_conflicts])
    logger.info("✅ Choices lateral routes registered (including value conflicts)")

    # Principles lateral routes
    principles_factory = LateralRouteFactory(
        app=app,
        rt=rt,
        domain="principles",
        lateral_service=services.principles_lateral,
        entity_name="Principle",
    )
    all_routes.extend(principles_factory.create_routes())

    # Principles-specific: Value tensions
    @rt("/api/principles/{uid}/lateral/conflicts", methods=["POST"])
    async def create_principle_conflict(
        request: Request,
        uid: str,
        target_uid: str,
        conflict_type: str,
        tension_description: str,
        severity: str = "moderate",
    ) -> dict[str, Any]:
        """Create CONFLICTS_WITH relationship for contradictory principles."""
        user_uid = require_authenticated_user(request)

        result = await services.principles_lateral.create_conflict_relationship(
            principle_a_uid=uid,
            principle_b_uid=target_uid,
            conflict_type=conflict_type,
            tension_description=tension_description,
            severity=severity,
            user_uid=user_uid,
        )

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "message": "Principle conflict relationship created",
            "principle_a_uid": uid,
            "principle_b_uid": target_uid,
            "conflict_type": conflict_type,
        }

    @rt("/api/principles/{uid}/lateral/conflicts", methods=["GET"])
    async def get_principle_conflicts(request: Request, uid: str) -> dict[str, Any]:
        """Get principles that conflict with this principle (value tensions)."""
        user_uid = require_authenticated_user(request)

        result = await services.principles_lateral.get_conflicting_principles(
            uid, user_uid=user_uid
        )

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "conflicts": result.value,
            "count": len(result.value),
        }

    all_routes.extend([create_principle_conflict, get_principle_conflicts])
    logger.info("✅ Principles lateral routes registered (including value tensions)")

    # ========================================================================
    # CURRICULUM DOMAINS (3)
    # ========================================================================

    # KU lateral routes
    ku_factory = LateralRouteFactory(
        app=app,
        rt=rt,
        domain="ku",
        lateral_service=services.ku_lateral,
        entity_name="Knowledge Unit",
    )
    all_routes.extend(ku_factory.create_routes())

    # KU-specific: ENABLES relationship
    @rt("/api/ku/{uid}/lateral/enables", methods=["POST"])
    async def create_ku_enables(
        request: Request,
        uid: str,
        target_uid: str,
        confidence: float = 0.8,
        topic_domain: str | None = None,
    ) -> dict[str, Any]:
        """Create ENABLES relationship (learning A unlocks B)."""
        require_authenticated_user(request)

        result = await services.ku_lateral.create_enables_relationship(
            enabler_uid=uid,
            enabled_uid=target_uid,
            confidence=confidence,
            topic_domain=topic_domain,
        )

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "message": "KU enables relationship created",
            "enabler_uid": uid,
            "enabled_uid": target_uid,
        }

    @rt("/api/ku/{uid}/lateral/enables", methods=["GET"])
    async def get_ku_enables(request: Request, uid: str) -> dict[str, Any]:
        """Get knowledge units that this KU enables."""
        require_authenticated_user(request)

        result = await services.ku_lateral.get_enables(uid)

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "enables": result.value,
            "count": len(result.value),
        }

    @rt("/api/ku/{uid}/lateral/enabled-by", methods=["GET"])
    async def get_ku_enabled_by(request: Request, uid: str) -> dict[str, Any]:
        """Get knowledge units that enable this KU."""
        require_authenticated_user(request)

        result = await services.ku_lateral.get_enabled_by(uid)

        if result.is_error:
            return {"success": False, "error": str(result.error)}, 400

        return {
            "success": True,
            "enabled_by": result.value,
            "count": len(result.value),
        }

    all_routes.extend([create_ku_enables, get_ku_enables, get_ku_enabled_by])
    logger.info("✅ KU lateral routes registered (including ENABLES relationships)")

    # LS lateral routes
    ls_factory = LateralRouteFactory(
        app=app,
        rt=rt,
        domain="ls",
        lateral_service=services.ls_lateral,
        entity_name="Learning Step",
    )
    all_routes.extend(ls_factory.create_routes())
    logger.info("✅ LS lateral routes registered")

    # LP lateral routes
    lp_factory = LateralRouteFactory(
        app=app,
        rt=rt,
        domain="lp",
        lateral_service=services.lp_lateral,
        entity_name="Learning Path",
    )
    all_routes.extend(lp_factory.create_routes())
    logger.info("✅ LP lateral routes registered")

    logger.info(f"✅ Lateral relationship routes registered: {len(all_routes)} total routes")
    logger.info(
        "   Activity Domains: Tasks, Goals, Habits, Events, Choices, Principles (6 domains)"
    )
    logger.info("   Curriculum Domains: KU, LS, LP (3 domains)")

    return all_routes


__all__ = ["create_lateral_routes"]
