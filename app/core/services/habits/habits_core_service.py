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

from datetime import datetime
from typing import Any

from core.events import publish_event
from core.events.habit_events import HabitCreated
from core.models.enums.ku_enums import EntityStatus, EntityType
from core.models.habit.habit_request import HabitCreateRequest
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.ports import get_enum_value
from core.ports.domain_protocols import HabitsOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.utils.decorators import with_error_handling
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import Errors, Result
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

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=HabitDTO,
        model_class=Habit,
        entity_label="Ku",
        domain_name="habits",
        date_field="created_at",
        completed_statuses=(EntityStatus.ARCHIVED.value,),
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
        from core.models.enums import RecurrencePattern
        from core.utils.result_simplified import Errors

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
        from core.models.enums import RecurrencePattern
        from core.models.enums.ku_enums import EntityStatus
        from core.utils.result_simplified import Errors

        # Business Rule 1: Streak preservation on archive
        # Users invest effort building streaks - prevent accidental destruction
        if (
            "status" in updates
            and updates["status"] == EntityStatus.ARCHIVED.value
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

        if new_pattern == RecurrencePattern.DAILY and (new_target or 0) > 7:
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
                title=habit.title,
                frequency=get_enum_value(habit.recurrence_pattern)
                if habit.recurrence_pattern
                else "daily",
                domain=get_enum_value(habit.habit_category)
                if habit.habit_category
                else None,  # Habit uses 'habit_category', not 'domain'
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    async def create_habit(
        self, habit_request: HabitCreateRequest, user_uid: str
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
        if validation:
            return validation

        # Create DTO from request with all fields
        dto = HabitDTO(
            uid=UIDGenerator.generate_random_uid("habit"),
            user_uid=user_uid,
            title=habit_request.name,
            description=habit_request.description,
            polarity=habit_request.polarity,
            habit_category=habit_request.category,
            habit_difficulty=habit_request.difficulty,
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
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish embedding request event for async background generation (Phase 1 - January 2026)
        # Background worker will process embeddings in batches (zero latency impact on user)
        embedding_text = build_embedding_text(EntityType.HABIT, habit)
        if embedding_text:
            from core.events import HabitEmbeddingRequested

            now = datetime.now()
            embedding_event = HabitEmbeddingRequested(
                entity_uid=habit.uid,
                entity_type="habit",
                embedding_text=embedding_text,
                user_uid=habit.user_uid,
                requested_at=now,
                occurred_at=now,
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

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Universal Hierarchical Pattern)
    # ========================================================================

    @with_error_handling("get_subhabits", error_type="database", uid_param="parent_uid")
    async def get_subhabits(self, parent_uid: str, depth: int = 1) -> Result[list[Habit]]:
        """
        Get all subhabits of a parent habit.

        Args:
            parent_uid: Parent habit UID
            depth: How many levels deep (1=direct children, 2=children+grandchildren, etc.)

        Returns:
            Result containing list of subhabits ordered by created_at

        Example:
            # Get direct children
            subhabits = await service.get_subhabits("habit_abc123")

            # Get all descendants
            all_subhabits = await service.get_subhabits("habit_abc123", depth=99)
        """
        query = f"""
        MATCH (parent:Habit {{uid: $parent_uid}})
        MATCH (parent)-[:HAS_SUBHABIT*1..{depth}]->(subhabit:Habit)
        RETURN subhabit
        ORDER BY subhabit.created_at
        """

        result = await self.backend.execute_query(query, {"parent_uid": parent_uid})

        if result.is_error:
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.ok([])

        # Convert to Habit models
        habits = []
        for record in result.value:
            habit_data = record["subhabit"]
            habit = self._to_domain_model(habit_data, HabitDTO, Habit)
            habits.append(habit)

        return Result.ok(habits)

    @with_error_handling("get_parent_habit", error_type="database", uid_param="subhabit_uid")
    async def get_parent_habit(self, subhabit_uid: str) -> Result[Habit | None]:
        """
        Get immediate parent of a subhabit (if any).

        Args:
            subhabit_uid: Subhabit UID

        Returns:
            Result containing parent Habit or None if root-level habit
        """
        query = """
        MATCH (subhabit:Habit {uid: $subhabit_uid})
        MATCH (parent:Habit)-[:HAS_SUBHABIT]->(subhabit)
        RETURN parent
        LIMIT 1
        """

        result = await self.backend.execute_query(query, {"subhabit_uid": subhabit_uid})

        if result.is_error:
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.ok(None)

        parent_data = result.value[0]["parent"]
        parent = self._to_domain_model(parent_data, HabitDTO, Habit)
        return Result.ok(parent)

    @with_error_handling("get_habit_hierarchy", error_type="database", uid_param="habit_uid")
    async def get_habit_hierarchy(self, habit_uid: str) -> Result[dict[str, Any]]:
        """
        Get full hierarchy context: ancestors, siblings, children.

        Args:
            habit_uid: Habit UID to get context for

        Returns:
            Result containing hierarchy dict with keys:
            - ancestors: list[Habit] (root to immediate parent)
            - current: Habit
            - siblings: list[Habit] (other children of same parent)
            - children: list[Habit] (immediate children)
            - depth: int (how deep in hierarchy, 0=root)

        Example:
            hierarchy = await service.get_habit_hierarchy("habit_xyz789")
            # {
            #   "ancestors": [root_habit, parent_habit],
            #   "current": habit_xyz789,
            #   "siblings": [sibling1, sibling2],
            #   "children": [child1, child2],
            #   "depth": 2
            # }
        """
        # Get ancestors
        ancestors_query = """
        MATCH path = (root:Habit)-[:HAS_SUBHABIT*]->(current:Habit {uid: $habit_uid})
        WHERE NOT EXISTS((root)<-[:HAS_SUBHABIT]-())
        RETURN nodes(path) as ancestors
        """

        # Get siblings
        siblings_query = """
        MATCH (current:Habit {uid: $habit_uid})
        OPTIONAL MATCH (parent:Habit)-[:HAS_SUBHABIT]->(current)
        OPTIONAL MATCH (parent)-[:HAS_SUBHABIT]->(sibling:Habit)
        WHERE sibling.uid <> $habit_uid
        RETURN collect(sibling) as siblings
        """

        # Get children
        children_query = """
        MATCH (current:Habit {uid: $habit_uid})
        OPTIONAL MATCH (current)-[:HAS_SUBHABIT]->(child:Habit)
        RETURN collect(child) as children
        """

        # Execute all queries
        current_result = await self.backend.get(habit_uid)
        if current_result.is_error:
            return Result.fail(current_result)

        current_habit = self._to_domain_model(current_result.value, HabitDTO, Habit)

        ancestors_result = await self.backend.execute_query(
            ancestors_query, {"habit_uid": habit_uid}
        )
        siblings_result = await self.backend.execute_query(siblings_query, {"habit_uid": habit_uid})
        children_result = await self.backend.execute_query(children_query, {"habit_uid": habit_uid})

        # Process ancestors
        ancestors = []
        if (
            not ancestors_result.is_error
            and ancestors_result.value
            and ancestors_result.value[0]["ancestors"]
        ):
            for node in ancestors_result.value[0]["ancestors"][:-1]:  # Exclude current
                habit_data = node
                ancestors.append(self._to_domain_model(habit_data, HabitDTO, Habit))

        # Process siblings
        siblings = []
        if (
            not siblings_result.is_error
            and siblings_result.value
            and siblings_result.value[0]["siblings"]
        ):
            for node in siblings_result.value[0]["siblings"]:
                if node:  # Skip None values
                    habit_data = node
                    siblings.append(self._to_domain_model(habit_data, HabitDTO, Habit))

        # Process children
        children = []
        if (
            not children_result.is_error
            and children_result.value
            and children_result.value[0]["children"]
        ):
            for node in children_result.value[0]["children"]:
                if node:  # Skip None values
                    habit_data = node
                    children.append(self._to_domain_model(habit_data, HabitDTO, Habit))

        return Result.ok(
            {
                "ancestors": ancestors,
                "current": current_habit,
                "siblings": siblings,
                "children": children,
                "depth": len(ancestors),
            }
        )

    @with_error_handling("create_subhabit_relationship", error_type="database")
    async def create_subhabit_relationship(
        self, parent_uid: str, subhabit_uid: str, progress_weight: float = 1.0
    ) -> Result[bool]:
        """
        Create bidirectional parent-child relationship.

        Args:
            parent_uid: Parent habit UID
            subhabit_uid: Subhabit UID
            progress_weight: How much this subhabit contributes to parent progress (default: 1.0)

        Returns:
            Result indicating success

        Note:
            Creates both HAS_SUBHABIT (parent→child) and SUBHABIT_OF (child→parent)
            for efficient bidirectional queries.
        """
        # Validate no cycle (can't make parent a child of its descendant)
        cycle_check = await self._would_create_cycle(parent_uid, subhabit_uid)
        if cycle_check:
            return Result.fail(
                Errors.validation(
                    f"Cannot create subhabit relationship: would create cycle "
                    f"({subhabit_uid} is ancestor of {parent_uid})"
                )
            )

        query = """
        MATCH (parent:Habit {uid: $parent_uid})
        MATCH (subhabit:Habit {uid: $subhabit_uid})

        CREATE (parent)-[:HAS_SUBHABIT {
            progress_weight: $weight,
            created_at: datetime()
        }]->(subhabit)

        CREATE (subhabit)-[:SUBHABIT_OF {
            created_at: datetime()
        }]->(parent)

        RETURN true as success
        """

        result = await self.backend.execute_query(
            query,
            {"parent_uid": parent_uid, "subhabit_uid": subhabit_uid, "weight": progress_weight},
        )

        if result.is_error:
            return Result.fail(
                Errors.database(
                    operation="create", message="Failed to create subhabit relationship"
                )
            )
        if result.value:
            self.logger.info(
                f"Created subhabit relationship: {parent_uid} -> {subhabit_uid} (weight: {progress_weight})"
            )
            return Result.ok(True)

        return Result.fail(
            Errors.database(operation="create", message="Failed to create subhabit relationship")
        )

    @with_error_handling("remove_subhabit_relationship", error_type="database")
    async def remove_subhabit_relationship(
        self, parent_uid: str, subhabit_uid: str
    ) -> Result[bool]:
        """
        Remove bidirectional parent-child relationship.

        Args:
            parent_uid: Parent habit UID
            subhabit_uid: Subhabit UID

        Returns:
            Result containing True if relationships were deleted
        """
        query = """
        MATCH (parent:Habit {uid: $parent_uid})-[r1:HAS_SUBHABIT]->(subhabit:Habit {uid: $subhabit_uid})
        MATCH (subhabit)-[r2:SUBHABIT_OF]->(parent)
        DELETE r1, r2
        RETURN count(r1) + count(r2) as deleted_count
        """

        result = await self.backend.execute_query(
            query, {"parent_uid": parent_uid, "subhabit_uid": subhabit_uid}
        )

        if not result.is_error and result.value:
            deleted = result.value[0]["deleted_count"]
            if deleted > 0:
                self.logger.info(f"Removed subhabit relationship: {parent_uid} -> {subhabit_uid}")
                return Result.ok(True)

        return Result.ok(False)

    async def _would_create_cycle(self, parent_uid: str, child_uid: str) -> bool:
        """Check if adding parent->child relationship would create a cycle."""
        query = """
        MATCH (child:Habit {uid: $child_uid})
        MATCH path = (child)-[:HAS_SUBHABIT*]->(parent:Habit {uid: $parent_uid})
        RETURN count(path) > 0 as would_create_cycle
        """

        result = await self.backend.execute_query(
            query, {"parent_uid": parent_uid, "child_uid": child_uid}
        )

        if result.is_error:
            return False
        if result.value:
            return result.value[0]["would_create_cycle"]

        return False
