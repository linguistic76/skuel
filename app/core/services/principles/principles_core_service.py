"""
Principles Core Service
=======================

Handles core CRUD operations for principles.

Responsibilities:
- Create principles
- Get user principles
- Basic principle queries
- Principle filtering

Part of the PrinciplesService decomposition.
"""

from datetime import date, datetime
from typing import Any

from core.events import publish_event
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.principle_enums import PrincipleCategory, PrincipleStrength
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.models.type_hints import EntityUID, UserUID
from core.ports.domain_protocols import PrinciplesOperations
from core.ports.query_types import PrincipleStats
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.utils.decorators import with_error_handling
from core.utils.embedding_text_builder import build_embedding_text
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
    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=PrincipleDTO,
        model_class=Principle,
        domain_name="principles",
        date_field="created_at",
        completed_statuses=(EntityStatus.ARCHIVED.value,),
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
        assert isinstance(principle, Principle)
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
        assert isinstance(current, Principle)
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
            current_strength = strength_order.get(
                current.strength.value if current.strength else "MODERATE", 3
            )
            new_strength = strength_order.get(updates["strength"], 3)
            if new_strength < current_strength:
                return Result.fail(
                    Errors.validation(
                        message="Cannot reduce principle strength. Principles should grow with practice. "
                        f"Current: {current.strength.value if current.strength else 'unknown'}, Proposed: {updates['strength']}. "
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

        from core.utils.uid_generator import UIDGenerator

        principle = Principle(
            uid=UIDGenerator.generate_random_uid("principle"),
            user_uid=user_uid,
            title=label,  # Map label → title
            statement=description,  # Map description → statement
            principle_category=category,
            description=why_matters,  # Map why_matters → description (why it matters)
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
        )
        await publish_event(self.event_bus, event, logger)

        # Publish embedding request event for async background generation
        # Background worker will process embeddings in batches (zero latency impact on user)
        embedding_text = build_embedding_text(EntityType.PRINCIPLE, principle)
        if embedding_text:
            from core.events import PrincipleEmbeddingRequested

            now = datetime.now()
            embedding_event = PrincipleEmbeddingRequested(
                entity_uid=principle.uid,
                entity_type="principle",
                embedding_text=embedding_text,
                user_uid=user_uid,
                requested_at=now,
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
            return Result.fail(existing_result)

        existing = existing_result.value
        if not existing:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))
        assert isinstance(existing, Principle)

        old_strength = existing.strength

        # Update in backend
        result = await self.backend.update(principle_uid, updates)
        if result.is_error:
            return result

        updated_principle = result.value
        assert isinstance(updated_principle, Principle)

        # Publish PrincipleUpdated event (event-driven architecture)
        from core.events import PrincipleStrengthChanged, PrincipleUpdated

        # General update event
        event = PrincipleUpdated(
            principle_uid=principle_uid,
            user_uid=updated_principle.user_uid,
            updated_fields=updates,
        )
        await publish_event(self.event_bus, event, logger)

        # Strength-specific event if strength changed
        if "strength" in updates and old_strength != updated_principle.strength:
            strength_event = PrincipleStrengthChanged(
                principle_uid=principle_uid,
                user_uid=updated_principle.user_uid,
                old_strength=old_strength.value if old_strength else "unknown",
                new_strength=updated_principle.strength.value
                if updated_principle.strength
                else "unknown",
            )
            await publish_event(self.event_bus, strength_event, logger)

        logger.info(f"Updated principle: {principle_uid}")
        return Result.ok(updated_principle)

    @with_error_handling("get_user_principles", error_type="database", uid_param="user_uid")
    async def get_user_principles(self, user_uid: UserUID) -> Result[list[Principle]]:
        """
        Get all principles for a user.

        Args:
            user_uid: User UID

        Returns:
            List of user's principles sorted by priority
        """
        result = await self.backend.find_by(user_uid=user_uid)

        if result.is_error:
            return result

        principles: list[Principle] = [p for p in result.value if isinstance(p, Principle)]
        principles.sort(key=get_principle_priority, reverse=True)

        return Result.ok(principles)

    @with_error_handling("get_user_items_in_range", error_type="database", uid_param="user_uid")
    async def get_user_items_in_range(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Principle]]:
        """Get user's principles adopted within a date range.

        Unified interface for meta-services (Calendar, Reports) that query across
        all activity domains. Delegates Cypher to PrinciplesBackend, which uses
        is_active (bool) filtering instead of the status-enum approach used by
        other activity domains.

        Args:
            user_uid: User UID
            start_date: Filter principles adopted on or after this date
            end_date: Filter principles adopted on or before this date
            include_completed: Include inactive principles (is_active=False)

        Returns:
            Result containing list of Principles
        """
        result = await self.backend.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=include_completed,
        )
        if result.is_error:
            return Result.fail(result)
        self.logger.debug(f"Found {len(result.value)} principles for user {user_uid}")
        return result

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
            return Result.fail(principle_result)

        principle = principle_result.value
        if not principle:
            return Result.fail(Errors.not_found(resource="Principle", identifier=uid))

        # Call parent delete
        result = await super().delete(uid, cascade=cascade)

        # Publish PrincipleDeleted event
        if result.is_ok:
            from core.events import PrincipleDeleted

            event = PrincipleDeleted(
                principle_uid=uid,
                user_uid=principle.user_uid,
                principle_label=principle.title,
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Flat UID, Rich Structure)
    # Delegated to PrinciplesBackend via _HierarchyMixin (2026-03-24)
    # ========================================================================

    @with_error_handling("get_subprinciples", error_type="database", uid_param="parent_uid")
    async def get_subprinciples(self, parent_uid: str, depth: int = 1) -> Result[list[Principle]]:
        """Get all subprinciples of a parent principle at the given depth."""
        result = await self.backend.get_children_raw(parent_uid, depth)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [self._to_domain_model(data, PrincipleDTO, Principle) for data in result.value]
        )

    @with_error_handling(
        "get_parent_principle", error_type="database", uid_param="subprinciple_uid"
    )
    async def get_parent_principle(self, subprinciple_uid: str) -> Result[Principle | None]:
        """Get immediate parent of a subprinciple (if any)."""
        result = await self.backend.get_parent_raw(subprinciple_uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.ok(None)
        return Result.ok(self._to_domain_model(result.value, PrincipleDTO, Principle))

    @with_error_handling(
        "get_principle_hierarchy", error_type="database", uid_param="principle_uid"
    )
    async def get_principle_hierarchy(self, principle_uid: str) -> Result[dict[str, Any]]:
        """Get full hierarchy context: ancestors, current, siblings, children, depth."""
        current_result = await self.backend.get(principle_uid)
        if current_result.is_error:
            return Result.fail(current_result)
        current_principle = self._to_domain_model(current_result.value, PrincipleDTO, Principle)

        hierarchy_result = await self.backend.get_hierarchy_raw(EntityUID(principle_uid))
        if hierarchy_result.is_error:
            return Result.fail(hierarchy_result)

        raw = hierarchy_result.value
        return Result.ok(
            {
                "ancestors": [
                    self._to_domain_model(n, PrincipleDTO, Principle) for n in raw["ancestors"]
                ],
                "current": current_principle,
                "siblings": [
                    self._to_domain_model(n, PrincipleDTO, Principle) for n in raw["siblings"]
                ],
                "children": [
                    self._to_domain_model(n, PrincipleDTO, Principle) for n in raw["children"]
                ],
                "depth": len(raw["ancestors"]),
            }
        )

    async def create_subprinciple_relationship(
        self, parent_uid: str, subprinciple_uid: str, order: int = 0, importance: str = "supporting"
    ) -> Result[bool]:
        """Create bidirectional HAS_SUBPRINCIPLE/SUBPRINCIPLE_OF relationship with cycle detection."""
        return await self.backend.create_hierarchy_relationship(
            parent_uid, subprinciple_uid, {"order": order, "importance": importance}
        )

    async def remove_subprinciple_relationship(
        self, parent_uid: str, subprinciple_uid: str
    ) -> Result[bool]:
        """Remove bidirectional HAS_SUBPRINCIPLE/SUBPRINCIPLE_OF relationship."""
        return await self.backend.remove_hierarchy_relationship(parent_uid, subprinciple_uid)

    # ========================================================================
    # QUERY LAYER — Cypher-level filtering for get_filtered_context
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[PrincipleStats]:
        """Count principle stats via Cypher COUNT — no entity deserialization."""
        return await self.backend.get_stats_for_user(user_uid)

    async def get_for_user_filtered(self, user_uid: UserUID) -> Result[list[Principle]]:
        """Fetch all principles for user (category/strength filtering stays Python-side)."""
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return result
        return Result.ok(self._to_domain_models(result.value, PrincipleDTO, Principle))
