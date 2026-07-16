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
from core.events.embedding_publisher import publish_embedding_requested
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.principle_enums import PrincipleStrength
from core.models.principle.principle import Principle, merge_why_important
from core.models.principle.principle_dto import PrincipleDTO
from core.models.principle.principle_request import PrincipleCreateRequest
from core.models.principle.principle_types import PrincipleExpression
from core.models.principle.principle_update_intent import PrincipleUpdateIntent
from core.models.type_hints import EntityUID, UserUID
from core.ports.domain_protocols import PrinciplesOperations
from core.ports.query_types import PrincipleStats
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_principle_priority

logger = get_logger(__name__)


class PrinciplesCoreService(BaseService[PrinciplesOperations, Principle, PrincipleUpdateIntent]):
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

    def _validate_create(self, principle: Principle) -> Result[None]:
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

        return Result.ok(None)  # All validations passed

    def _validate_update(self, current: Principle, updates: PrincipleUpdateIntent) -> Result[None]:
        """
        Validate principle updates with business rules.

        Business Rules:
        1. Label validation: If updating label, must remain meaningful (>= 10 characters)
        2. Description validation: If updating description, must be substantial (>= 20 characters)
        3. Adoption level: Cannot reduce adoption level (principles should grow with practice)
        4. Well-established principles: Require modification reason for principles with adoption >= 80%

        Note: ``update_principle`` is backend-direct and does not invoke this hook (the
        rules are stale — Rule 1 keys on ``label`` not ``title``; Rule 3's ``strength_order``
        casing never matches; Rule 4's ``modification_reason`` field exists nowhere). Reforming
        these rules onto the intent is tracked separately; the hook is retained for the base
        ``update`` contract and reads ``updates.to_changes()`` to stay type-consistent.

        Args:
            current: Current principle state
            updates: Typed ``PrincipleUpdateIntent`` of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        assert isinstance(current, Principle)
        changes = updates.to_changes()
        # Business Rule 1: Label validation on update
        if "label" in changes:
            label = changes["label"]
            if not label or len(str(label).strip()) < 10:
                return Result.fail(
                    Errors.validation(
                        message="Principle label must be at least 10 characters and meaningful",
                        field="label",
                        value=label,
                    )
                )

        # Business Rule 2: Description validation on update
        if "description" in changes:
            description = changes["description"]
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
        if "strength" in changes:
            current_rank = PrincipleStrength.from_value(
                current.strength if current.strength else PrincipleStrength.MODERATE
            ).rank()
            new_rank = PrincipleStrength.from_value(changes["strength"]).rank()
            if new_rank < current_rank:
                return Result.fail(
                    Errors.validation(
                        message="Cannot reduce principle strength. Principles should grow with practice. "
                        f"Current: {current.strength.value if current.strength else 'unknown'}, Proposed: {changes['strength']}. "
                        "Archive the principle instead if no longer relevant.",
                        field="strength",
                        value=changes["strength"],
                    )
                )

        # Business Rule 4: Core/Strong principles require justification for modification
        # Principles with high strength are core to identity - changes should be intentional
        # GRAPH-NATIVE: Uses strength enum (CORE/STRONG = well-established)
        if current.strength in (PrincipleStrength.CORE, PrincipleStrength.STRONG):
            modifying_core_fields = {"label", "description", "category"}
            if set(changes.keys()) & modifying_core_fields and (
                "modification_reason" not in changes or not changes["modification_reason"]
            ):
                strength_label = current.strength.value if current.strength else "unknown"
                return Result.fail(
                    Errors.validation(
                        message=f"Modifying well-established principles (strength: {strength_label}) "
                        "requires a modification_reason field explaining why this core value is changing.",
                        field="modification_reason",
                        value=None,
                    )
                )

        return Result.ok(None)  # All validations passed

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
        self, request: PrincipleCreateRequest, user_uid: UserUID
    ) -> Result[Principle]:
        """
        Create a principle from a validated request.

        Args:
            request: Validated PrincipleCreateRequest
            user_uid: User UID (REQUIRED — fail-fast on missing)

        Returns:
            Result containing created Principle
        """
        validation = self._validate_required_user_uid(user_uid, "principle creation")
        if validation.is_error:
            return Result.fail(validation)

        from core.utils.uid_generator import UIDGenerator

        body = merge_why_important(request.description, request.why_important)

        expressions = tuple(
            PrincipleExpression(context=e.context, behavior=e.behavior, example=e.example)
            for e in request.expressions
        )

        principle = Principle(
            uid=UIDGenerator.generate_random_uid("principle"),
            user_uid=user_uid,
            title=request.title,
            statement=request.statement,
            description=body,
            principle_category=request.principle_category,
            principle_source=request.principle_source,
            strength=request.strength,
            tradition=request.tradition,
            original_source=request.original_source,
            personal_interpretation=request.personal_interpretation,
            origin_story=request.origin_story,
            key_behaviors=tuple(request.key_behaviors),
            expressions=expressions,
            priority=request.priority,
            tags=tuple(request.tags),
            created_at=datetime.now(),
        )

        result = await self.backend.create(principle)
        if result.is_error:
            return result

        from core.events import PrincipleCreated

        event = PrincipleCreated(
            principle_uid=principle.uid,
            user_uid=user_uid,
            principle_label=request.title,
            category=request.principle_category.value,
            strength=request.strength.value,
        )
        await publish_event(self.event_bus, event, logger)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.PRINCIPLE, principle, logger)

        logger.info(f"Created principle: {request.title}")
        return result

    @with_error_handling("update_principle", error_type="database", uid_param="principle_uid")
    async def update_principle(
        self, principle_uid: str, intent: PrincipleUpdateIntent
    ) -> Result[Principle]:
        """Update a principle's node properties (ADR-066 typed update contract).

        Materializes the intent to a partial patch once, writes it at the single
        ``backend.update`` seam, then publishes ``PrincipleUpdated`` (and
        ``PrincipleStrengthChanged`` if strength changed).

        Backend-direct (like ``TasksCoreService.update_task``), **not** ``super().update``:
        Principles' inherited ``_validate_update`` is stale — its rules reference fields
        that no longer match the schema (``label``/``category`` are not columns; the
        ``strength`` rule compares uppercase keys against lowercase enum values so it never
        fires; the well-established-principle rule demands a ``modification_reason`` field
        that exists nowhere, making it unsatisfiable). The only caller that reaches it
        (``principles_api`` via ``core.update``) sends ``{"status": ...}``, which triggers
        no rule. Routing through ``super().update`` would activate the unsatisfiable
        modification-reason gate and block CORE/STRONG description edits — a regression.
        Reforming ``_validate_update`` onto the intent is Phase-7 work (see
        ``docs/roadmap/update-intents.md``); until then this path preserves exact behavior.

        Args:
            principle_uid: UID of the principle
            intent: Typed ``PrincipleUpdateIntent`` — only its set fields are written

        Returns:
            Result containing updated Principle

        Events Published:
            - PrincipleUpdated: when any field changes (so user-context caches invalidate)
            - PrincipleStrengthChanged: when the strength field transitions
        """
        # Get existing principle (not-found guard + old strength for the change event)
        existing_result = await self.get_principle(principle_uid)
        if existing_result.is_error:
            return Result.fail(existing_result)

        existing = existing_result.value
        if not existing:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))
        assert isinstance(existing, Principle)

        old_strength = existing.strength

        changes = intent.to_changes()
        # Snapshot the intended fields now: the backend stamps updated_at in place, so
        # reading the dict after the write would leak that bump into the event payload.
        updated_fields = dict(changes)

        result = await self.backend.update(principle_uid, changes)
        if result.is_error:
            return result

        updated_principle = result.value
        assert isinstance(updated_principle, Principle)

        if not updated_fields:
            return Result.ok(updated_principle)

        # Publish PrincipleUpdated event (event-driven architecture)
        from core.events import PrincipleStrengthChanged, PrincipleUpdated

        # General update event
        event = PrincipleUpdated(
            principle_uid=principle_uid,
            user_uid=updated_principle.user_uid,
            updated_fields=updated_fields,
        )
        await publish_event(self.event_bus, event, logger)

        # Strength-specific event if strength changed
        if "strength" in changes and old_strength != updated_principle.strength:
            strength_event = PrincipleStrengthChanged(
                principle_uid=principle_uid,
                user_uid=updated_principle.user_uid,
                old_strength=old_strength.value if old_strength else "unknown",
                new_strength=updated_principle.strength.value
                if updated_principle.strength
                else "unknown",
            )
            await publish_event(self.event_bus, strength_event, logger)

        # Post-persist embedding refresh (ADR-074) — only when a text field changed
        await publish_embedding_requested(
            self.event_bus,
            EntityType.PRINCIPLE,
            updated_principle,
            logger,
            changed_fields=updated_fields,
        )

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

    # get_for_user_filtered: inherited from SearchOperationsMixin. Principles
    # configures no status_filters, so every call returns all of the user's
    # principles (category/strength filtering stays Python-side).
