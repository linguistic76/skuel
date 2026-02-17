"""
Relationship Creation Helper - Generic Cross-Domain Relationship Pattern
=========================================================================

Eliminates duplication across relationship services by providing generic
implementations for cross-domain relationship creation and context retrieval.

**The Problem:**
All relationship services (Habits, Goals, Tasks, Choices, Principles, Events)
had identical patterns for creating relationships:
- link_X_to_knowledge() (~15 lines each)
- link_X_to_goal() (~15 lines each)
- link_X_to_principle() (~15 lines each)
- create_user_X_relationship() (~10 lines each)
- get_X_cross_domain_context() (~20 lines each)

Total duplication: ~300-400 LOC across 8 services

**The Solution:**
Single generic helper that handles the common pattern, reducing
each relationship service's creation methods from ~15 LOC → 3 LOC.
"""

from typing import Any, TypeVar

from core.models.enums import Domain
from core.services.base_service import BaseService
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# Generic type variables
T = TypeVar("T")  # Domain model type (Habit, Goal, Task, etc.)
DTO = TypeVar("DTO")  # DTO type (HabitDTO, GoalDTO, etc.)


class RelationshipCreationHelper[T, DTO]:
    """
    Generic helper for cross-domain relationship creation and context retrieval.

    This helper eliminates ~40-50 lines of duplicated code in each
    relationship service's relationship creation methods.

    **Pattern Before (Habits, Goals, Tasks, etc. all identical):**
    ```python
    async def link_X_to_knowledge(
        self, x_uid: str, knowledge_uid: str, property_1: Any, property_2: Any
    ) -> Result[bool]:
        '''
        Link X to knowledge unit.
        Creates: (X)-[:REQUIRES_KNOWLEDGE]->(Knowledge)
        '''
        try:
            result = await self.backend.link_X_to_knowledge(
                x_uid, knowledge_uid, property_1, property_2
            )

            if result.is_ok:
                self.logger.info(f"Linked {x_uid} to knowledge {knowledge_uid}")

            return result

        except Exception as e:
            self.logger.error(f"Link X to knowledge failed: {e}")
            return Result.fail(
                Errors.database(operation="link_X_to_knowledge", message=str(e))
            )
    ```

    **Pattern After (Using Helper):**
    ```python
    async def link_X_to_knowledge(
        self, x_uid: str, knowledge_uid: str, property_1: Any, property_2: Any
    ) -> Result[bool]:
        return await self.relationship_helper.create_relationship(
            backend_method="link_X_to_knowledge",
            from_uid=x_uid,
            to_uid=knowledge_uid,
            relationship_label=SemanticRelationshipType.REQUIRES_KNOWLEDGE.value,
            properties={"property_1": property_1, "property_2": property_2},
            log_message=f"Linked {x_uid} to knowledge {knowledge_uid}",
        )
    ```

    **15 lines → 8 lines (47% reduction, ~300-400 lines saved across all services)**

    SKUEL Architecture:
    - Follows SemanticRelationshipHelper pattern exactly
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    - Leverages BaseService infrastructure
    - Protocol-based backend calls
    """

    def __init__(
        self,
        service: BaseService,
        backend_get_method: str,
        dto_class: type[DTO],
        model_class: type[T],
        domain: Domain,
    ) -> None:
        """
        Initialize relationship creation helper with service-specific configuration.

        Args:
            service: The relationship service (provides backend, BaseService helpers),
            backend_get_method: Name of backend method to call (e.g., "get_habit", "get_goal"),
            dto_class: DTO class for conversion (e.g., HabitDTO),
            model_class: Domain model class (e.g., Habit),
            domain: Domain enum for categorization (e.g., Domain.HABITS),
        """
        self.service = service
        self.backend = service.backend
        self.backend_get_method = backend_get_method
        self.dto_class = dto_class
        self.model_class = model_class
        self.domain = domain
        self.logger = get_logger(
            f"skuel.services.infrastructure.relationship_helper.{domain.value}"
        )

    @with_error_handling(error_type="database")
    async def create_relationship(
        self,
        backend_method: str,
        from_uid: str,
        to_uid: str,
        relationship_label: str,
        properties: dict[str, Any] | None = None,
        log_message: str | None = None,
    ) -> Result[bool]:
        """
        Generic implementation of link_X_to_Y() pattern.

        Handles the complete relationship creation flow:
        1. Call backend method with specified parameters
        2. Log success/failure
        3. Return Result[bool]

        This single implementation replaces identical code in:
        - HabitsRelationshipService.link_habit_to_knowledge()
        - HabitsRelationshipService.link_habit_to_principle()
        - GoalsRelationshipService.link_goal_to_knowledge()
        - GoalsRelationshipService.link_goal_to_habit()
        - TasksRelationshipService.link_task_to_knowledge()
        - TasksRelationshipService.link_task_to_goal()
        - EventsRelationshipService.link_event_to_habit()
        - ChoicesRelationshipService.link_choice_to_knowledge()
        - PrinciplesRelationshipService.link_principle_to_knowledge()
        - (30-40+ identical methods across all services)

        Args:
            backend_method: Name of backend method to call (e.g., "link_habit_to_knowledge"),
            from_uid: Source entity UID,
            to_uid: Target entity UID,
            relationship_label: Cypher relationship label (e.g., SemanticRelationshipType.REQUIRES_KNOWLEDGE.value),
            properties: Dict of relationship properties (domain-specific),
            log_message: Optional custom success log message

        Returns:
            Result[bool] indicating success

        Example:
            ```python
            # In HabitsRelationshipService.__init__:
            self.relationship_helper = RelationshipCreationHelper[Habit, HabitDTO](
                service=self,
                backend_get_method="get_habit",
                dto_class=HabitDTO,
                model_class=Habit,
                domain=Domain.HABITS,
            )

            # In link_habit_to_knowledge():
            return await self.relationship_helper.create_relationship(
                backend_method="link_habit_to_knowledge",
                from_uid=habit_uid,
                to_uid=knowledge_uid,
                relationship_label="DEVELOPS_SKILL",
                properties={
                    "skill_level": skill_level,
                    "proficiency_gain_rate": proficiency_gain_rate,
                },
                log_message=f"Linked habit {habit_uid} to knowledge {knowledge_uid}",
            )
            ```
        """
        # Step 1: Get backend method
        backend_fn = getattr(self.backend, backend_method, None)
        if not backend_fn:
            return Result.fail(
                Errors.system(
                    message=f"Backend method '{backend_method}' not found",
                    operation="create_relationship",
                )
            )

        self.logger.debug(
            f"Creating relationship via {backend_method}: {from_uid} -[{relationship_label}]-> {to_uid}"
        )

        # Step 2: Call backend method
        # Backend methods have varying signatures, so we need to handle parameters dynamically
        # Most backends accept (from_uid, to_uid, **properties)
        if properties:
            result = await backend_fn(from_uid, to_uid, **properties)
        else:
            result = await backend_fn(from_uid, to_uid)

        # Step 3: Log success
        if result.is_ok:
            if log_message:
                self.logger.info(log_message)
            else:
                self.logger.info(
                    f"Created relationship: {from_uid} -[{relationship_label}]-> {to_uid}"
                )

        return result

    async def create_user_relationship(
        self,
        user_uid: str,
        entity_uid: str,
        relationship_label: str,
        properties: dict[str, Any] | None = None,
        backend_method: str | None = None,
    ) -> Result[bool]:
        """
        Generic implementation of create_user_X_relationship() pattern.

        Handles the complete user→entity relationship creation flow:
        1. Call backend method to create User→Entity edge
        2. Log success/failure
        3. Return Result[bool]

        This single implementation replaces identical code in:
        - HabitsRelationshipService.create_user_habit_relationship()
        - GoalsRelationshipService.create_user_goal_relationship()
        - TasksRelationshipService.create_user_task_relationship()
        - EventsRelationshipService.create_user_event_relationship()
        - ChoicesRelationshipService.create_user_choice_relationship()
        - PrinciplesRelationshipService.create_user_principle_relationship()

        Args:
            user_uid: User UID,
            entity_uid: Entity UID (habit, goal, task, etc.),
            relationship_label: Cypher relationship label (e.g., "HAS_HABIT", "ASSIGNED_TO"),
            properties: Dict of relationship properties (e.g., {"commitment_level": "active"}),
            backend_method: Optional backend method name (defaults to "create_user_{domain}_relationship")

        Returns:
            Result[bool] indicating success

        Example:
            ```python
            # In HabitsRelationshipService:
            async def create_user_habit_relationship(
                self, user_uid: str, habit_uid: str, commitment_level: str = "active"
            ) -> Result[bool]:
                return await self.relationship_helper.create_user_relationship(
                    user_uid=user_uid,
                    entity_uid=habit_uid,
                    relationship_label="HAS_HABIT",
                    properties={"commitment_level": commitment_level},
                )
            ```
        """
        # Step 1: Determine backend method name
        if not backend_method:
            # Default: create_user_{domain}_relationship
            domain_name = self.domain.value  # e.g., "habits"
            backend_method = f"create_user_{domain_name.rstrip('s')}_relationship"
            # habits → create_user_habit_relationship
            # goals → create_user_goal_relationship

        # Step 2: Use generic create_relationship method
        return await self.create_relationship(
            backend_method=backend_method,
            from_uid=user_uid,
            to_uid=entity_uid,
            relationship_label=relationship_label,
            properties=properties,
            log_message=f"Created {relationship_label} relationship: {user_uid} → {entity_uid}",
        )

    @with_error_handling(error_type="database", uid_param="entity_uid")
    async def get_cross_domain_context(
        self,
        entity_uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
        backend_method: str | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Generic implementation of get_X_cross_domain_context() pattern with configurable depth and confidence.

        Handles the complete cross-domain context retrieval flow:
        1. Call backend method to get comprehensive context
        2. Return structured context dict

        This single implementation replaces identical code in:
        - HabitsRelationshipService.get_habit_cross_domain_context()
        - GoalsRelationshipService.get_goal_cross_domain_context()
        - TasksRelationshipService.get_task_cross_domain_context()
        - EventsRelationshipService.get_event_cross_domain_context()
        - ChoicesRelationshipService.get_choice_cross_domain_context()
        - PrinciplesRelationshipService.get_principle_cross_domain_context()

        Args:
            entity_uid: Entity UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)
            min_confidence: Minimum path confidence filter (0.0-1.0, default=0.7 = 70% confidence)
            backend_method: Optional backend method name (defaults to "get_{domain}_cross_domain_context")

        Returns:
            Result containing comprehensive cross-domain context dict with path-aware intelligence

        Example:
            ```python
            # In HabitsRelationshipService:
            async def get_habit_cross_domain_context(
                self, habit_uid: str, depth: int = 2, min_confidence: float = 0.7
            ) -> Result[dict[str, Any]]:
                return await self.relationship_helper.get_cross_domain_context(
                    entity_uid=habit_uid, depth=depth, min_confidence=min_confidence
                )
            ```
        """
        # Step 1: Determine backend method name
        if not backend_method:
            # Default: get_{domain}_cross_domain_context
            domain_name = self.domain.value  # e.g., "habits"
            singular = domain_name.rstrip("s")  # habits → habit
            backend_method = f"get_{singular}_cross_domain_context"

        # Step 2: Get backend method
        backend_fn = getattr(self.backend, backend_method, None)
        if not backend_fn:
            return Result.fail(
                Errors.system(
                    message=f"Backend method '{backend_method}' not found",
                    operation="get_cross_domain_context",
                )
            )

        self.logger.debug(
            f"Retrieving cross-domain context for {self.model_class.__name__} {entity_uid} (depth={depth}, min_confidence={min_confidence})"
        )

        # Step 3: Call backend method with depth and min_confidence parameters
        result = await backend_fn(entity_uid, depth=depth, min_confidence=min_confidence)

        if result.is_ok:
            self.logger.debug(
                f"Retrieved cross-domain context for {self.model_class.__name__} {entity_uid}"
            )

        return result

    @with_error_handling(error_type="database")
    async def batch_get_cross_domain_context(
        self,
        entity_uids: list[str],
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[dict[str, dict[str, Any]]]:
        """
        Batch version of get_cross_domain_context - retrieves context for multiple entities in a single query.

        This eliminates N+1 query patterns by using UNWIND to process all UIDs in one database round-trip.

        Performance: 100 entities = 1 query (vs 100 queries with get_cross_domain_context loop)

        Args:
            entity_uids: List of entity UIDs to retrieve context for
            depth: Reserved for future enhancement (currently only direct relationships)
            min_confidence: Reserved for future enhancement (currently no confidence filtering)

        Returns:
            Result containing dict mapping entity_uid -> context_dict

        Example:
            ```python
            # Instead of N+1 pattern:
            for expense in expenses:
                context = await get_cross_domain_context(expense.uid)

            # Use batch:
            contexts = await batch_get_cross_domain_context([e.uid for e in expenses])
            for expense in expenses:
                context = contexts[expense.uid]
            ```
        """
        if not entity_uids:
            return Result.ok({})

        # Build batch query using UNWIND pattern
        domain_name = self.domain.value
        singular = domain_name.rstrip("s")
        label = singular.capitalize()

        # Cypher query using UNWIND to process all UIDs in one round-trip
        query = f"""
        UNWIND $entity_uids AS entity_uid
        MATCH (entity:{label} {{uid: entity_uid}})

        // Get cross-domain relationships
        OPTIONAL MATCH (entity)-[:SUPPORTS_GOAL]->(goal:Goal)
        OPTIONAL MATCH (entity)-[:ENABLES_KNOWLEDGE|:APPLIES_KNOWLEDGE]->(ku:Ku)
        OPTIONAL MATCH (entity)-[:FUNDS_HABIT]->(habit:Habit)
        OPTIONAL MATCH (entity)-[:FUNDS_TASK|:ENABLES_TASK]->(task:Task)
        OPTIONAL MATCH (entity)-[:INFORMED_BY_PRINCIPLE]->(principle:Principle)

        RETURN
            entity_uid,
            collect(DISTINCT goal) as goals,
            collect(DISTINCT ku) as knowledge,
            collect(DISTINCT habit) as habits,
            collect(DISTINCT task) as tasks,
            collect(DISTINCT principle) as principles
        """

        params = {"entity_uids": entity_uids}

        self.logger.debug(
            f"Batch retrieving cross-domain context for {len(entity_uids)} {self.model_class.__name__} entities"
        )

        # Execute batch query
        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return result

        # Transform results into dict[uid -> context]
        contexts = {}
        for record in result.value:
            uid = record.get("entity_uid")
            contexts[uid] = {
                "goals": record.get("goals", []),
                "knowledge": record.get("knowledge", []),
                "habits": record.get("habits", []),
                "tasks": record.get("tasks", []),
                "principles": record.get("principles", []),
            }

        self.logger.debug(
            f"Retrieved cross-domain context for {len(contexts)} {self.model_class.__name__} entities"
        )

        return Result.ok(contexts)

    async def get_entity(self, uid: str) -> Result[T]:
        """
        Fetch a single entity and convert to domain model.

        Convenience method for relationship services that need to fetch entities.

        Args:
            uid: Entity UID

        Returns:
            Result containing domain model object
        """
        get_method = getattr(self.backend, self.backend_get_method, None)
        if not get_method:
            return Result.fail(
                Errors.system(
                    message=f"Backend method '{self.backend_get_method}' not found",
                    operation="get_entity",
                )
            )

        entity_result = await get_method(uid)
        if entity_result.is_error:
            return entity_result

        if not entity_result.value:
            return Result.fail(Errors.not_found(resource=self.model_class.__name__, identifier=uid))

        # Convert using BaseService helper
        entity = self.service._to_domain_model(
            entity_result.value, self.dto_class, self.model_class
        )

        return Result.ok(entity)
