"""
Goals Core Service
==================

Handles basic CRUD operations for goals.

Responsibilities:
- Basic goal retrieval (get_user_goals)
- Delegates create/update/delete to backend via BaseService
- Publishes domain events (GoalCreated, GoalUpdated, GoalAchieved, GoalAbandoned).
  GoalProgressUpdated is owned by GoalsProgressService (progress-propagation provenance).

  RelationshipRegistry (GOAPS_CONFIG). Shared-neighbor pattern for
  related_goals is now defined in the registry.
  See: /core/models/relationship_registry.py
- v2.1.0 (2025-11-28): Eliminated APOC dependency.
- v2.0.0 (2025-11-05): Initial facade pattern implementation
"""

import dataclasses
from datetime import date, datetime
from typing import TYPE_CHECKING

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.models.goal.goal_request import GoalCreateRequest

from core.events import publish_event
from core.events.embedding_publisher import publish_embedding_requested
from core.events.goal_events import (
    GoalAbandoned,
    GoalAchieved,
    GoalCreated,
    GoalUpdated,
)
from core.models.enums import EntityStatus
from core.models.enums.entity_enums import EntityType
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.ports import get_enum_value
from core.ports.domain_protocols import GoalsOperations
from core.ports.query_types import GoalStats
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator


class GoalsCoreService(
    HierarchyReadMixin[GoalsOperations, Goal],
    BaseService[GoalsOperations, Goal, GoalUpdateIntent],
):
    """
    Core CRUD operations for goals.

    This service provides basic goal operations:
    - get_user_goals: Retrieve all goals for a user
    - Inherits: create, get, update, delete from BaseService
    - Publishes domain events for all state changes

    Event-Driven Architecture:
    - Publishes GoalCreated on creation
    - Publishes GoalUpdated on every property update (cache invalidation)
    - Publishes GoalAchieved when goal completed
    - Publishes GoalAbandoned when goal cancelled
    """

    def __init__(
        self,
        backend: GoalsOperations,
        event_bus=None,
    ) -> None:
        """
        Initialize goals core service.

        Args:
            backend: Protocol-based backend for goal operations
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "goals")
        self.logger = get_logger("skuel.services.goals.core")  # type: ignore[assignment]  # structlog BoundLogger
        self.event_bus = event_bus

    # ========================================================================
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=GoalDTO,
        model_class=Goal,
        domain_name="goals",
        date_field="target_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        status_filters={
            "active": {"status": "active"},
            "completed": {"status": "completed"},
            "paused": {"status": "paused"},
        },
        entity_label="Entity",
    )
    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, goal: Goal) -> Result[None]:
        """
        Validate goal creation with business rules.

        Business Rules:
        1. Target date must not precede start date (timeline consistency)

        A same-day goal is legal. ``GoalCreateRequest`` validates the same pair with
        ``validate_date_after("target_date", "start_date", allow_equal=True)`` and defaults
        ``start_date`` to ``date.today()``, so "finish this today" is a shape the API
        deliberately accepts; this hook rejected it until the rule was reachable, which
        would have made the two layers disagree the moment it started running.

        Args:
            goal: Goal domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """

        # Business Rule: Target date must not precede start date (equal is allowed —
        # same bound as the request model's allow_equal=True).
        if goal.target_date and goal.start_date and goal.target_date < goal.start_date:
            return Result.fail(
                Errors.validation(
                    message="Target date cannot be before start date",
                    field="target_date",
                    value=goal.target_date.isoformat(),
                )
            )

        return Result.ok(None)  # All validations passed

    def _validate_update(self, current: Goal, updates: GoalUpdateIntent) -> Result[None]:
        """
        Validate goal updates with business rules.

        Business Rules:
        1. Achievement state immutability: Cannot modify achieved goals
        2. Target date validation: If updating dates, target must be after start

        Note: Goal abandonment protection (checking for active tasks) is handled
        in the update() method since it requires async relationship queries.

        Args:
            current: Current goal state
            updates: Typed ``GoalUpdateIntent`` of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        changes = updates.to_changes()

        # Business Rule 1: Achievement state immutability
        # Achieved goals are historical records - modifying them corrupts progress tracking
        if current.status == EntityStatus.COMPLETED:
            return Result.fail(
                Errors.validation(
                    message="Cannot modify achieved goals - they are historical records",
                    field="status",
                    value=current.status.value,
                )
            )

        # Business Rule 2: Target date validation (if both dates present)
        # Check if we're updating either date field
        if "target_date" in changes or "start_date" in changes:
            # Determine new values (use updated value if present, else current)
            new_target = changes.get("target_date", current.target_date)
            new_start = changes.get("start_date", current.start_date)

            # Both must be present and target must be after start
            if new_target and new_start:
                # Handle both date objects and ISO strings
                if isinstance(new_target, str):
                    from datetime import date as date_type

                    new_target = date_type.fromisoformat(new_target)
                if isinstance(new_start, str):
                    from datetime import date as date_type

                    new_start = date_type.fromisoformat(new_start)

                if new_target <= new_start:
                    return Result.fail(
                        Errors.validation(
                            message="Target date must be after start date",
                            field="target_date",
                            value=str(new_target),
                        )
                    )

        return Result.ok(None)  # All validations passed

    # ========================================================================
    # READ OPERATIONS WITH GRAPH CONTEXT
    # ========================================================================
    # NOTE: get_with_context() is inherited from BaseService (January 2026)
    #
    # Uses registry-driven query generation from RelationshipRegistry.
    # The GOAPS_CONFIG config includes:
    # - contributing_tasks, contributing_habits (supporting activities)
    # - sub_goals, parent_goal (hierarchy)
    # - required_knowledge, aligned_principles (prerequisites and guidance)
    # - inspired_by_choice (motivation)
    # - milestones (progress tracking)
    # - related_goals (shared-neighbor pattern via FULFILLS_GOAL|SUPPORTS_GOAL)
    # - milestone_progress (calculated in BaseService._parse_context_result)
    #
    # See: /core/models/relationship_registry.py - GOAPS_CONFIG
    # See: /core/services/base_service.py - get_with_context()
    # ========================================================================

    async def get_goal(self, goal_uid: str) -> Result[Goal]:
        """
        Get a specific goal by UID.

        Uses BaseService.get() which delegates to BackendOperations.get().
        Not found is returned as Result.fail(Errors.not_found(...)).

        Args:
            goal_uid: Goal UID

        Returns:
            Result[Goal] - success contains Goal, not found is an error
        """
        return await self.get(goal_uid)

    async def get_user_goals(self, user_uid: UserUID) -> Result[list[Goal]]:
        """
        Get all goals for a user, including learning relationships.

        Args:
            user_uid: User identifier

        Returns:
            Result containing list of Goal domain models
        """
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return result

        # Convert to enriched Goal models using helper
        goals = self._to_domain_models(result.value, GoalDTO, Goal)

        self.logger.info(f"Retrieved {len(goals)} goals for user {user_uid}")
        return Result.ok(goals)

    # get_user_items_in_range() is now inherited from BaseService
    # Configured via class attributes: _date_field, _completed_statuses, _dto_class, _model_class
    # CONSOLIDATED (November 27, 2025) - Removed 45 lines of duplicate code

    # ========================================================================
    # EVENT-DRIVEN CRUD OPERATIONS
    # ========================================================================

    async def create(self, entity: Goal) -> Result[Goal]:
        """Validate, persist, then announce — THE create primitive for Goals.

        Both doors land here: the generated CRUD route (via ``GoalsService.create``) and
        ``create_goal``. ``super().create`` runs ``_validate_create`` (timeline
        consistency), so the rule cannot be reached by one door and missed by the other.

        Args:
            entity: Goal to create

        Returns:
            Result containing created Goal

        Events Published:
            - GoalCreated: when the goal is successfully created
            - GoalEmbeddingRequested (ADR-074): post-persist embedding refresh. Fired here
              rather than in ``create_goal`` so route-created goals are embedded too —
              they previously were not.
        """
        result: Result[Goal] = await super().create(entity)
        if result.is_error:
            return result

        goal: Goal = result.value  # Type hint to help MyPy
        event = GoalCreated(
            goal_uid=goal.uid,
            user_uid=goal.user_uid,
            title=goal.title,
            domain=get_enum_value(goal.domain) if goal.domain else None,
            target_date=datetime.combine(goal.target_date, datetime.min.time())
            if goal.target_date
            else None,
        )
        await publish_event(self.event_bus, event, self.logger)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.GOAL, goal, self.logger)

        return result

    async def create_goal(
        self, goal_request: "GoalCreateRequest", user_uid: UserUID
    ) -> Result[Goal]:
        """
        Create a goal from a request with user_uid.

        Args:
            goal_request: Goal creation request
            user_uid: User UID (REQUIRED - fail-fast on None)

        Returns:
            Result containing created Goal

        Builds the entity with the SAME converter the generated CRUD route uses, then
        hands it to the one create primitive. The previous hand-listed ``GoalDTO(...)``
        silently dropped six request fields the route door kept — ``potential_obstacles``,
        ``strategies``, ``success_criteria``, ``tags``, ``unit_of_measurement`` and
        ``why_important`` — so the two doors persisted different goals from one request.

        Still not carried by EITHER door, because they are not ``Goal`` properties:
        ``progress_weight`` and the three edge-typed uid lists (``required_knowledge_uids``,
        ``supporting_habit_uids``, ``guiding_principle_uids``). ``progress_weight`` belongs
        on the HAS_SUBGOAL edge — see ``create_subgoal_relationship``, which Tasks' create
        path calls and this one does not yet.
        """
        # Validate user_uid (uses BaseService helper)
        validation = self._validate_required_user_uid(user_uid, "goal creation")
        if validation.is_error:
            return Result.fail(validation)

        from core.services.conversion_service import ConversionServiceV2

        # status=ACTIVE so the goal appears in the default list view; the request
        # carries no status field, so this is the door's contribution, not a default
        # the converter could supply.
        goal = ConversionServiceV2.goal_create_to_pure(
            goal_request,
            UIDGenerator.generate_random_uid("goal"),
            user_uid=user_uid,
            status=EntityStatus.ACTIVE,
        )
        return await self.create(goal)

    @with_error_handling("update_goal", error_type="database", uid_param="uid")
    async def update_goal(self, uid: str, intent: GoalUpdateIntent) -> Result[Goal]:
        """Update a goal's node properties (ADR-066 typed update contract).

        Materializes the intent to a partial patch once, validated and written through the
        inherited CRUD ``update`` (BaseService → ``_validate_update`` → ``backend.update``),
        then publishes domain events. Goals carry no edge fields on the update path, so the
        intent's ``to_changes()`` is written wholesale — there is nothing to split off.

        Args:
            uid: Goal UID
            intent: Typed ``GoalUpdateIntent`` — only its set fields are written

        Returns:
            Result containing updated Goal

        Events Published:
            - GoalUpdated: always, so user-context caches invalidate even for plain
              property edits (title / description / target_date) with no more specific event
            - GoalAchieved: if status transitions into COMPLETED

        (Manual / system progress changes fire ``GoalProgressUpdated`` from
        ``GoalsProgressService``, which owns the progress-propagation provenance.)
        """
        changes = intent.to_changes()
        # Capture the intended fields now: the backend stamps updated_at in place, so
        # reading changes.keys() after the write would leak that bump into the event.
        updated_fields = list(changes.keys())

        # Fetch the prior goal only when a status transition needs old-vs-new comparison.
        old_goal: Goal | None = None
        if "status" in changes:
            current_result = await self.get(uid)
            if current_result.is_ok:
                old_goal = current_result.value

        result: Result[Goal] = await super().update(uid, intent)
        if result.is_error:
            return result

        goal: Goal = result.value

        # GoalUpdated: always fired (cache invalidation contract).
        await publish_event(
            self.event_bus,
            GoalUpdated(goal_uid=goal.uid, user_uid=goal.user_uid, updated_fields=updated_fields),
            self.logger,
        )

        # GoalAchieved: status transitioned into COMPLETED.
        if "status" in changes and old_goal is not None:
            old_status = get_enum_value(old_goal.status)  # Handle both enum and string
            if (
                changes["status"] == EntityStatus.COMPLETED.value
                and old_status != EntityStatus.COMPLETED.value
            ):
                actual_duration_days = (
                    (datetime.now() - goal.created_at).days if goal.created_at else None
                )
                await publish_event(
                    self.event_bus,
                    GoalAchieved(
                        goal_uid=goal.uid,
                        user_uid=goal.user_uid,
                        actual_duration_days=actual_duration_days,
                    ),
                    self.logger,
                )

        # Post-persist embedding refresh (ADR-074) — only when a text field changed
        await publish_embedding_requested(
            self.event_bus, EntityType.GOAL, goal, self.logger, changed_fields=updated_fields
        )

        return result

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        Delete (abandon) a goal and publish GoalAbandoned event.

        Args:
            uid: Goal UID
            cascade: Whether to cascade delete (default False)

        Returns:
            Result indicating success

        Events Published:
            - GoalAbandoned: When goal is successfully deleted
        """
        # Get goal details before deletion for event publishing
        goal_result = await self.get(uid)
        if goal_result.is_error:
            return Result.fail(goal_result)

        goal = goal_result.value

        # Call parent delete
        result = await super().delete(uid, cascade=cascade)

        # Publish GoalAbandoned event
        if result.is_ok:
            progress_at_abandonment = getattr(goal, "progress", 0.0) or 0.0

            # Calculate days active
            days_active = 0
            if goal.created_at:
                days_active = (datetime.now() - goal.created_at).days

            event = GoalAbandoned(
                goal_uid=uid,
                user_uid=goal.user_uid,
                progress_at_abandonment=progress_at_abandonment,
                days_active=days_active,
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # STATUS OPERATIONS
    # ========================================================================

    async def activate_goal(self, uid: str) -> Result[bool]:
        """
        Activate a goal (set status to ACTIVE).

        Args:
            uid: Goal UID

        Returns:
            Result containing True if goal was activated
        """
        result = await self.update_goal(uid, GoalUpdateIntent(status=EntityStatus.ACTIVE.value))
        return Result.ok(True) if result.is_ok else Result.fail(result)

    async def pause_goal(
        self, uid: str, reason: str = "Paused", until_date: str | None = None
    ) -> Result[bool]:
        """
        Pause a goal temporarily.

        Args:
            uid: Goal UID
            reason: Reason for pausing
            until_date: Optional resume date (ISO format)

        Returns:
            Result containing True if goal was paused
        """
        # Store pause metadata
        metadata_updates = {"pause_reason": reason}
        if until_date:
            metadata_updates["paused_until"] = until_date

        result = await self.update_goal(uid, GoalUpdateIntent(status=EntityStatus.PAUSED.value))
        if result.is_ok and metadata_updates:
            # Update metadata separately
            goal = result.value
            goal.metadata.update(metadata_updates)
            await self.update_goal(uid, GoalUpdateIntent(metadata=goal.metadata))

        return Result.ok(True) if result.is_ok else Result.fail(result)

    async def complete_goal(
        self, uid: str, completion_notes: str = "", completion_date: str | None = None
    ) -> Result[bool]:
        """
        Mark a goal as completed.

        Args:
            uid: Goal UID
            completion_notes: Optional completion notes
            completion_date: Optional completion date (ISO format), defaults to today

        Returns:
            Result containing True if goal was completed
        """
        intent = GoalUpdateIntent(
            status=EntityStatus.COMPLETED.value,
            progress_percentage=100.0,
            completion_date=(
                date.fromisoformat(completion_date) if completion_date else date.today()
            ),
        )

        if completion_notes:
            # Get current goal to update metadata
            goal_result = await self.get(uid)
            if goal_result.is_ok and goal_result.value:
                goal = goal_result.value
                goal.metadata["completion_notes"] = completion_notes
                intent = dataclasses.replace(intent, metadata=goal.metadata)

        result = await self.update_goal(uid, intent)
        return Result.ok(True) if result.is_ok else Result.fail(result)

    async def archive_goal(self, uid: str, reason: str = "Archived") -> Result[bool]:
        """
        Archive a goal (set status to ARCHIVED).

        Args:
            uid: Goal UID
            reason: Reason for archiving

        Returns:
            Result containing True if goal was archived
        """
        intent = GoalUpdateIntent(status=EntityStatus.ARCHIVED.value)

        # Get current goal to update metadata
        goal_result = await self.get(uid)
        if goal_result.is_ok and goal_result.value:
            goal = goal_result.value
            goal.metadata["archive_reason"] = reason
            goal.metadata["archived_at"] = datetime.now().isoformat()
            intent = dataclasses.replace(intent, metadata=goal.metadata)

        result = await self.update_goal(uid, intent)
        return Result.ok(True) if result.is_ok else Result.fail(result)

    # ========================================================================
    # QUERY AND TIME-BASED OPERATIONS — Delegated to GoalsSearchService
    # ========================================================================
    # The facade (GoalsService) delegates all query/search methods to the
    # search sub-service (GoalsSearchService) which inherits from BaseService
    # with proper user_uid scoping. Dead duplicates removed March 2026.

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Universal Hierarchical Pattern)
    # Delegated to GoalsBackend via _HierarchyMixin (2026-03-24)
    # ========================================================================

    async def create_subgoal_relationship(
        self, parent_uid: str, subgoal_uid: str, progress_weight: float = 1.0
    ) -> Result[bool]:
        """Create bidirectional HAS_SUBGOAL/SUBGOAL_OF relationship with cycle detection."""
        return await self.backend.create_hierarchy_relationship(
            parent_uid, subgoal_uid, {"progress_weight": progress_weight}
        )

    async def remove_subgoal_relationship(self, parent_uid: str, subgoal_uid: str) -> Result[bool]:
        """Remove bidirectional HAS_SUBGOAL/SUBGOAL_OF relationship."""
        return await self.backend.remove_hierarchy_relationship(parent_uid, subgoal_uid)

    # ========================================================================
    # QUERY LAYER — Cypher-level filtering for get_filtered_context
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[GoalStats]:
        """Count goal stats via Cypher COUNT — no entity deserialization."""
        return await self.backend.get_stats_for_user(user_uid)

    # get_for_user_filtered: inherited from SearchOperationsMixin, driven by
    # the status_filters map in _config above.
