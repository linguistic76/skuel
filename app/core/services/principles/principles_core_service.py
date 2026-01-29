"""
Principles Core Service
=======================

Handles core CRUD operations for principles.

Responsibilities:
- Create principles
- Get user principles
- Basic principle queries
- Principle filtering

Part of the PrincipleAlignmentService decomposition (October 13, 2025).
"""

from datetime import date, datetime
from typing import Any

from core.events import publish_event
from core.models.enums.activity_enums import ActivityStatus
from core.models.principle.principle import Principle, PrincipleCategory, PrincipleStrength
from core.models.principle.principle_dto import PrincipleDTO
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.protocols.domain_protocols import PrinciplesOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_principle_priority

logger = get_logger(__name__)


class PrinciplesCoreService(BaseService[PrinciplesOperations, Principle]):
    """
    Core service for principle CRUD operations.

    This service handles:
    - Creating new principles
    - Retrieving user principles with filters
    - Basic principle queries


    Source Tag: "principles_core_service_explicit"
    - Format: "principles_core_service_explicit" for user-created relationships
    - Format: "principles_core_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from principles_core metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=PrincipleDTO,
        model_class=Principle,
        domain_name="principles",
        date_field="created_at",
        completed_statuses=(ActivityStatus.ARCHIVED.value,),
    )

    def __init__(self, backend: PrinciplesOperations, event_bus=None) -> None:
        """
        Initialize principles core service.

        Args:
            backend: Protocol-based backend for principle operations
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Created principles trigger PrincipleCreated events which invalidate context.
        """
        super().__init__(backend, "principles.core")
        self.event_bus = event_bus

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Principle entities."""
        return "Principle"

    # ========================================================================
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    def _build_embedding_text(self, principle: Principle) -> str:
        """
        Build text for embedding from principle fields.

        Used for async background embedding generation.
        Includes name, statement, and description for comprehensive semantic search.

        Args:
            principle: Principle domain model

        Returns:
            Text for embedding (name + statement + description)
        """
        parts = [principle.name]
        if principle.statement:
            parts.append(principle.statement)
        if principle.description:
            parts.append(principle.description)
        return "\n".join(parts).strip()

    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, principle: Principle) -> Result[None] | None:
        """
        Validate principle creation with business rules.

        Business Rules:
        1. Principle statement validation: Label must be meaningful (at least 10 characters)
        2. Description validation: Description must be substantial (at least 20 characters)

        Args:
            principle: Principle domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        # Business Rule 1: Statement must be meaningful
        # Principles guide behavior - vague principles aren't useful
        if not principle.statement or len(principle.statement.strip()) < 10:
            return Result.fail(
                Errors.validation(
                    message="Principle statement must be at least 10 characters and meaningful",
                    field="statement",
                    value=principle.statement,
                )
            )

        # Business Rule 2: Description must be substantial (if provided)
        # Forces thoughtful articulation of the principle
        if principle.description and len(principle.description.strip()) < 20:
            return Result.fail(
                Errors.validation(
                    message="Principle description must be at least 20 characters to ensure thoughtful articulation",
                    field="description",
                    value=principle.description,
                )
            )

        return None  # All validations passed

    def _validate_update(self, current: Principle, updates: dict[str, Any]) -> Result[None] | None:
        """
        Validate principle updates with business rules.

        Business Rules:
        1. Label validation: If updating label, must remain meaningful (>= 10 characters)
        2. Description validation: If updating description, must be substantial (>= 20 characters)
        3. Adoption level: Cannot reduce adoption level (principles should grow with practice)
        4. Well-established principles: Require modification reason for principles with adoption >= 80%

        Args:
            current: Current principle state
            updates: Dictionary of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        # Business Rule 1: Label validation on update
        if "label" in updates:
            label = updates["label"]
            if not label or len(str(label).strip()) < 10:
                return Result.fail(
                    Errors.validation(
                        message="Principle label must be at least 10 characters and meaningful",
                        field="label",
                        value=label,
                    )
                )

        # Business Rule 2: Description validation on update
        if "description" in updates:
            description = updates["description"]
            if not description or len(str(description).strip()) < 20:
                return Result.fail(
                    Errors.validation(
                        message="Principle description must be at least 20 characters to ensure thoughtful articulation",
                        field="description",
                        value=description,
                    )
                )

        # Business Rule 3: Strength should not decrease
        # Principles grow with practice - decreasing strength suggests abandonment
        # GRAPH-NATIVE: Uses strength enum, not numeric adoption_level
        strength_order = {"EXPLORING": 1, "DEVELOPING": 2, "MODERATE": 3, "STRONG": 4, "CORE": 5}
        if "strength" in updates:
            current_strength = strength_order.get(current.strength.value, 3)
            new_strength = strength_order.get(updates["strength"], 3)
            if new_strength < current_strength:
                return Result.fail(
                    Errors.validation(
                        message="Cannot reduce principle strength. Principles should grow with practice. "
                        f"Current: {current.strength.value}, Proposed: {updates['strength']}. "
                        "Archive the principle instead if no longer relevant.",
                        field="strength",
                        value=updates["strength"],
                    )
                )

        # Business Rule 4: Core/Strong principles require justification for modification
        # Principles with high strength are core to identity - changes should be intentional
        # GRAPH-NATIVE: Uses strength enum (CORE/STRONG = well-established)
        if current.strength in (PrincipleStrength.CORE, PrincipleStrength.STRONG):
            modifying_core_fields = {"label", "description", "category"}
            if set(updates.keys()) & modifying_core_fields and (
                "modification_reason" not in updates or not updates["modification_reason"]
            ):
                return Result.fail(
                    Errors.validation(
                        message=f"Modifying well-established principles (strength: {current.strength.value}) "
                        "requires a modification_reason field explaining why this core value is changing.",
                        field="modification_reason",
                        value=None,
                    )
                )

        return None  # All validations passed

    # ========================================================================
    # CORE CRUD OPERATIONS
    # ========================================================================

    async def get_principle(self, principle_uid: str) -> Result[Principle]:
        """
        Get a specific principle by UID.

        Uses BaseService.get() which delegates to BackendOperations.get().
        Not found is returned as Result.fail(Errors.not_found(...)).

        Args:
            principle_uid: Principle UID

        Returns:
            Result[Principle] - success contains Principle, not found is an error
        """
        return await self.get(principle_uid)

    @with_error_handling("create_principle", error_type="database")
    async def create_principle(
        self,
        label: str,
        description: str,
        category: PrincipleCategory,
        why_matters: str,
        **kwargs: Any,
    ) -> Result[Principle]:
        """
        Create a new principle.

        Args:
            label: Short name for the principle,
            description: Full description,
            category: Principle category,
            why_matters: Personal importance
            **kwargs: Additional principle fields

        Returns:
            Created principle
        """
        # Extract user_uid from kwargs if provided
        user_uid = kwargs.pop("user_uid", "unknown")  # Use pop to remove from kwargs
        strength = kwargs.get("strength", PrincipleStrength.CORE)

        principle = Principle(
            uid=f"principle_{label.lower().replace(' ', '_')}_{datetime.now().timestamp()}",
            user_uid=user_uid,
            name=label,  # Map label → name
            statement=description,  # Map description → statement
            category=category,
            why_important=why_matters,  # Map why_matters → why_important
            created_at=datetime.now(),
            **kwargs,
        )

        result = await self.backend.create(principle)

        # Check for creation failure before proceeding
        if result.is_error:
            return result

        # Publish PrincipleCreated event (event-driven architecture)
        from core.events import PrincipleCreated

        event = PrincipleCreated(
            principle_uid=principle.uid,
            user_uid=user_uid,
            principle_label=label,
            category=category.value,
            strength=strength.value,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, logger)

        # Publish embedding request event for async background generation (Phase 1 - January 2026)
        # Background worker will process embeddings in batches (zero latency impact on user)
        embedding_text = self._build_embedding_text(principle)
        if embedding_text:
            from core.events import PrincipleEmbeddingRequested

            embedding_event = PrincipleEmbeddingRequested(
                entity_uid=principle.uid,
                entity_type="principle",
                embedding_text=embedding_text,
                user_uid=user_uid,
                requested_at=datetime.now(),
            )
            await publish_event(self.event_bus, embedding_event, logger)

        logger.info(f"Created principle: {label}")
        return result  # backend.create() already returns Result[Principle]

    @with_error_handling("update_principle", error_type="database", uid_param="principle_uid")
    async def update_principle(
        self, principle_uid: str, updates: dict[str, Any]
    ) -> Result[Principle]:
        """
        Update a principle.

        Publishes PrincipleUpdated event, and PrincipleStrengthChanged if strength changes.

        Args:
            principle_uid: UID of the principle
            updates: Dictionary of fields to update

        Returns:
            Result containing updated Principle
        """
        # Get existing principle to detect changes
        existing_result = await self.get_principle(principle_uid)
        if existing_result.is_error:
            return Result.fail(existing_result.expect_error())

        existing = existing_result.value
        if not existing:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))

        old_strength = existing.strength

        # Update in backend
        result = await self.backend.update(principle_uid, updates)
        if result.is_error:
            return result

        updated_principle = result.value

        # Publish PrincipleUpdated event (event-driven architecture)
        from core.events import PrincipleStrengthChanged, PrincipleUpdated

        # General update event
        event = PrincipleUpdated(
            principle_uid=principle_uid,
            user_uid=updated_principle.user_uid,
            updated_fields=updates,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, logger)

        # Strength-specific event if strength changed
        if "strength" in updates and old_strength != updated_principle.strength:
            strength_event = PrincipleStrengthChanged(
                principle_uid=principle_uid,
                user_uid=updated_principle.user_uid,
                old_strength=old_strength.value,
                new_strength=updated_principle.strength.value,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, strength_event, logger)

        logger.info(f"Updated principle: {principle_uid}")
        return Result.ok(updated_principle)

    @with_error_handling("get_user_principles", error_type="database", uid_param="user_uid")
    async def get_user_principles(
        self, user_uid: str, strength_filter: PrincipleStrength | None = None
    ) -> Result[list[Principle]]:
        """
        Get all principles for a user, optionally filtered by strength.

        Args:
            user_uid: User UID,
            strength_filter: Optional strength filter

        Returns:
            List of user's principles
        """
        # Get all principles for user using find_by
        result = await self.backend.find_by(user_uid=user_uid)

        if result.is_error:
            return result

        principles = result.value

        # Filter by strength if requested
        if strength_filter:
            principles = [p for p in principles if p.strength == strength_filter]

        # Sort by priority rank (using to_numeric() method)
        principles.sort(key=get_principle_priority, reverse=True)

        return Result.ok(principles)

    @with_error_handling("get_principles_for_goal", error_type="database", uid_param="goal_uid")
    async def get_principles_for_goal(self, goal_uid: str) -> Result[list[Principle]]:
        """
        Get all principles that guide a specific goal.

        Graph-native query: (goal)-[:GUIDED_BY_PRINCIPLE]->(principle)

        Args:
            goal_uid: Goal UID

        Returns:
            Result containing list of Principles guiding this goal
        """
        # Query graph for principles guiding this goal
        from core.models.relationship_names import RelationshipName

        uids_result = await self.backend.get_related_uids(
            uid=goal_uid,
            relationship_type=RelationshipName.GUIDED_BY_PRINCIPLE,
            direction="outgoing",
            limit=100,
        )

        if uids_result.is_error:
            return Result.fail(uids_result.expect_error())

        principle_uids = uids_result.value

        if not principle_uids:
            return Result.ok([])

        # Fetch full principle entities
        principles = []
        for principle_uid in principle_uids:
            principle_result = await self.get_principle(principle_uid)
            if principle_result.is_ok:
                principles.append(principle_result.value)

        # Sort by strength (core principles first)
        principles.sort(key=get_principle_priority, reverse=True)

        logger.debug(f"Found {len(principles)} principles for goal {goal_uid}")
        return Result.ok(principles)

    @with_error_handling("get_principles_for_habit", error_type="database", uid_param="habit_uid")
    async def get_principles_for_habit(self, habit_uid: str) -> Result[list[Principle]]:
        """
        Get all principles that are aligned with a specific habit.

        Graph-native query: (habit)-[:ALIGNED_WITH_PRINCIPLE]->(principle)

        Args:
            habit_uid: Habit UID

        Returns:
            Result containing list of Principles aligned with this habit
        """
        # Query graph for principles aligned with this habit
        from core.models.relationship_names import RelationshipName

        uids_result = await self.backend.get_related_uids(
            uid=habit_uid,
            relationship_type=RelationshipName.ALIGNED_WITH_PRINCIPLE,
            direction="outgoing",
            limit=100,
        )

        if uids_result.is_error:
            return Result.fail(uids_result.expect_error())

        principle_uids = uids_result.value

        if not principle_uids:
            return Result.ok([])

        # Fetch full principle entities
        principles = []
        for principle_uid in principle_uids:
            principle_result = await self.get_principle(principle_uid)
            if principle_result.is_ok:
                principles.append(principle_result.value)

        # Sort by strength (core principles first)
        principles.sort(key=get_principle_priority, reverse=True)

        logger.debug(f"Found {len(principles)} principles for habit {habit_uid}")
        return Result.ok(principles)

    @with_error_handling("get_user_items_in_range", error_type="database", uid_param="user_uid")
    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Principle]]:
        """
        Get user's principles - standard interface for meta-services.

        This method provides a unified query API for meta-services (Calendar, Reports)
        that need consistent querying across all activity domains.

        Filters principles by:
        - User ownership (user_uid)
        - Adoption date (adopted_date between start_date and end_date)
        - Active status (is_active=True unless include_completed=True)

        ARCHITECTURAL NOTE:
        This method does NOT use BaseService.get_user_items_in_range_base() because
        Principles uses a boolean `is_active` field instead of a status enum.
        The base implementation filters on `n.status IN [...]`, which doesn't apply here.
        This is a legitimate architectural difference - Principles has binary state
        (active/inactive) rather than lifecycle states (pending/active/completed/etc.).

        Note: Principles without an adopted_date will not be included in date-filtered results.
        This is intentional - the query returns principles adopted within a specific timeframe.

        Args:
            user_uid: User UID
            start_date: Filter principles adopted on or after this date
            end_date: Filter principles adopted on or before this date
            include_completed: Include inactive principles (is_active=False)

        Returns:
            Result containing list of Principles

        Example:
            # Get active principles adopted in October 2025
            result = await principles_core.get_user_items_in_range(
                user_uid="user.mike",
                start_date=date(2025, 10, 1),
                end_date=date(2025, 10, 31),
                include_completed=False
            )
        """
        # Build query with custom filtering for is_active field
        # Note: Principles use is_active (bool) instead of status enum
        base_query = """
        MATCH (n:Principle)
        WHERE n.user_uid = $user_uid
          AND n.adopted_date >= date($start_date)
          AND n.adopted_date <= date($end_date)
        """

        # Add is_active filter if not including completed/inactive
        if not include_completed:
            base_query += "  AND n.is_active = true\n"

        base_query += """
        RETURN n
        ORDER BY n.created_at DESC
        LIMIT $limit
        """

        params = {
            "user_uid": user_uid,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "limit": 1000,
        }

        query = base_query

        # Execute query
        results = await self.backend.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Convert to domain models
        principles = []
        for record in results.value:
            principle_data = record.get("n")
            if principle_data:
                dto = PrincipleDTO.from_dict(principle_data)
                principle = Principle.from_dto(dto)
                principles.append(principle)

        self.logger.debug(f"Found {len(principles)} principles for user {user_uid}")

        return Result.ok(principles)

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        DETACH DELETE a principle and publish PrincipleDeleted event.

        Args:
            uid: Principle UID
            cascade: Whether to cascade DETACH DELETE

        Returns:
            Result indicating success
        """
        # Get principle details before deletion for event publishing
        principle_result = await self.get_principle(uid)
        if principle_result.is_error:
            return Result.fail(principle_result.expect_error())

        principle = principle_result.value

        # Call parent delete
        result = await super().delete(uid, cascade=cascade)

        # Publish PrincipleDeleted event
        if result.is_ok:
            from core.events import PrincipleDeleted

            event = PrincipleDeleted(
                principle_uid=uid,
                user_uid=principle.user_uid,
                principle_label=principle.name,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result
