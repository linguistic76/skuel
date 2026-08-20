"""
Semantic Relationship Linker - Generic Semantic Operations Pattern
===================================================================

Eliminates duplication across relationship services by providing generic
implementations for semantic relationship operations.

**The Problem:**
All relationship services (Habits, Goals, Tasks, Choices, Principles, Events)
had identical per-domain implementations of semantic relationship methods:
- create_semantic_X_relationship() (~40 lines each)
- find_X_by_semantic_filter() (~45 lines each)

**The Solution:**
Single generic helper that handles the common pattern; each relationship
service's semantic methods are thin delegations to it.

(The semantic-context READ surface — get_with_semantic_context — was deleted
in the tasks bloat campaign after its last facade caller went; the typed
reader ``get_cross_domain_context_typed`` is the live context lens.)
"""

from datetime import datetime
from typing import Any

from core.infrastructure.relationships.semantic_relationships import (
    RelationshipMetadata,
    SemanticRelationshipType,
)
from core.models.enums import Domain
from core.models.protocols.domain_model_protocol import DomainModelProtocol, DTOProtocol
from core.ports.base_protocols import BackendOperations
from core.services.base_service import BaseService
from core.services.relationship_builder import relate
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class SemanticRelationshipLinker[T: DomainModelProtocol, DTO: DTOProtocol]:
    """
    Generic helper for semantic relationship operations across all domains.

    Consolidates the per-domain semantic write/filter methods into one
    generic implementation:

    **Pattern (Using Helper):**
    ```python
    async def create_semantic_X_relationship(
        self, from_uid: str, to_uid: str, semantic_type, confidence: float = 0.9
    ):
        return await self.semantic_helper.create_semantic_relationship(
            from_uid, to_uid, semantic_type, confidence
        )
    ```

    SKUEL Architecture:
    - Leverages BaseService._to_domain_model() from
    """

    def __init__(
        self,
        service: BaseService,
        dto_class: type[DTO],
        model_class: type[T],
        domain: Domain,
        source_tag: str,
    ) -> None:
        """
        Initialize semantic relationship helper with service-specific configuration.

        Args:
            service: The relationship service (provides backend, BaseService helpers),
            dto_class: DTO class for conversion (e.g., HabitDTO),
            model_class: Domain model class (e.g., Habit),
            domain: Domain enum for categorization (e.g., Domain.HABITS),
            source_tag: Source tag for relationships (e.g., "habits_service_explicit")
        """
        self.service = service
        self.backend: BackendOperations[T] = service.backend
        self.dto_class = dto_class
        self.model_class = model_class
        self.domain = domain
        self.source_tag = source_tag
        self.logger = get_logger(f"skuel.services.infrastructure.semantic_helper.{domain.value}")

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

        Generic implementation for all domains via UnifiedRelationshipService.

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
            # Usage example:
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

        # Step 2: Write the edge. `to_neo4j_name()` supplies the coarse
        # RelationshipName edge type; `semantic_type` in the properties preserves
        # the precise namespaced predicate so the many-to-one collapse loses
        # nothing (roadmap Phase 1).
        #
        # add_relationship MERGEs on (from, TYPE, to) and updates properties, so
        # re-linking the same pair with new confidence/notes revises the edge
        # instead of forking a second one — the idempotence every other writer in
        # the codebase already has.
        metadata_props = metadata.to_neo4j_properties()
        metadata_props["semantic_type"] = semantic_type.value

        result = await (
            relate(self.backend, from_uid)
            .via(semantic_type.to_neo4j_name())
            .to(to_uid)
            .with_properties(**metadata_props)
            .create()
        )

        if result.is_error:
            return Result.fail(result)

        # Step 3: Construct the semantic triple for the response (the write
        # returns bool, not a triple).
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

        Generic implementation for all domains via UnifiedRelationshipService.

        Args:
            target_uid: Target entity UID to filter by (usually Knowledge UID),
            semantic_types: List of semantic relationship types to match,
            min_confidence: Minimum confidence threshold (0.0-1.0),
            direction: Relationship direction ('incoming' or 'outgoing')

        Returns:
            Result containing list of domain model objects (Habit, Goal, Task, etc.),

        Example:
            ```python
            # Usage example:
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

        # Step 1: Build semantic filter query.
        # The pattern carries the coarse RelationshipName edge type(s) (deduped —
        # many predicates collapse onto one); the precise predicates are passed
        # separately so the backend filters by r.semantic_type and does not return
        # other semantic types that share the same edge (roadmap Phase 1).
        rel_types = "|".join(sorted({str(st.to_neo4j_name()) for st in semantic_types}))
        semantic_type_values = [st.value for st in semantic_types]
        label = self.model_class.__name__

        # Build direction pattern
        if direction == "incoming":
            pattern = f"(n:{label})-[r:{rel_types}]->(target)"
        elif direction == "outgoing":
            pattern = f"(n:{label})<-[r:{rel_types}]-(target)"
        else:  # both
            pattern = f"(n:{label})-[r:{rel_types}]-(target)"

        # Step 2: Execute query to get entity UIDs via typed backend method
        result = await self.backend.find_uids_by_semantic_filter(
            pattern=pattern,
            target_uid=target_uid,
            min_confidence=min_confidence,
            semantic_type_values=semantic_type_values,
        )
        if result.is_error:
            return Result.fail(result)

        entity_uids = result.value

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

    async def _fetch_single_entity(self, uid: str) -> Result[T]:
        """
        Fetch a single entity and convert to domain model.

        Args:
            uid: Entity UID

        Returns:
            Result containing domain model object
        """
        entity_result = await self.backend.get(uid)
        if entity_result.is_error:
            return Result.fail(entity_result)

        if not entity_result.value:
            return Result.fail(Errors.not_found(resource=self.model_class.__name__, identifier=uid))

        # Convert using BaseService helper
        entity = self.service._to_domain_model(
            entity_result.value, self.dto_class, self.model_class
        )

        return Result.ok(entity)
