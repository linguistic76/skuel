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

from core.events import publish_event
from core.events.embedding_publisher import publish_embedding_requested
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.principle_enums import PrincipleStrength
from core.models.principle.principle import Principle, get_principle_priority
from core.models.principle.principle_dto import PrincipleDTO
from core.models.principle.principle_request import PrincipleCreateRequest
from core.models.principle.principle_types import PrincipleExpression
from core.models.principle.principle_update_intent import PrincipleUpdateIntent
from core.models.type_hints import UserUID
from core.ports.domain_protocols import PrinciplesOperations
from core.ports.query_types import PrincipleStats
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class PrinciplesCoreService(
    HierarchyReadMixin[PrinciplesOperations, Principle],
    BaseService[PrinciplesOperations, Principle, PrincipleUpdateIntent],
):
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

    # No _validate_create hook: Principles have no creation-time business rule.
    #
    # There were two — statement >= 10 chars, description >= 20 chars — but at the time
    # they were deleted (#963) neither had ever executed: create_principle then persisted
    # backend-direct, bypassing CrudOperationsMixin.create, the hook's only caller. Both
    # doors now run that caller (see ``create`` below), so the hook is reachable and
    # resolves to the inherited no-op BY CHOICE, not by accident — both rules were
    # stricter than the contract the edge actually publishes:
    #   - PrincipleCreateRequest declares statement min_length=1, deliberately; a short
    #     principle ("Be kind") is a legitimate one
    #   - the Activity DSL sets statement = the whole activity description, so any short
    #     @context(principle) line would have started being refused
    #
    # Length bounds on statement/description are the request model's to state
    # (min_length/max_length), not this layer's.

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
        casing never matches; Rule 4's ``modification_reason`` field exists nowhere). Reform
        (or deletion per the create-rules precedent above) is tracked live in
        ``docs/roadmap/deferred-work.md`` § Principles ``_validate_update`` Reform; the hook
        is retained for the base ``update`` contract and reads ``updates.to_changes()`` to
        stay type-consistent.

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

    async def create(self, entity: Principle) -> Result[Principle]:
        """Persist, then announce — THE create primitive for Principles.

        Both doors land here: the entity door (``PrinciplesService.create``) and
        ``create_principle`` below — which the generated CRUD route enters through,
        since it was bound to the request door (``CRUDRouteConfig.request_create_method``). Before this, only ``create_principle`` published
        anything, so a principle created through ``POST /api/principles/create``
        invalidated no user context and was never embedded — the route calls
        ``service.create(entity)`` on the FACADE, which resolved to
        ``CrudOperationsMixin.create`` and went straight to ``backend.create``.

        Principles declare no ``_validate_create`` hook (see the comment above
        ``_validate_update`` — both rules were deleted in #963 as stricter than
        ``PrincipleCreateRequest``'s deliberate ``min_length=1``), so unlike Goals,
        Habits, Events and Choices there is no validation to reach here. What this
        primitive reconciles is the EVENT half.

        No ordering split (``_create_validated`` / ``_publish_created``) as Choices and
        Tasks need: ``create_principle`` writes no graph edges after persisting, so there
        is nothing the context rebuild could observe too early.

        Args:
            entity: Principle to create

        Returns:
            Result containing created Principle

        Events Published:
            - PrincipleCreated: when the principle is successfully created
            - PrincipleEmbeddingRequested (ADR-074): post-persist embedding refresh
        """
        result: Result[Principle] = await super().create(entity)
        if result.is_error:
            return result

        principle = result.value

        from core.events import PrincipleCreated

        event = PrincipleCreated(
            principle_uid=principle.uid,
            user_uid=principle.user_uid,
            principle_label=principle.title,
            # principle_category and strength are nullable on the MODEL while
            # PrincipleCreated declares both as non-optional str. PrincipleCreateRequest
            # defaults them, so the request door always fills them in — but this
            # primitive now runs for hand-built entities too (the entity door, the
            # DSL's short "@context(principle)" lines), where a bare ``.value`` raises.
            category=principle.principle_category.value if principle.principle_category else "",
            strength=principle.strength.value if principle.strength else "",
        )
        await publish_event(self.event_bus, event, logger)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.PRINCIPLE, principle, logger)

        return result

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

        expressions = tuple(
            PrincipleExpression(context=e.context, behavior=e.behavior, example=e.example)
            for e in request.expressions
        )

        principle = Principle(
            uid=UIDGenerator.generate_random_uid("principle"),
            user_uid=user_uid,
            title=request.title,
            statement=request.statement,
            description=request.description,
            principle_category=request.principle_category,
            principle_source=request.principle_source,
            strength=request.strength,
            tradition=request.tradition,
            original_source=request.original_source,
            personal_interpretation=request.personal_interpretation,
            why_important=request.why_important,
            origin_story=request.origin_story,
            key_behaviors=tuple(request.key_behaviors),
            expressions=expressions,
            priority=request.priority,
            tags=tuple(request.tags),
            created_at=datetime.now(),
        )

        # Persist and announce through the one primitive the entity door also reaches
        # (see ``create``). NOT backend.create directly, which is what left the
        # generated route publishing nothing.
        result = await self.create(principle)
        if result.is_error:
            return result

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
        Reforming ``_validate_update`` onto the intent is tracked live in
        ``docs/roadmap/deferred-work.md`` § Principles ``_validate_update`` Reform (extracted
        from the archived ``docs/roadmap/done/update-intents.md`` Phase-7 notes); until then
        this path preserves exact behavior.

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
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
        date_field: str | list[str] | None = None,
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
            date_field: Unsupported here — Principles always range on adoption
                date via its is_active backend path (fails fast if provided)

        Returns:
            Result containing list of Principles
        """
        if date_field is not None:
            return Result.fail(
                Errors.validation(
                    message="PrinciplesService does not support a date_field override; "
                    "principles always range on their adoption date",
                    field="date_field",
                )
            )
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
        Delete a principle and publish PrincipleDeleted event.

        Args:
            uid: Principle UID
            cascade: Whether to cascade delete

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
