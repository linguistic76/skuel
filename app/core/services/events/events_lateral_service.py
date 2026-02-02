"""
Events Lateral Service - Domain-Specific Lateral Relationships
===============================================================

Manages lateral relationships specifically for Events domain.

This service wraps the core LateralRelationshipService with domain-specific
logic, validation, and business rules for event relationships.

Common Event Lateral Relationships:
    - CONFLICTS_WITH: Scheduling conflicts (time overlap)
    - COMPLEMENTARY_TO: Events that enhance each other
    - PREREQUISITE_FOR: Event A should happen before Event B
    - RELATED_TO: Events in similar contexts

Usage:
    events_lateral = EventsLateralService(driver, events_service)

    # Create conflict relationship
    await events_lateral.create_conflict_relationship(
        event_a_uid="event_meeting_abc",
        event_b_uid="event_workshop_xyz",
        conflict_type="time_overlap",
        severity="hard"
    )

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from core.models.enums.lateral_relationship_types import LateralRelationType
from core.services.lateral_relationships import LateralRelationshipService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class EventsLateralService:
    """
    Domain-specific service for Event lateral relationships.

    Delegates to core LateralRelationshipService while adding:
    - Domain-specific validation
    - Business rules enforcement
    - Convenient wrapper methods
    - Event-specific relationship types (conflicts, scheduling)
    """

    def __init__(
        self,
        driver: Any,
        events_service: Any,  # EventsOperations protocol
    ) -> None:
        """
        Initialize events lateral service.

        Args:
            driver: Neo4j driver
            events_service: Events domain service for validation
        """
        self.driver = driver
        self.events_service = events_service
        self.lateral_service = LateralRelationshipService(driver)

    async def create_conflict_relationship(
        self,
        event_a_uid: str,
        event_b_uid: str,
        conflict_type: str,
        severity: str = "hard",
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create CONFLICTS_WITH relationship for scheduling conflicts.

        Args:
            event_a_uid: First event
            event_b_uid: Second event
            conflict_type: Type of conflict (time_overlap, resource, location, energy)
            severity: "hard" (impossible) or "soft" (difficult but possible)
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Team Meeting" CONFLICTS_WITH "Client Call"
            → Time overlap makes both impossible
        """
        # Verify ownership
        if user_uid:
            for event_uid in [event_a_uid, event_b_uid]:
                ownership_result = await self.events_service.verify_ownership(event_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Event {event_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=event_a_uid,
            target_uid=event_b_uid,
            relationship_type=LateralRelationType.CONFLICTS_WITH,
            metadata={
                "conflict_type": conflict_type,
                "severity": severity,
                "domain": "events",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_complementary_relationship(
        self,
        event_a_uid: str,
        event_b_uid: str,
        synergy_description: str,
        synergy_type: str | None = None,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create COMPLEMENTARY_TO relationship for synergistic events.

        Args:
            event_a_uid: First event
            event_b_uid: Second event
            synergy_description: How events complement each other
            synergy_type: Type of synergy (e.g., "theory_practice", "networking")
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Workshop Lecture" COMPLEMENTARY_TO "Hands-on Lab"
            → Theory + practice = better learning
        """
        # Verify ownership
        if user_uid:
            for event_uid in [event_a_uid, event_b_uid]:
                ownership_result = await self.events_service.verify_ownership(event_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Event {event_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=event_a_uid,
            target_uid=event_b_uid,
            relationship_type=LateralRelationType.COMPLEMENTARY_TO,
            metadata={
                "synergy_description": synergy_description,
                "synergy_type": synergy_type,
                "domain": "events",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_prerequisite_relationship(
        self,
        prerequisite_uid: str,
        dependent_uid: str,
        strength: float = 0.8,
        reasoning: str | None = None,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create PREREQUISITE_FOR relationship for event sequencing.

        Args:
            prerequisite_uid: Event that should happen first
            dependent_uid: Event that follows
            strength: How important sequencing is (0.0-1.0)
            reasoning: Optional explanation
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Orientation" PREREQUISITE_FOR "First Day of Class"
        """
        if not 0.0 <= strength <= 1.0:
            return Result.fail(Errors.validation("strength must be between 0.0 and 1.0"))

        # Verify ownership
        if user_uid:
            for event_uid in [prerequisite_uid, dependent_uid]:
                ownership_result = await self.events_service.verify_ownership(event_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Event {event_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=prerequisite_uid,
            target_uid=dependent_uid,
            relationship_type=LateralRelationType.PREREQUISITE_FOR,
            metadata={
                "strength": strength,
                "reasoning": reasoning,
                "domain": "events",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=True,  # Creates REQUIRES_PREREQUISITE
        )

    async def create_related_relationship(
        self,
        event_a_uid: str,
        event_b_uid: str,
        relationship_type: str,
        strength: float = 0.7,
        description: str | None = None,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create RELATED_TO relationship for semantic connection.

        Args:
            event_a_uid: First event
            event_b_uid: Second event
            relationship_type: Type of relationship (e.g., "same_project", "same_context")
            strength: Strength of relation (0.0-1.0)
            description: Optional description
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Planning Meeting" RELATED_TO "Review Meeting"
            → Same project context
        """
        if not 0.0 <= strength <= 1.0:
            return Result.fail(Errors.validation("strength must be between 0.0 and 1.0"))

        # Verify ownership
        if user_uid:
            for event_uid in [event_a_uid, event_b_uid]:
                ownership_result = await self.events_service.verify_ownership(event_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Event {event_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=event_a_uid,
            target_uid=event_b_uid,
            relationship_type=LateralRelationType.RELATED_TO,
            metadata={
                "relationship_type": relationship_type,
                "strength": strength,
                "description": description,
                "domain": "events",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def get_conflicting_events(
        self,
        event_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get events that conflict with this event.

        Args:
            event_uid: Event UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of conflicting events
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.events_service.verify_ownership(event_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Event {event_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=event_uid,
            relationship_types=[LateralRelationType.CONFLICTS_WITH],
            direction="both",
            include_metadata=True,
        )

    async def get_complementary_events(
        self,
        event_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get events that complement this event.

        Args:
            event_uid: Event UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of complementary events
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.events_service.verify_ownership(event_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Event {event_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=event_uid,
            relationship_types=[LateralRelationType.COMPLEMENTARY_TO],
            direction="both",
            include_metadata=True,
        )

    async def get_prerequisite_events(
        self,
        event_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get events that are prerequisites for this event.

        Args:
            event_uid: Event UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of prerequisite events
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.events_service.verify_ownership(event_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Event {event_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=event_uid,
            relationship_types=[LateralRelationType.PREREQUISITE_FOR],
            direction="incoming",
            include_metadata=True,
        )

    async def get_dependent_events(
        self,
        event_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get events that depend on this event.

        Args:
            event_uid: Event UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of dependent events
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.events_service.verify_ownership(event_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Event {event_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=event_uid,
            relationship_types=[LateralRelationType.PREREQUISITE_FOR],
            direction="outgoing",
            include_metadata=True,
        )

    async def get_related_events(
        self,
        event_uid: str,
        min_strength: float = 0.5,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get related events.

        Args:
            event_uid: Event UID
            min_strength: Minimum relationship strength
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of related events
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.events_service.verify_ownership(event_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Event {event_uid} not found or access denied")
                )

        all_related = await self.lateral_service.get_lateral_relationships(
            entity_uid=event_uid,
            relationship_types=[LateralRelationType.RELATED_TO],
            direction="both",
            include_metadata=True,
        )

        if all_related.is_error:
            return all_related

        # Filter by minimum strength
        filtered = [
            event
            for event in all_related.value
            if event.get("metadata", {}).get("strength", 0) >= min_strength
        ]

        return Result.ok(filtered)

    async def get_sibling_events(
        self,
        event_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling events (same parent event or project).

        Args:
            event_uid: Event UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of sibling events
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.events_service.verify_ownership(event_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Event {event_uid} not found or access denied")
                )

        return await self.lateral_service.get_siblings(
            entity_uid=event_uid,
            include_explicit_only=False,
        )


__all__ = ["EventsLateralService"]
