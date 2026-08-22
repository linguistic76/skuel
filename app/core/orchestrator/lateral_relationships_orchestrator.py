"""Lateral Relationships Orchestrator
======================================

Application orchestrator for the Lateral Relationships API. Consolidates
LateralRelationshipService and the 6 Activity Domain services into a single
facade, eliminating the multi-service kwargs threading in create_lateral_api_routes.

All dependencies are required — bootstrap raises if any are missing
(Fail-Fast Dependency Philosophy).
"""

from typing import TYPE_CHECKING, Any

from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.service_protocols import (
        LateralRelationshipOperations,
        OwnershipVerifier,
    )
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.principles_service import PrinciplesService
    from core.services.tasks_service import TasksService


class LateralRelationshipsOrchestrator:
    """Facade for the Lateral Relationships API layer.

    Wraps LateralRelationshipService and the 6 Activity Domain services,
    eliminating the multi-service kwargs threading in create_lateral_api_routes.

    All dependencies are required — bootstrap raises if any are missing
    (Fail-Fast Dependency Philosophy).
    """

    def __init__(
        self,
        lateral_service: "LateralRelationshipOperations",
        tasks_service: "TasksService",
        goals_service: "GoalsService",
        habits_service: "HabitsService",
        events_service: "EventsService",
        choices_service: "ChoicesService",
        principles_service: "PrinciplesService",
    ) -> None:
        self._lateral = lateral_service
        self._domain_services: dict[str, OwnershipVerifier] = {
            "tasks": tasks_service,
            "goals": goals_service,
            "habits": habits_service,
            "events": events_service,
            "choices": choices_service,
            "principles": principles_service,
        }

    # --- Service access ---

    @property
    def lateral_service(self) -> "LateralRelationshipOperations":
        """Expose lateral service for LateralRouteFactory construction.

        LateralRouteFactory lives in the inbound adapter layer and cannot depend
        on this orchestrator — it must receive the raw service. This property is
        the one legitimate point where the orchestrator surface leaks a sub-service.
        """
        return self._lateral

    def get_domain_service(self, domain: str) -> "OwnershipVerifier | None":
        """Return the Activity Domain service for a given domain slug.

        Returns None for curriculum domains (ku, ps, lp), which have no ownership
        verification and are shared across all users.
        """
        return self._domain_services.get(domain)

    # --- Relationship operations ---

    async def create_relationship(
        self,
        user_uid: UserUID,
        uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        domain: str,
        metadata: dict[str, Any],
        message: str,
        response_extra: dict[str, Any],
        domain_service: "OwnershipVerifier | None" = None,
    ) -> "Result[dict[str, Any]]":
        """Create a domain-specific lateral relationship with optional ownership check.

        Args:
            user_uid: Authenticated user (injected by route before calling).
            uid: Source entity UID.
            target_uid: Target entity UID.
            relationship_type: The RelationshipName to create.
            domain: Domain slug added to relationship metadata.
            metadata: Domain-specific metadata fields.
            message: Human-readable success message.
            response_extra: Additional fields merged into the success response.
            domain_service: Activity Domain service for ownership verification.
                None for curriculum domains (shared, no ownership check).
        """
        full_metadata: dict[str, Any] = {**metadata, "domain": domain}
        create_kwargs: dict[str, Any] = {
            "source_uid": uid,
            "target_uid": target_uid,
            "relationship_type": relationship_type,
            "metadata": full_metadata,
        }
        if domain_service is not None:
            full_metadata["created_by"] = user_uid
            create_kwargs["user_uid"] = user_uid
            create_kwargs["domain_service"] = domain_service

        result = await self._lateral.create_lateral_relationship(**create_kwargs)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"message": message, **response_extra})

    async def get_relationships(
        self,
        user_uid: UserUID,
        uid: str,
        relationship_type: RelationshipName,
        direction: str,
        response_key: str,
        domain_service: "OwnershipVerifier | None" = None,
    ) -> "Result[dict[str, Any]]":
        """Get lateral relationships for an entity with optional ownership check.

        Args:
            user_uid: Authenticated user (injected by route before calling).
            uid: Entity UID to query.
            relationship_type: Relationship type to filter on.
            direction: "incoming", "outgoing", or "both".
            response_key: Top-level key for the relationship list in the response.
            domain_service: Activity Domain service for ownership verification.
                None for curriculum domains (shared, no ownership check).
        """
        # user_uid ALWAYS rides along: target audience scoping (ADR-085 G4)
        # needs the caller even on curriculum anchors, where domain_service is
        # None (no anchor ownership check) but the caller's own linked
        # activities must still be visible to them and nobody else's are.
        get_kwargs: dict[str, Any] = {
            "entity_uid": uid,
            "relationship_types": [relationship_type],
            "direction": direction,
            "user_uid": user_uid,
        }
        if domain_service is not None:
            get_kwargs["domain_service"] = domain_service

        result = await self._lateral.get_lateral_relationships(**get_kwargs)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({response_key: result.value, "count": len(result.value)})
