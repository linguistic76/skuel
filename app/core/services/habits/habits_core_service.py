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

Version: 2.0.0
Date: 2025-11-05
"""

from datetime import datetime
from typing import Any

from core.events import publish_event
from core.events.habit_events import HabitCreated
from core.models.enums.activity_enums import ActivityStatus
from core.models.habit.habit import Habit, HabitStatus
from core.models.habit.habit_dto import HabitDTO
from core.models.habit.habit_request import HabitCreateRequest
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.protocols import get_enum_value
from core.services.protocols.domain_protocols import HabitsOperations
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator


class HabitsCoreService(BaseService[HabitsOperations, Habit]):
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


    Source Tag: "habits_core_service_explicit"
    - Format: "habits_core_service_explicit" for user-created relationships
    - Format: "habits_core_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from habits_core metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

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
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Habit entities."""
        return "Habit"

    # ========================================================================
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    def _build_embedding_text(self, habit: Habit) -> str:
        """
        Build text for embedding from habit fields.

        Used for async background embedding generation.
        Includes name, description, cue (trigger), and reward for comprehensive semantic search.

        Args:
            habit: Habit domain model

        Returns:
            Text for embedding (name + description + cue + reward)
        """
        parts = [habit.name]
        if habit.description:
            parts.append(habit.description)
        if habit.cue:
            parts.append(habit.cue)
        if habit.reward:
            parts.append(habit.reward)
        return "\n".join(parts).strip()

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=HabitDTO,
        model_class=Habit,
        domain_name="habits",
        date_field="created_at",
        completed_statuses=(ActivityStatus.ARCHIVED.value,),
    )
    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, habit: Habit) -> Result[None] | None:
        """
        Validate habit creation with business rules.

        Business Rules:
        1. Frequency consistency: Daily habits can't have target > 7 days/week

        Args:
            habit: Habit domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.models.shared_enums import RecurrencePattern
        from core.utils.result_simplified import Errors

        # Business Rule: Frequency consistency
        # Daily habit with target > 7 days/week is logically impossible
        if habit.recurrence_pattern == RecurrencePattern.DAILY and habit.target_days_per_week > 7:
            return Result.fail(
                Errors.validation(
                    message="Daily habit cannot have target > 7 days per week",
                    field="target_days_per_week",
                    value=habit.target_days_per_week,
                )
            )

        return None  # All validations passed

    def _validate_update(self, current: Habit, updates: dict[str, Any]) -> Result[None] | None:
        """
        Validate habit updates with business rules.

        Business Rules:
        1. Streak preservation: Warn before archiving habits with active streaks (7+ days)
        2. Frequency consistency: If updating to DAILY, target_days_per_week must be <= 7

        Args:
            current: Current habit state
            updates: Dictionary of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.models.habit.habit import HabitStatus
        from core.models.shared_enums import RecurrencePattern
        from core.utils.result_simplified import Errors

        # Business Rule 1: Streak preservation on archive
        # Users invest effort building streaks - prevent accidental destruction
        if (
            "status" in updates
            and updates["status"] == HabitStatus.ARCHIVED.value
            and current.current_streak
            and current.current_streak >= 7
        ):
            return Result.fail(
                Errors.validation(
                    message=f"This habit has an active {current.current_streak}-day streak. "
                    f"Archiving will end it. Set force_archive=true in updates to proceed.",
                    field="status",
                    value=updates["status"],
                )
            )

        # Business Rule 2: Frequency consistency on update
        # Check if updating recurrence_pattern to DAILY or updating target_days_per_week
        new_pattern = updates.get("recurrence_pattern", current.recurrence_pattern)
        new_target = updates.get("target_days_per_week", current.target_days_per_week)

        # Handle both enum and string values for recurrence_pattern
        if isinstance(new_pattern, str):
            new_pattern = RecurrencePattern(new_pattern)

        if new_pattern == RecurrencePattern.DAILY and new_target > 7:
            return Result.fail(
                Errors.validation(
                    message="Daily habit cannot have target > 7 days per week",
                    field="target_days_per_week",
                    value=new_target,
                )
            )

        # Allow archive if force_archive flag is present
        if updates.get("force_archive"):
            return None  # Bypass streak protection

        return None  # All validations passed

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

    async def get_user_habits(self, user_uid: str) -> Result[list[Habit]]:
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
                title=habit.name,  # Habit uses 'name' field, not 'title'
                frequency=get_enum_value(habit.recurrence_pattern)
                if habit.recurrence_pattern
                else "daily",
                domain=get_enum_value(habit.category)
                if habit.category
                else None,  # Habit uses 'category', not 'domain'
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    async def create_habit(self, habit_request: HabitCreateRequest, user_uid: str) -> Result[Habit]:
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
        if validation:
            return validation

        # Create DTO from request with all fields
        dto = HabitDTO(
            uid=UIDGenerator.generate_random_uid("habit"),
            user_uid=user_uid,
            name=habit_request.name,
            description=habit_request.description,
            polarity=habit_request.polarity,
            category=habit_request.category,
            difficulty=habit_request.difficulty,
            recurrence_pattern=habit_request.recurrence_pattern,
            target_days_per_week=habit_request.target_days_per_week,
            preferred_time=habit_request.preferred_time,
            duration_minutes=habit_request.duration_minutes,
            cue=habit_request.cue,
            routine=habit_request.routine,
            reward=habit_request.reward,
            is_identity_habit=habit_request.is_identity_habit,
            reinforces_identity=habit_request.reinforces_identity,
            status=HabitStatus.ACTIVE,
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
            title=habit.name,
            frequency=get_enum_value(habit.recurrence_pattern)
            if habit.recurrence_pattern
            else "daily",
            domain=get_enum_value(habit.category) if habit.category else None,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish embedding request event for async background generation (Phase 1 - January 2026)
        # Background worker will process embeddings in batches (zero latency impact on user)
        embedding_text = self._build_embedding_text(habit)
        if embedding_text:
            from core.events import HabitEmbeddingRequested

            embedding_event = HabitEmbeddingRequested(
                entity_uid=habit.uid,
                entity_type="habit",
                embedding_text=embedding_text,
                user_uid=habit.user_uid,
                requested_at=datetime.now(),
            )
            await publish_event(self.event_bus, embedding_event, self.logger)

        return Result.ok(habit)

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Habit]:
        """
        Update a habit.

        Note: Habit updates don't have specific events beyond generic update.
        Streak-related events (HabitStreakBroken, HabitStreakMilestone) are
        published by HabitsProgressService when completions are logged.

        Args:
            uid: Habit UID
            updates: Dictionary of field updates

        Returns:
            Result containing updated Habit
        """
        # Call parent update (no special event for habit updates)
        return await super().update(uid, updates)

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        DETACH DELETE (archive) a habit.

        Note: Habits are typically archived rather than deleted.
        No specific event for habit deletion - archived status is sufficient.

        Args:
            uid: Habit UID
            cascade: Whether to cascade DETACH DELETE (default False)

        Returns:
            Result indicating success
        """
        # Call parent delete (no special event for habit deletion)
        return await super().delete(uid, cascade=cascade)
