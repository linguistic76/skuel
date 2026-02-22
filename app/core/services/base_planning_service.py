"""
Base Planning Service - Context-First User Planning Foundation
==============================================================

Provides the common foundation for all domain planning services that leverage
UserContext (~240 fields) for personalized, filtered, and ranked queries.

**Pattern:** Context-First - "Filter by readiness, rank by relevance, enrich with insights"

**DOMAINS USING THIS BASE SERVICE (4)**
---------------------------------------
1. TasksPlanningService(BasePlanningService[TasksOperations, Task])
2. GoalsPlanningService(BasePlanningService[GoalsOperations, Goal])
3. HabitsPlanningService(BasePlanningService[HabitsOperations, Habit])
4. PrinciplesPlanningService(BasePlanningService[PrinciplesOperations, Principle])

**Extracted Common Patterns:**
- Constructor initialization with backend + optional relationship service
- Post-construction wiring via set_relationship_service()
- Batch entity fetching via _get_entities_by_uids()
- Relationship querying via _get_related_uids()
- Logger initialization

**Philosophy:** "All dependencies are REQUIRED - no graceful degradation"
SKUEL runs at full capacity or not at all.

**Naming Convention:** *_for_user() suffix indicates context-awareness
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from core.ports.base_protocols import BackendOperations
    from core.services.relationships import UnifiedRelationshipService

# Type variables for generic backend and entity types
BackendT = TypeVar("BackendT", bound="BackendOperations[Any]")
EntityT = TypeVar("EntityT")


class BasePlanningService(ABC, Generic[BackendT, EntityT]):
    """
    Abstract base class for context-aware planning services.

    Provides common infrastructure for all planning services that use
    UserContext to deliver personalized recommendations.

    Type Parameters:
        BackendT: Domain-specific Operations protocol (e.g., TasksOperations)
        EntityT: Domain entity type (e.g., Task)

    Class Attributes (configure in subclasses):
        _domain_name: str - Domain name for error messages (e.g., "Tasks")

    Example:
        class TasksPlanningService(BasePlanningService[TasksOperations, Task]):
            _domain_name = "Tasks"

            async def get_actionable_tasks_for_user(
                self, context: UserContext, limit: int = 10
            ) -> Result[list[ContextualTask]]:
                # Domain-specific implementation
                ...
    """

    # Subclasses MUST override this
    _domain_name: str = "Entity"

    def __init__(
        self,
        backend: BackendT,
        relationship_service: UnifiedRelationshipService | None = None,
    ) -> None:
        """
        Initialize with required dependencies.

        Args:
            backend: Domain-specific Operations backend for entity retrieval
            relationship_service: UnifiedRelationshipService for relationship queries
                                 (can be wired post-construction via set_relationship_service)

        Raises:
            ValueError: If backend is not provided (fail-fast philosophy)
        """
        if not backend:
            raise ValueError(f"{self._domain_name} backend is required")

        self.backend: BackendT = backend
        self._relationship_service: UnifiedRelationshipService | None = relationship_service
        self.logger = logging.getLogger(self.__class__.__module__)

    def set_relationship_service(self, service: UnifiedRelationshipService) -> None:
        """
        Set relationship service reference (for post-construction wiring).

        This enables circular dependency resolution by allowing the relationship
        service to be injected after initial construction.

        Args:
            service: UnifiedRelationshipService instance
        """
        self._relationship_service = service

    # ========================================================================
    # PROTECTED HELPER METHODS
    # ========================================================================

    async def _get_entities_by_uids(self, uids: list[str]) -> list[EntityT]:
        """
        Batch-fetch domain entities from UIDs.

        Uses the backend's get_many() method to efficiently retrieve
        multiple entities in a single database call.

        Args:
            uids: List of entity UIDs to fetch

        Returns:
            List of domain models (excludes None values for missing UIDs)
        """
        if not uids:
            return []

        result = await self.backend.get_many(uids)
        if result.is_error:
            self.logger.warning(f"Failed to fetch {self._domain_name} by UIDs: {result.error}")
            return []

        # Filter out None values that may occur if some UIDs weren't found
        return [entity for entity in (result.value or []) if entity is not None]

    async def _get_related_uids(self, relationship_key: str, entity_uid: str) -> list[str]:
        """
        Get related UIDs using UnifiedRelationshipService.

        Args:
            relationship_key: Relationship key (e.g., "knowledge", "prerequisite_tasks")
            entity_uid: Entity UID to query from

        Returns:
            List of related UIDs, empty list if relationship service unavailable or on error
        """
        if not self._relationship_service:
            self.logger.debug(f"Relationship service not available for {relationship_key} query")
            return []

        result = await self._relationship_service.get_related_uids(relationship_key, entity_uid)
        if result.is_error:
            self.logger.warning(
                f"Failed to get related UIDs for {relationship_key}: {result.error}"
            )
            return []

        return result.value or []

    @property
    def has_relationship_service(self) -> bool:
        """Check if relationship service is available."""
        return self._relationship_service is not None
