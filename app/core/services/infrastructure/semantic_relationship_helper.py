"""
Semantic Relationship Helper - Generic Semantic Operations Pattern
===================================================================

Eliminates duplication across relationship services by providing generic
implementations for semantic relationship operations.

**The Problem:**
All relationship services (Habits, Goals, Tasks, Choices, Principles, Events)
had identical 155-line implementations of semantic relationship methods:
- get_X_with_semantic_context() (~70 lines each)
- create_semantic_X_relationship() (~40 lines each)
- find_X_by_semantic_filter() (~45 lines each)

Total duplication: ~930 LOC across 6 services

**The Solution:**
Single generic helper that handles the common pattern, reducing
each relationship service's semantic methods from 155 LOC → 11 LOC.
"""

from datetime import datetime
from typing import Any, TypeVar

from adapters.persistence.neo4j.query import build_semantic_context
from core.infrastructure.relationships.semantic_relationships import (
    RelationshipMetadata,
    SemanticRelationshipType,
)
from core.models.enums import Domain
from core.services.base_service import BaseService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# Generic type variables
T = TypeVar("T")  # Domain model type (Habit, Goal, Task, etc.)
DTO = TypeVar("DTO")  # DTO type (HabitDTO, GoalDTO, etc.)


class SemanticRelationshipHelper[T, DTO]:
    """
    Generic helper for semantic relationship operations across all domains.

    This helper eliminates ~155 lines of duplicated code in each
    relationship service's semantic methods.

    **Pattern Before (Habits, Goals, Tasks, etc. all identical):**
    ```python
    async def get_X_with_semantic_context(
        self, uid: str, min_confidence: float = 0.8
    ):
        # Get entity (10 lines)
        entity_result = await self.backend.get_X(uid)
        if entity_result.is_error:
            return entity_result

        # Convert dict → DTO → Domain (10 lines)
        dto = (
            XDTO.from_dict(entity_result.value)
            if isinstance(...)
            else entity_result.value
        )
        entity = X.from_dto(dto) if isinstance(...) else entity_result.value

        # Build semantic context query (10 lines)
        cypher, params = build_semantic_context(
            node_uid=uid,
            semantic_types=[...],
            GraphDepth.DEFAULT,
            min_confidence=min_confidence,
        )

        # Execute query (5 lines)
        context_result = await self.backend.execute_query(cypher, params)
        if context_result.is_error:
            return context_result

        semantic_context = context_result.value or []

        # Filter by semantic types (25 lines)
        type_1 = [
            item
            for item in semantic_context
            if TYPE_1 in item.get("relationship_types", [])
        ]
        type_2 = [
            item
            for item in semantic_context
            if TYPE_2 in item.get("relationship_types", [])
        ]
        type_3 = [
            item
            for item in semantic_context
            if TYPE_3 in item.get("relationship_types", [])
        ]

        # Return structured result (10 lines)
        return Result.ok(
            {
                "entity": entity,
                "semantic_context": semantic_context,
                "type_1": type_1,
                "type_2": type_2,
                "type_3": type_3,
                "total_relationships": len(semantic_context),
            }
        )
    ```

    **Pattern After (Using Helper):**
    ```python
    async def get_X_with_semantic_context(
        self, uid: str, min_confidence: float = 0.8
    ):
        return await self.semantic_helper.get_with_semantic_context(
            uid=uid,
            semantic_types=[TYPE_1, TYPE_2, TYPE_3],
            min_confidence=min_confidence,
        )
    ```

    **70 lines → 5 lines (93% reduction)**

    SKUEL Architecture:
    - Leverages BaseService._to_domain_model() from
    """

    def __init__(
        self,
        service: BaseService,
        backend_get_method: str,
        dto_class: type[DTO],
        model_class: type[T],
        domain: Domain,
        source_tag: str,
    ) -> None:
        """
        Initialize semantic relationship helper with service-specific configuration.

        Args:
            service: The relationship service (provides backend, BaseService helpers),
            backend_get_method: Name of backend method to call (e.g., "get_habit", "get_goal"),
            dto_class: DTO class for conversion (e.g., HabitDTO),
            model_class: Domain model class (e.g., Habit),
            domain: Domain enum for categorization (e.g., Domain.HABITS),
            source_tag: Source tag for relationships (e.g., "habits_service_explicit")
        """
        self.service = service
        self.backend = service.backend
        self.backend_get_method = backend_get_method
        self.dto_class = dto_class
        self.model_class = model_class
        self.domain = domain
        self.source_tag = source_tag
        self.logger = get_logger(f"skuel.services.infrastructure.semantic_helper.{domain.value}")

    async def get_with_semantic_context(
        self,
        uid: str,
        semantic_types: list[SemanticRelationshipType],
        min_confidence: float = 0.8,
        depth: int = 3,
    ) -> Result[dict[str, Any]]:
        """
        Generic implementation of get_X_with_semantic_context() pattern.

        Handles the complete semantic context retrieval flow:
        1. Fetch entity from backend
        2. Convert dict → DTO → Domain model
        3. Build semantic context query with specified types
        4. Execute query via backend
        5. Filter results by semantic types
        6. Return structured response

        This single implementation replaces identical code in:
        - HabitsRelationshipService.get_habit_with_semantic_context()
        - GoalsRelationshipService.get_goal_with_semantic_context()
        - TasksRelationshipService.get_task_with_semantic_context()
        - ChoicesRelationshipService.get_choice_with_semantic_context()
        - PrinciplesRelationshipService.get_principle_with_semantic_context()
        - EventsRelationshipService.get_event_with_semantic_context()

        Args:
            uid: Entity UID,
            semantic_types: List of semantic relationship types to query,
            min_confidence: Minimum confidence threshold (0.0-1.0),
            depth: Graph traversal depth (default: 3)

        Returns:
            Result containing:
            - entity: The domain model (Habit, Goal, Task, etc.)
            - semantic_context: All semantic relationships found
            - categorized_relationships: Relationships grouped by type
            - total_relationships: Count of relationships

        Example:
            ```python
            # In HabitsRelationshipService.__init__:
            self.semantic_helper = SemanticRelationshipHelper[Habit, HabitDTO](
                service=self,
                backend_get_method="get_habit",
                dto_class=HabitDTO,
                model_class=Habit,
                domain=Domain.HABITS,
                source_tag="habits_service_explicit",
            )

            # In get_habit_with_semantic_context():
            return await self.semantic_helper.get_with_semantic_context(
                uid=uid,
                semantic_types=[
                    SemanticRelationshipType.DEVELOPS_SKILL,
                    SemanticRelationshipType.STRENGTHENS_PRACTICE,
                ],
                min_confidence=min_confidence,
            )
            ```
        """
        # Step 1: Get entity from backend
        get_method = getattr(self.backend, self.backend_get_method, None)
        if not get_method:
            return Result.fail(
                Errors.system(
                    message=f"Backend method '{self.backend_get_method}' not found",
                    operation="get_with_semantic_context",
                )
            )

        entity_result = await get_method(uid)
        if entity_result.is_error:
            return entity_result

        if not entity_result.value:
            return Result.fail(Errors.not_found(resource=self.model_class.__name__, identifier=uid))

        # Step 2: Convert dict → DTO → Domain model using BaseService helper
        entity = self.service._to_domain_model(
            entity_result.value, self.dto_class, self.model_class
        )

        self.logger.debug(
            f"Fetching semantic context for {self.model_class.__name__} {uid} "
            f"with {len(semantic_types)} types, min_confidence={min_confidence}"
        )

        # Step 3: Build semantic context query
        cypher, params = build_semantic_context(
            node_uid=uid, semantic_types=semantic_types, depth=depth, min_confidence=min_confidence
        )

        # Step 4: Execute query through backend
        context_result = await self.backend.execute_query(cypher, params)
        if context_result.is_error:
            return context_result

        semantic_context = context_result.value or []

        # Step 5: Categorize relationships by type
        categorized = self._categorize_semantic_relationships(semantic_context, semantic_types)

        self.logger.debug(
            f"Retrieved {len(semantic_context)} semantic relationships for {self.model_class.__name__} {uid}"
        )

        # Step 6: Return structured result
        return Result.ok(
            {
                "entity": entity,
                "semantic_context": semantic_context,
                "categorized_relationships": categorized,
                "total_relationships": len(semantic_context),
            }
        )

    async def create_semantic_relationship(
        self,
        from_uid: str,
        to_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Generic implementation of create_semantic_X_relationship() pattern.

        Handles the complete semantic relationship creation flow:
        1. Create relationship metadata with source tag
        2. Call backend create_semantic_relationship
        3. Return structured response with semantic triple

        This single implementation replaces identical code in:
        - HabitsRelationshipService.create_semantic_skill_relationship()
        - GoalsRelationshipService.create_semantic_goal_relationship()
        - TasksRelationshipService.create_semantic_knowledge_relationship()
        - ChoicesRelationshipService.create_semantic_choice_relationship()
        - PrinciplesRelationshipService.create_semantic_principle_relationship()
        - EventsRelationshipService.create_semantic_event_relationship()

        Args:
            from_uid: Source entity UID,
            to_uid: Target entity UID (usually Knowledge UID),
            semantic_type: Type of semantic relationship,
            confidence: Confidence score (0.0-1.0, default 0.9),
            notes: Optional explanation/notes

        Returns:
            Result containing:
            - from_uid: Source entity UID
            - to_uid: Target entity UID
            - semantic_type: Relationship type value
            - confidence: Confidence score
            - source: Source tag
            - notes: Optional notes

        Example:
            ```python
            # In HabitsRelationshipService:
            async def create_semantic_skill_relationship(
                self, habit_uid, knowledge_uid, semantic_type, ConfidenceLevel.HIGH, notes=None
            ):
                return await self.semantic_helper.create_semantic_relationship(
                    from_uid=habit_uid,
                    to_uid=knowledge_uid,
                    semantic_type=semantic_type,
                    confidence=confidence,
                    notes=notes,
                )
            ```
        """
        self.logger.debug(
            f"Creating semantic relationship: {from_uid} -> {to_uid} "
            f"(type={semantic_type.value}, confidence={confidence})"
        )

        # Step 1: Create metadata with domain-specific source tag
        metadata = RelationshipMetadata(
            confidence=confidence,
            source=self.source_tag,
            strength=1.0,
            notes=notes,
            created_at=datetime.now(),
        )

        # Step 2: Create relationship via RELATIONSHIP-FIRST API (fluent interface)
        # Replaces: backend.create_semantic_relationship()
        # With: backend.relate().from_node().via().to_node().with_metadata().create()
        metadata_props = metadata.to_neo4j_properties()

        result = (
            await self.backend.relate()
            .from_node(from_uid)
            .via(semantic_type.to_neo4j_name())
            .to_node(to_uid)
            .with_metadata(**metadata_props)
            .create()
        )

        if result.is_error:
            return result

        # Step 3: Construct semantic triple for response (fluent API returns bool, not triple)
        # We build the triple manually to maintain backward compatibility
        self.logger.info(
            f"Created semantic relationship: {from_uid} -[{semantic_type.value}]-> {to_uid}"
        )

        # Return structured response (compatible with existing consumers)
        return Result.ok(
            {
                "from_uid": from_uid,
                "to_uid": to_uid,
                "semantic_type": semantic_type.value,
                "confidence": confidence,
                "source": self.source_tag,
                "notes": notes,
            }
        )

    async def find_by_semantic_filter(
        self,
        target_uid: str,
        semantic_types: list[SemanticRelationshipType],
        min_confidence: float = 0.8,
        direction: str = "incoming",
    ) -> Result[list[T]]:
        """
        Generic implementation of find_X_by_semantic_filter() pattern.

        Handles the complete semantic filter flow:
        1. Build semantic filter query
        2. Execute query to get entity UIDs
        3. Batch fetch full domain objects
        4. Convert each DTO → Domain model
        5. Return list of domain objects

        This single implementation replaces identical code in:
        - HabitsRelationshipService.find_habits_developing_knowledge()
        - GoalsRelationshipService.find_goals_requiring_knowledge()
        - TasksRelationshipService.find_tasks_requiring_knowledge()
        - ChoicesRelationshipService.find_choices_requiring_knowledge()
        - PrinciplesRelationshipService.find_principles_requiring_knowledge()
        - EventsRelationshipService.find_events_requiring_knowledge()

        Args:
            target_uid: Target entity UID to filter by (usually Knowledge UID),
            semantic_types: List of semantic relationship types to match,
            min_confidence: Minimum confidence threshold (0.0-1.0),
            direction: Relationship direction ('incoming' or 'outgoing')

        Returns:
            Result containing list of domain model objects (Habit, Goal, Task, etc.),

        Example:
            ```python
            # In HabitsRelationshipService:
            async def find_habits_developing_knowledge(
                self, knowledge_uid, min_ConfidenceLevel.STANDARD
            ):
                return await self.semantic_helper.find_by_semantic_filter(
                    target_uid=knowledge_uid,
                    semantic_types=[
                        SemanticRelationshipType.DEVELOPS_SKILL,
                        SemanticRelationshipType.STRENGTHENS_PRACTICE,
                    ],
                    min_confidence=min_confidence,
                    direction="incoming",
                )
            ```
        """
        self.logger.debug(
            f"Finding {self.model_class.__name__} by semantic filter: target={target_uid}, "
            f"types={[t.value for t in semantic_types]}, direction={direction}"
        )

        # Step 1: Build semantic filter query
        # Build relationship type list for Cypher
        rel_types = "|".join([st.to_neo4j_name() for st in semantic_types])
        label = self.model_class.__name__

        # Build direction pattern
        if direction == "incoming":
            pattern = f"(n:{label})-[r:{rel_types}]->(target)"
        elif direction == "outgoing":
            pattern = f"(n:{label})<-[r:{rel_types}]-(target)"
        else:  # both
            pattern = f"(n:{label})-[r:{rel_types}]-(target)"

        cypher = f"""
        MATCH {pattern}
        WHERE target.uid = $target_uid
          AND r.confidence >= $min_confidence
        RETURN DISTINCT n.uid as uid
        """

        params = {"target_uid": target_uid, "min_confidence": min_confidence}

        # Step 2: Execute query to get entity UIDs
        result = await self.backend.execute_query(cypher, params)
        if result.is_error:
            return result

        entity_uids = [row.get("uid") for row in result.value or []]

        self.logger.debug(f"Found {len(entity_uids)} matching {self.model_class.__name__} UIDs")

        # Step 3: Batch fetch full domain objects
        entities = []
        for uid in entity_uids:
            entity_result = await self._fetch_single_entity(uid)
            if entity_result.is_ok and entity_result.value:
                entities.append(entity_result.value)

        self.logger.info(
            f"Found {len(entities)} {self.model_class.__name__} matching semantic filter for {target_uid}"
        )

        return Result.ok(entities)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _categorize_semantic_relationships(
        self, semantic_context: list[dict[str, Any]], semantic_types: list[SemanticRelationshipType]
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Categorize semantic relationships by type.

        Args:
            semantic_context: List of semantic relationship records,
            semantic_types: List of semantic types to categorize

        Returns:
            Dict mapping semantic type values to lists of relationships
        """
        categorized = {}

        for semantic_type in semantic_types:
            type_value = semantic_type.value
            categorized[type_value] = [
                item
                for item in semantic_context
                if type_value in item.get("relationship_types", [])
            ]

        return categorized

    async def _fetch_single_entity(self, uid: str) -> Result[T]:
        """
        Fetch a single entity and convert to domain model.

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
                    operation="fetch_single_entity",
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
