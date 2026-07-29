"""
Habits Core Service
===================

Handles basic CRUD operations for habits.

Responsibilities:
- Get habit by UID
- Get user's habits
- List habits with filters
- Basic habit retrieval operations
- Publishes domain events (HabitCreated, HabitCompleted, HabitStreakBroken)
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from core.events import publish_event
from core.events.embedding_publisher import publish_embedding_requested
from core.events.habit_events import HabitCreated, HabitUpdated
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.habit.habit_request import HabitCreateRequest
from core.models.habit.habit_update_intent import HabitUpdateIntent
from core.models.type_hints import UserUID
from core.ports import get_enum_value
from core.ports.domain_protocols import HabitsOperations
from core.ports.query_types import HabitStats
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator


class HabitsCoreService(
    HierarchyReadMixin[HabitsOperations, Habit],
    BaseService[HabitsOperations, Habit, HabitUpdateIntent],
):
    """
    Core CRUD service for habits.

    Handles:
    - Basic retrieval operations
    - User habit queries
    - Habit listing and filtering
    - Publishes domain events for all state changes

    Event-Driven Architecture:
    - Publishes HabitCreated on creation
    - Note: HabitCompleted, HabitStreakBroken, HabitStreakMilestone
      published by HabitsProgressService (streak tracking logic)
    """

    def __init__(self, backend: HabitsOperations, event_bus=None) -> None:
        """
        Initialize habits core service.

        Args:
            backend: Protocol-based backend for habit operations
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "habits.core")
        self.event_bus = event_bus

    # ========================================================================
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=HabitDTO,
        model_class=Habit,
        entity_label="Entity",
        domain_name="habits",
        date_field="created_at",
        completed_statuses=(EntityStatus.ARCHIVED.value,),
        status_filters={
            "active": {"status": "active"},
            "paused": {"status": "paused"},
            "completed": {"status": "completed"},
        },
    )
    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, habit: Habit) -> Result[None]:
        """
        Validate habit creation with business rules.

        Business Rules:
        1. Frequency consistency: Daily habits can't have target > 7 days/week

        Args:
            habit: Habit domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.models.enums import RecurrencePattern

        # Business Rule: Frequency consistency
        # Daily habit with target > 7 days/week is logically impossible
        if (
            habit.recurrence_pattern == RecurrencePattern.DAILY
            and (habit.target_days_per_week or 0) > 7
        ):
            return Result.fail(
                Errors.validation(
                    message="Daily habit cannot have target > 7 days per week",
                    field="target_days_per_week",
                    value=habit.target_days_per_week,
                )
            )

        return Result.ok(None)  # All validations passed

    def _validate_update(self, current: Habit, updates: HabitUpdateIntent) -> Result[None]:
        """
        Validate habit updates (base contract hook).

        Delegates to :meth:`_validate_habit_update` with ``force_archive=False``. The
        bespoke ``update_habit`` path calls ``_validate_habit_update`` directly so it can
        surface the transient ``force_archive`` directive (which cannot ride the intent —
        it would persist as a junk column).

        Args:
            current: Current habit state
            updates: Typed ``HabitUpdateIntent`` of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        return self._validate_habit_update(current, updates.to_changes(), force_archive=False)

    def _validate_habit_update(
        self, current: Habit, changes: Mapping[str, Any], *, force_archive: bool
    ) -> Result[None]:
        """
        Validate habit updates with business rules.

        Business Rules:
        1. Streak preservation: Warn before archiving habits with active streaks (7+ days)
        2. Frequency consistency: If updating to DAILY, target_days_per_week must be <= 7

        Args:
            current: Current habit state
            changes: Proposed field changes (the intent's ``to_changes()``)
            force_archive: Transient directive bypassing the streak-preservation rule only —
                never a persisted column

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.models.enums import RecurrencePattern
        from core.models.enums.entity_enums import EntityStatus

        # Business Rule 1: Streak preservation on archive
        # Users invest effort building streaks - prevent accidental destruction.
        # The transient ``force_archive`` directive (never a persisted column; passed via
        # the keyword on update_habit) bypasses THIS rule only — gating the condition on it
        # is what makes the bypass the error message advertises actually work.
        if (
            "status" in changes
            and changes["status"] == EntityStatus.ARCHIVED.value
            and current.current_streak
            and current.current_streak >= 7
            and not force_archive
        ):
            return Result.fail(
                Errors.validation(
                    message=f"This habit has an active {current.current_streak}-day streak. "
                    f"Archiving will end it. Set force_archive=true to proceed.",
                    field="status",
                    value=changes["status"],
                )
            )

        # Business Rule 2: Frequency consistency on update
        # Check if updating recurrence_pattern to DAILY or updating target_days_per_week.
        # This is a data-integrity rule — NOT bypassable by force_archive.
        new_pattern = changes.get("recurrence_pattern", current.recurrence_pattern)
        new_target = changes.get("target_days_per_week", current.target_days_per_week)

        # Handle both enum and string values for recurrence_pattern
        if isinstance(new_pattern, str):
            new_pattern = RecurrencePattern(new_pattern)

        if new_pattern == RecurrencePattern.DAILY and (new_target or 0) > 7:
            return Result.fail(
                Errors.validation(
                    message="Daily habit cannot have target > 7 days per week",
                    field="target_days_per_week",
                    value=new_target,
                )
            )

        return Result.ok(None)  # All validations passed

    # ========================================================================
    # BASIC CRUD OPERATIONS
    # ========================================================================

    async def get_habit(self, uid: str) -> Result[Habit]:
        """
        Get habit by UID.

        Uses BaseService.get() for standardized retrieval pattern.
        Not found is returned as Result.fail(Errors.not_found(...)).
        """
        return await self.get(uid)

    async def get_user_habits(self, user_uid: UserUID) -> Result[list[Habit]]:
        """Get all habits for a user."""
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return result

        # Use BaseService helper for batch DTO conversion
        habits = self._to_domain_models(result.value, HabitDTO, Habit)

        self.logger.info(f"Retrieved {len(habits)} habits for user {user_uid}")
        return Result.ok(habits)

    async def list_habits(
        self, limit: int = 100, **filters: Any
    ) -> Result[tuple[list[Habit], int]]:
        """
        List habits with optional filters.

        Returns:
            Result[tuple[list[Habit], int]]: Tuple of (habits, total_count) for pagination
        """
        result = await self.backend.list(limit=limit, filters=filters)
        if result.is_error:
            return result

        # Unpack pagination tuple
        habits_data, total_count = result.value

        # Use BaseService helper for batch DTO conversion
        habits = self._to_domain_models(habits_data, HabitDTO, Habit)
        return Result.ok((habits, total_count))

    # get_user_items_in_range() is now inherited from BaseService
    # Configured via class attributes: _date_field, _completed_statuses, _dto_class, _model_class
    # CONSOLIDATED (November 27, 2025) - Removed 40 lines of duplicate code

    # ========================================================================
    # EVENT-DRIVEN CRUD OPERATIONS
    # ========================================================================

    async def create(self, entity: Habit) -> Result[Habit]:
        """
        Create a habit and publish HabitCreated event.

        Args:
            entity: Habit to create

        Returns:
            Result containing created Habit

        Events Published:
            - HabitCreated: When habit is successfully created
        """
        # Call parent create
        result = await super().create(entity)

        # Publish HabitCreated event
        if result.is_ok:
            habit = result.value
            event = HabitCreated(
                habit_uid=habit.uid,
                user_uid=habit.user_uid,
                title=habit.title,
                frequency=get_enum_value(habit.recurrence_pattern)
                if habit.recurrence_pattern
                else "daily",
                domain=get_enum_value(habit.habit_category)
                if habit.habit_category
                else None,  # Habit uses 'habit_category', not 'domain'
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    async def create_habit(
        self, habit_request: HabitCreateRequest, user_uid: UserUID
    ) -> Result[Habit]:
        """
        Create a habit from a request with user_uid.

        Args:
            habit_request: Habit creation request
            user_uid: User UID (REQUIRED - fail-fast on None)

        Returns:
            Result containing created Habit
        """
        # Validate user_uid (uses BaseService helper)
        validation = self._validate_required_user_uid(user_uid, "habit creation")
        if validation.is_error:
            return Result.fail(validation)

        # Create DTO from request with all fields
        dto = HabitDTO(
            uid=UIDGenerator.generate_random_uid("habit"),
            user_uid=user_uid,
            title=habit_request.title,
            description=habit_request.description,
            polarity=habit_request.polarity,
            habit_category=habit_request.habit_category,
            habit_difficulty=habit_request.habit_difficulty,
            recurrence_pattern=habit_request.recurrence_pattern,
            target_days_per_week=habit_request.target_days_per_week,
            preferred_time=habit_request.preferred_time,
            duration_minutes=habit_request.duration_minutes,
            cue=habit_request.cue,
            routine=habit_request.routine,
            reward=habit_request.reward,
            is_identity_habit=habit_request.is_identity_habit,
            reinforces_identity=habit_request.reinforces_identity,
            status=EntityStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Create habit via backend and convert to domain model (uses BaseService helper)
        result = await self._create_and_convert(dto.to_dict(), HabitDTO, Habit)
        if result.is_error:
            return result
        habit = result.value

        # Publish HabitCreated event
        event = HabitCreated(
            habit_uid=habit.uid,
            user_uid=habit.user_uid,
            title=habit.title,
            frequency=get_enum_value(habit.recurrence_pattern)
            if habit.recurrence_pattern
            else "daily",
            domain=get_enum_value(habit.habit_category) if habit.habit_category else None,
        )
        await publish_event(self.event_bus, event, self.logger)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.HABIT, habit, self.logger)

        return Result.ok(habit)

    @with_error_handling("update_habit", error_type="database", uid_param="uid")
    async def update_habit(
        self, uid: str, intent: HabitUpdateIntent, *, force_archive: bool = False
    ) -> Result[Habit]:
        """Update a habit's node properties (ADR-066 typed update contract).

        Materializes the intent to a partial patch, runs ``_validate_update`` (Habits' live
        rules: streak preservation on archive, DAILY-frequency consistency), writes the
        patch, then publishes ``HabitUpdated``. Habits carry no edge fields on the update
        path, so the intent's ``to_changes()`` is written wholesale.

        Design note (ADR-066 trace-and-deviate, mirrors Principles' documented case):
        unlike Goals/Choices, ``update_habit`` does **not** route through ``super().update()``.
        Habits' ``_validate_update`` reads a transient ``force_archive`` directive that bypasses
        the streak-preservation rule. The shared base passes the *same* mapping to
        ``_validate_update`` and ``backend.update`` (``SET n += $updates``, no key filtering), so
        carrying ``force_archive`` through ``super().update()`` would persist it as a junk node
        column. Instead we validate explicitly here — with the flag visible to validation only —
        then write the clean column patch backend-direct. Validation still runs on every path
        (all callers funnel through here), and the previously-unwired ``force_archive`` escape
        hatch its own error message advertises now works honestly.

        Args:
            uid: Habit UID
            intent: Typed ``HabitUpdateIntent`` — only its set fields are written
            force_archive: Bypass the streak-preservation rule (transient; never persisted)

        Returns:
            Result containing updated Habit

        Events Published:
            - HabitUpdated: always, so user-context caches invalidate even for plain property
              edits (title / schedule / cue) with no more specific event

        (Streak / completion changes fire HabitCompleted / HabitStreakBroken /
        HabitStreakMilestone from HabitsProgressService, which owns that provenance.)
        """
        changes = intent.to_changes()
        # Capture the intended fields now: the backend stamps updated_at in place, so
        # reading changes.keys() after the write would leak that bump into the event.
        updated_fields = list(changes.keys())

        current_result = await self.get(uid)
        if current_result.is_error:
            return current_result
        current = current_result.value

        # Validate with the transient force_archive flag visible to validation only — it is
        # never added to `changes`, so it can never reach backend.update.
        validation = self._validate_habit_update(current, changes, force_archive=force_archive)
        if validation.is_error:
            return Result.fail(validation)

        result: Result[Habit] = await self.backend.update(uid, dict(changes))
        if result.is_error:
            return result

        habit = result.value
        await publish_event(
            self.event_bus,
            HabitUpdated(
                habit_uid=habit.uid, user_uid=habit.user_uid, updated_fields=updated_fields
            ),
            self.logger,
        )

        # Post-persist embedding refresh (ADR-074) — only when a text field changed
        await publish_embedding_requested(
            self.event_bus, EntityType.HABIT, habit, self.logger, changed_fields=updated_fields
        )

        return result

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        Delete (archive) a habit.

        Note: Habits are typically archived rather than deleted.
        No specific event for habit deletion - archived status is sufficient.

        Args:
            uid: Habit UID
            cascade: Whether to cascade delete (default False)

        Returns:
            Result indicating success
        """
        # Call parent delete (no special event for habit deletion)
        return await super().delete(uid, cascade=cascade)

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Universal Hierarchical Pattern)
    # Delegated to HabitsBackend via _HierarchyMixin (2026-03-24)
    # ========================================================================

    async def create_subhabit_relationship(
        self, parent_uid: str, subhabit_uid: str, progress_weight: float = 1.0
    ) -> Result[bool]:
        """Create bidirectional HAS_SUBHABIT/SUBHABIT_OF relationship with cycle detection."""
        return await self.backend.create_hierarchy_relationship(
            parent_uid, subhabit_uid, {"progress_weight": progress_weight}
        )

    async def remove_subhabit_relationship(
        self, parent_uid: str, subhabit_uid: str
    ) -> Result[bool]:
        """Remove bidirectional HAS_SUBHABIT/SUBHABIT_OF relationship."""
        return await self.backend.remove_hierarchy_relationship(parent_uid, subhabit_uid)

    # ========================================================================
    # QUERY LAYER — Cypher-level filtering for get_filtered_context
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[HabitStats]:
        """Count habit stats via Cypher COUNT — no entity deserialization."""
        return await self.backend.get_stats_for_user(user_uid)

    # get_for_user_filtered: inherited from SearchOperationsMixin, driven by
    # the status_filters map in _config above.
