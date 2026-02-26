"""
Goals Core Service
==================

Handles basic CRUD operations for goals.

Responsibilities:
- Basic goal retrieval (get_user_goals)
- Delegates create/update/DETACH DELETE to backend via BaseService
- Publishes domain events (GoalCreated, GoalAchieved, GoalProgressUpdated, GoalAbandoned)

  RelationshipRegistry (GOALS_CONFIG). Shared-neighbor pattern for
  related_goals is now defined in the registry.
  See: /core/models/relationship_registry.py
- v2.2.0 (2025-11-28): Milestones as graph nodes.
  Milestones are now stored as separate Milestone nodes connected via HAS_MILESTONE edge.
- v2.1.0 (2025-11-28): Eliminated APOC dependency.
- v2.0.0 (2025-11-05): Initial facade pattern implementation
"""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.goal.goal_request import GoalCreateRequest

from core.events import publish_event
from core.events.goal_events import (
    GoalAbandoned,
    GoalAchieved,
    GoalCreated,
    GoalProgressUpdated,
)
from core.models.enums import EntityStatus
from core.models.enums.entity_enums import EntityType
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.models.relationship_names import RelationshipName
from core.ports import get_enum_value
from core.ports.domain_protocols import GoalsOperations
from core.ports.query_types import GoalUpdatePayload
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.utils.decorators import with_error_handling
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator


class GoalsCoreService(BaseService[GoalsOperations, Goal]):
    """
    Core CRUD operations for goals.

    This service provides basic goal operations:
    - get_user_goals: Retrieve all goals for a user
    - Inherits: create, get, update, DETACH DELETE from BaseService
    - Publishes domain events for all state changes

    Event-Driven Architecture:
    - Publishes GoalCreated on creation
    - Publishes GoalAchieved when goal completed
    - Publishes GoalProgressUpdated on progress changes
    - Publishes GoalAbandoned when goal cancelled


    Source Tag: "goals_core_service_explicit"
    - Format: "goals_core_service_explicit" for user-created relationships
    - Format: "goals_core_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from goals_core metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, backend: GoalsOperations, event_bus=None) -> None:
        """
        Initialize goals core service.

        Args:
            backend: Protocol-based backend for goal operations
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "goals")
        self.logger = get_logger("skuel.services.goals.core")
        self.event_bus = event_bus

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Goal entities."""
        return "Entity"

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
        entity_label="Entity",
    )
    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, goal: Goal) -> Result[None] | None:
        """
        Validate goal creation with business rules.

        Business Rules:
        1. Target date must be after start date (timeline consistency)

        Args:
            goal: Goal domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """

        # Business Rule: Target date must be after start date
        if goal.target_date and goal.start_date and goal.target_date <= goal.start_date:
            return Result.fail(
                Errors.validation(
                    message="Target date must be after start date",
                    field="target_date",
                    value=goal.target_date.isoformat(),
                )
            )

        return None  # All validations passed

    def _validate_update(self, current: Goal, updates: dict[str, Any]) -> Result[None] | None:
        """
        Validate goal updates with business rules.

        Business Rules:
        1. Achievement state immutability: Cannot modify achieved goals
        2. Target date validation: If updating dates, target must be after start

        Note: Goal abandonment protection (checking for active tasks) is handled
        in the update() method since it requires async relationship queries.

        Args:
            current: Current goal state
            updates: Dictionary of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """

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
        if "target_date" in updates or "start_date" in updates:
            # Determine new values (use updated value if present, else current)
            new_target = updates.get("target_date", current.target_date)
            new_start = updates.get("start_date", current.start_date)

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

        return None  # All validations passed

    # ========================================================================
    # READ OPERATIONS WITH GRAPH CONTEXT
    # ========================================================================
    # NOTE: get_with_context() is inherited from BaseService (January 2026)
    #
    # Uses registry-driven query generation from RelationshipRegistry.
    # The GOALS_CONFIG config includes:
    # - contributing_tasks, contributing_habits (supporting activities)
    # - sub_goals, parent_goal (hierarchy)
    # - required_knowledge, aligned_principles (prerequisites and guidance)
    # - inspired_by_choice (motivation)
    # - milestones (progress tracking)
    # - related_goals (shared-neighbor pattern via FULFILLS_GOAL|SUPPORTS_GOAL)
    # - milestone_progress (calculated in BaseService._parse_context_result)
    #
    # See: /core/models/relationship_registry.py - GOALS_CONFIG
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

    async def get_user_goals(self, user_uid: str) -> Result[list[Goal]]:
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
        """
        Create a goal and publish GoalCreated event.

        Args:
            entity: Goal to create

        Returns:
            Result containing created Goal

        Events Published:
            - GoalCreated: When goal is successfully created
        """
        # Call parent create
        result: Result[Goal] = await super().create(entity)

        # Publish GoalCreated event
        if result.is_ok:
            goal: Goal = result.value  # Type hint to help MyPy
            event = GoalCreated(
                goal_uid=goal.uid,
                user_uid=goal.user_uid,
                title=goal.title,
                domain=get_enum_value(goal.domain) if goal.domain else None,
                target_date=goal.target_date,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    async def create_goal(self, goal_request: "GoalCreateRequest", user_uid: str) -> Result[Goal]:
        """
        Create a goal from a request with user_uid.

        Args:
            goal_request: Goal creation request
            user_uid: User UID (REQUIRED - fail-fast on None)

        Returns:
            Result containing created Goal
        """
        # Validate user_uid (uses BaseService helper)
        validation = self._validate_required_user_uid(user_uid, "goal creation")
        if validation:
            return validation

        # Create DTO from request with all fields
        # Set status to ACTIVE so goal appears in default list view
        dto = GoalDTO(
            uid=UIDGenerator.generate_random_uid("goal"),
            user_uid=user_uid,
            title=goal_request.title,
            description=goal_request.description,
            vision_statement=goal_request.vision_statement,
            goal_type=goal_request.goal_type,
            domain=goal_request.domain,
            timeframe=goal_request.timeframe,
            measurement_type=goal_request.measurement_type,
            target_value=goal_request.target_value,
            start_date=goal_request.start_date,
            target_date=goal_request.target_date,
            fulfills_goal_uid=goal_request.parent_goal_uid,
            priority=goal_request.priority,
            status=EntityStatus.ACTIVE,
        )

        # Create goal via backend and convert to domain model (uses BaseService helper)
        result = await self._create_and_convert(dto.to_dict(), GoalDTO, Goal)
        if result.is_error:
            return result
        goal = result.value

        # Publish GoalCreated event
        event = GoalCreated(
            goal_uid=goal.uid,
            user_uid=goal.user_uid,
            title=goal.title,
            domain=get_enum_value(goal.domain) if goal.domain else None,
            target_date=goal.target_date,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish embedding request event for async background generation
        # Background worker will process embeddings in batches (zero latency impact on user)
        embedding_text = build_embedding_text(EntityType.GOAL, goal)
        if embedding_text:
            from core.events import GoalEmbeddingRequested

            now = datetime.now()
            embedding_event = GoalEmbeddingRequested(
                entity_uid=goal.uid,
                entity_type="goal",
                embedding_text=embedding_text,
                user_uid=goal.user_uid,
                requested_at=now,
                occurred_at=now,
            )
            await publish_event(self.event_bus, embedding_event, self.logger)

        return Result.ok(goal)

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Goal]:
        """
        Update a goal and publish appropriate events.

        Business Rule Enforcement (async validation):
        - Goal abandonment protection: Cannot cancel goal with active tasks

        Publishes GoalProgressUpdated if progress field changed.
        Publishes GoalAchieved if status changed to COMPLETED.

        Args:
            uid: Goal UID
            updates: Dictionary of field updates

        Returns:
            Result containing updated Goal

        Events Published:
            - GoalProgressUpdated: If progress field updated
            - GoalAchieved: If status changed to COMPLETED
        """
        # Business Rule: Goal abandonment protection (requires async relationship query)
        # Cannot abandon goal with active tasks - forces user to handle dependencies first
        if "status" in updates and updates["status"] == EntityStatus.CANCELLED.value:
            # Query for active tasks linked to this goal
            from core.models.query import build_relationship_count

            # Check for tasks that are not in terminal states (i.e., still active/pending)
            # We can't filter by non-terminal in a simple property match, so we check for
            # the most common active states: IN_PROGRESS, SCHEDULED, BLOCKED, PAUSED
            query, params = build_relationship_count(
                uid=uid,
                relationship_type=RelationshipName.FULFILLS_GOAL.value,
                direction="incoming",  # (task)-[:FULFILLS_GOAL]->(goal)
                properties={
                    "status__in": [
                        EntityStatus.ACTIVE.value,
                        EntityStatus.SCHEDULED.value,
                        EntityStatus.BLOCKED.value,
                        EntityStatus.PAUSED.value,
                    ]
                },
            )

            query_result = await self.backend.execute_query(query, params)
            if query_result.is_error:
                # Log warning but continue - don't block on relationship query failure
                self.logger.warning(
                    f"Failed to check active tasks for goal {uid}: {query_result.expect_error()}"
                )
            else:
                active_task_count = query_result.value[0]["count"] if query_result.value else 0

                if active_task_count > 0:
                    from core.utils.result_simplified import Errors

                    return Result.fail(
                        Errors.validation(
                            message=f"Cannot abandon goal with {active_task_count} active task(s). Complete or reassign tasks first.",
                            field="status",
                            value=updates["status"],
                        )
                    )

        # Get current goal to track changes (always fetch if updating progress or status)
        old_goal = None
        old_progress = None
        if "progress" in updates or "status" in updates:
            current_result = await self.get(uid)
            if current_result.is_ok and current_result.value:
                old_goal = current_result.value
                old_progress = getattr(old_goal, "progress", 0.0) or 0.0

        # Call parent update
        result: Result[Goal] = await super().update(uid, updates)

        if result.is_ok:
            goal: Goal = result.value  # Type hint to help MyPy

            # Publish GoalProgressUpdated event if progress changed
            if "progress" in updates and old_progress is not None:
                new_progress = updates.get("progress", 0.0)

                event = GoalProgressUpdated(
                    goal_uid=goal.uid,
                    user_uid=goal.user_uid,
                    old_progress=old_progress,
                    new_progress=new_progress,
                    occurred_at=datetime.now(),
                    triggered_by_manual_update=True,
                )
                await publish_event(self.event_bus, event, self.logger)

            # Publish GoalAchieved event if status changed to ACHIEVED
            if "status" in updates and old_goal:
                new_status = updates.get("status")
                old_status = get_enum_value(old_goal.status)  # Handle both enum and string

                if (
                    new_status == EntityStatus.COMPLETED.value
                    and old_status != EntityStatus.COMPLETED.value
                ):
                    # Calculate duration if created_at exists
                    actual_duration_days = None
                    if goal.created_at:
                        actual_duration_days = (datetime.now() - goal.created_at).days

                    achieved_event = GoalAchieved(
                        goal_uid=goal.uid,
                        user_uid=goal.user_uid,
                        actual_duration_days=actual_duration_days,
                        occurred_at=datetime.now(),
                    )
                    await publish_event(self.event_bus, achieved_event, self.logger)

        return result

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        DETACH DELETE (abandon) a goal and publish GoalAbandoned event.

        Args:
            uid: Goal UID
            cascade: Whether to cascade DETACH DELETE (default False)

        Returns:
            Result indicating success

        Events Published:
            - GoalAbandoned: When goal is successfully deleted
        """
        # Get goal details before deletion for event publishing
        goal_result = await self.get(uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

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
                occurred_at=datetime.now(),
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
        updates: GoalUpdatePayload = {"status": EntityStatus.ACTIVE.value}
        result = await self.update(uid, updates)
        return Result.ok(True) if result.is_ok else Result.fail(result.expect_error())

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
        updates: GoalUpdatePayload = {"status": EntityStatus.PAUSED.value}

        # Store pause metadata
        metadata_updates = {"pause_reason": reason}
        if until_date:
            metadata_updates["paused_until"] = until_date

        result = await self.update(uid, updates)
        if result.is_ok and metadata_updates:
            # Update metadata separately
            goal = result.value
            goal.metadata.update(metadata_updates)
            await self.update(uid, {"metadata": goal.metadata})

        return Result.ok(True) if result.is_ok else Result.fail(result.expect_error())

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
        updates: GoalUpdatePayload = {
            "status": EntityStatus.COMPLETED.value,
            "progress_percentage": 100.0,
            "completion_date": (
                date.fromisoformat(completion_date) if completion_date else date.today()
            ),
        }

        if completion_notes:
            # Get current goal to update metadata
            goal_result = await self.get(uid)
            if goal_result.is_ok and goal_result.value:
                goal = goal_result.value
                goal.metadata["completion_notes"] = completion_notes
                updates["metadata"] = goal.metadata

        result = await self.update(uid, updates)
        return Result.ok(True) if result.is_ok else Result.fail(result.expect_error())

    async def archive_goal(self, uid: str, reason: str = "Archived") -> Result[bool]:
        """
        Archive a goal (set status to ARCHIVED).

        Args:
            uid: Goal UID
            reason: Reason for archiving

        Returns:
            Result containing True if goal was archived
        """
        updates: GoalUpdatePayload = {"status": EntityStatus.ARCHIVED.value}

        # Get current goal to update metadata
        goal_result = await self.get(uid)
        if goal_result.is_ok and goal_result.value:
            goal = goal_result.value
            goal.metadata["archive_reason"] = reason
            goal.metadata["archived_at"] = datetime.now().isoformat()
            updates["metadata"] = goal.metadata

        result = await self.update(uid, updates)
        return Result.ok(True) if result.is_ok else Result.fail(result.expect_error())

    # ========================================================================
    # QUERY OPERATIONS
    # ========================================================================

    async def list_goal_categories(self) -> Result[list[str]]:
        """
        List all unique goal categories.

        Returns:
            Result containing list of category strings
        """
        # Query Neo4j for distinct domain values
        query = """
        MATCH (g:Entity {ku_type: 'goal'})
        RETURN DISTINCT g.domain as category
        ORDER BY category
        """

        result = await self.backend.execute_query(query, {})
        if result.is_error:
            return Result.fail(result.expect_error())

        categories = [record["category"] for record in result.value if record.get("category")]
        return Result.ok(categories)

    async def get_goals_by_category(self, category: str, limit: int = 100) -> Result[list[Goal]]:
        """
        Get goals in a specific category.

        Args:
            category: Category/domain name
            limit: Maximum number of goals to return

        Returns:
            Result containing list of Goals
        """
        result = await self.backend.find_by(domain=category, limit=limit)
        if result.is_error:
            return result

        goals = self._to_domain_models(result.value, GoalDTO, Goal)
        return Result.ok(goals)

    async def get_goals_by_status(self, status: str, limit: int = 100) -> Result[list[Goal]]:
        """
        Get goals by status.

        Args:
            status: Goal status (active, completed, paused, etc.)
            limit: Maximum number of goals to return

        Returns:
            Result containing list of Goals
        """
        result = await self.backend.find_by(status=status, limit=limit)
        if result.is_error:
            return result

        goals = self._to_domain_models(result.value, GoalDTO, Goal)
        return Result.ok(goals)

    async def search_goals(self, query: str, limit: int = 50) -> Result[list[Goal]]:
        """
        Search goals by title or description.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            Result containing list of matching Goals
        """
        # Use Neo4j text search on title and description
        cypher_query = """
        MATCH (g:Entity {ku_type: 'goal'})
        WHERE toLower(g.title) CONTAINS toLower($query)
           OR toLower(g.description) CONTAINS toLower($query)
        RETURN g
        ORDER BY g.created_at DESC
        LIMIT $limit
        """

        result = await self.backend.execute_query(cypher_query, {"query": query, "limit": limit})
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Goals
        goals = []
        for record in result.value:
            goal_node = record["g"]
            dto = GoalDTO.from_dict(goal_node)
            goals.append(Goal.from_dto(dto))

        return Result.ok(goals)

    # ========================================================================
    # TIME-BASED QUERIES - REMOVED (January 2026)
    # ========================================================================
    # The following methods were removed as duplicates of GoalsSearchService:
    # - get_goals_due_soon() -> Use search.get_due_soon() instead
    # - get_overdue_goals() -> Use search.get_overdue() instead
    #
    # The facade (GoalsService) delegates to search service via:
    # "get_goals_due_soon": ("search", "get_due_soon")
    # "get_overdue_goals": ("search", "get_overdue")
    #
    # GoalsSearchService has custom implementations with Goals-specific
    # status filtering (IN ['active', 'in_progress', 'on_track']).
    # ========================================================================

    # ========================================================================
    # SPECIALIZED OPERATIONS
    # ========================================================================

    async def mark_achieved(self, uid: str) -> Result[Goal]:
        """
        Mark a goal as achieved and publish GoalAchieved event.

        This is a specialized operation that sets status to COMPLETED
        and publishes a GoalAchieved event (high-priority event).

        Args:
            uid: Goal UID

        Returns:
            Result containing updated Goal

        Events Published:
            - GoalAchieved: When goal is successfully marked as achieved
        """
        # Get current goal to calculate metrics
        goal_result = await self.get(uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        current_goal = goal_result.value

        # Update status to completed
        updates = {"status": EntityStatus.COMPLETED.value}
        result = await super().update(uid, updates)

        # Publish GoalAchieved event
        if result.is_ok:
            goal = result.value

            # Calculate duration metrics
            actual_days = None
            planned_days = None
            ahead_of_schedule = False

            if current_goal.created_at:
                actual_days = (datetime.now() - current_goal.created_at).days

            if current_goal.target_date and current_goal.created_at:
                planned_days = (current_goal.target_date - current_goal.created_at).days
                if actual_days and planned_days:
                    ahead_of_schedule = actual_days < planned_days

            event = GoalAchieved(
                goal_uid=goal.uid,
                user_uid=goal.user_uid,
                occurred_at=datetime.now(),
                actual_duration_days=actual_days,
                planned_duration_days=planned_days,
                completed_ahead_of_schedule=ahead_of_schedule,
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Universal Hierarchical Pattern)
    # ========================================================================

    @with_error_handling("get_subgoals", error_type="database", uid_param="parent_uid")
    async def get_subgoals(self, parent_uid: str, depth: int = 1) -> Result[list[Goal]]:
        """
        Get all subgoals of a parent goal.

        Args:
            parent_uid: Parent goal UID
            depth: How many levels deep (1=direct children, 2=children+grandchildren, etc.)

        Returns:
            Result containing list of subgoals ordered by created_at

        Example:
            # Get direct children
            subgoals = await service.get_subgoals("goal_abc123")

            # Get all descendants
            all_subgoals = await service.get_subgoals("goal_abc123", depth=99)
        """
        query = f"""
        MATCH (parent:Entity {{uid: $parent_uid}})
        MATCH (parent)-[:HAS_SUBGOAL*1..{depth}]->(subgoal:Entity)
        RETURN subgoal
        ORDER BY subgoal.created_at
        """

        result = await self.backend.execute_query(query, {"parent_uid": parent_uid})

        if result.is_error:
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.ok([])

        # Convert to Goal models
        goals = []
        for record in result.value:
            goal_data = record["subgoal"]
            goal = self._to_domain_model(goal_data, GoalDTO, Goal)
            goals.append(goal)

        return Result.ok(goals)

    @with_error_handling("get_parent_goal", error_type="database", uid_param="subgoal_uid")
    async def get_parent_goal(self, subgoal_uid: str) -> Result[Goal | None]:
        """
        Get immediate parent of a subgoal (if any).

        Args:
            subgoal_uid: Subgoal UID

        Returns:
            Result containing parent Goal or None if root-level goal
        """
        query = """
        MATCH (subgoal:Entity {uid: $subgoal_uid})
        MATCH (parent:Entity)-[:HAS_SUBGOAL]->(subgoal)
        RETURN parent
        LIMIT 1
        """

        result = await self.backend.execute_query(query, {"subgoal_uid": subgoal_uid})

        if result.is_error:
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.ok(None)

        parent_data = result.value[0]["parent"]
        parent = self._to_domain_model(parent_data, GoalDTO, Goal)
        return Result.ok(parent)

    @with_error_handling("get_goal_hierarchy", error_type="database", uid_param="goal_uid")
    async def get_goal_hierarchy(self, goal_uid: str) -> Result[dict[str, Any]]:
        """
        Get full hierarchy context: ancestors, siblings, children.

        Args:
            goal_uid: Goal UID to get context for

        Returns:
            Result containing hierarchy dict with keys:
            - ancestors: list[Goal] (root to immediate parent)
            - current: Goal
            - siblings: list[Goal] (other children of same parent)
            - children: list[Goal] (immediate children)
            - depth: int (how deep in hierarchy, 0=root)

        Example:
            hierarchy = await service.get_goal_hierarchy("goal_xyz789")
            # {
            # "ancestors": [root_goal, parent_goal],
            # "current": goal_xyz789,
            # "siblings": [sibling1, sibling2],
            # "children": [child1, child2],
            # "depth": 2
            # }
        """
        # Get ancestors
        ancestors_query = """
        MATCH path = (root:Entity)-[:HAS_SUBGOAL*]->(current:Entity {uid: $goal_uid})
        WHERE NOT EXISTS((root)<-[:HAS_SUBGOAL]-())
        RETURN nodes(path) as ancestors
        """

        # Get siblings
        siblings_query = """
        MATCH (current:Entity {uid: $goal_uid})
        OPTIONAL MATCH (parent:Entity)-[:HAS_SUBGOAL]->(current)
        OPTIONAL MATCH (parent)-[:HAS_SUBGOAL]->(sibling:Entity)
        WHERE sibling.uid <> $goal_uid
        RETURN collect(sibling) as siblings
        """

        # Get children
        children_query = """
        MATCH (current:Entity {uid: $goal_uid})
        OPTIONAL MATCH (current)-[:HAS_SUBGOAL]->(child:Entity)
        RETURN collect(child) as children
        """

        # Execute all queries
        current_result = await self.backend.get(goal_uid)
        if current_result.is_error:
            return Result.fail(current_result)

        current_goal = self._to_domain_model(current_result.value, GoalDTO, Goal)

        ancestors_result = await self.backend.execute_query(ancestors_query, {"goal_uid": goal_uid})
        siblings_result = await self.backend.execute_query(siblings_query, {"goal_uid": goal_uid})
        children_result = await self.backend.execute_query(children_query, {"goal_uid": goal_uid})

        # Process ancestors
        ancestors = []
        if (
            not ancestors_result.is_error
            and ancestors_result.value
            and ancestors_result.value[0]["ancestors"]
        ):
            for node in ancestors_result.value[0]["ancestors"][:-1]:  # Exclude current
                goal_data = node
                ancestors.append(self._to_domain_model(goal_data, GoalDTO, Goal))

        # Process siblings
        siblings = []
        if (
            not siblings_result.is_error
            and siblings_result.value
            and siblings_result.value[0]["siblings"]
        ):
            for node in siblings_result.value[0]["siblings"]:
                if node:  # Skip None values
                    goal_data = node
                    siblings.append(self._to_domain_model(goal_data, GoalDTO, Goal))

        # Process children
        children = []
        if (
            not children_result.is_error
            and children_result.value
            and children_result.value[0]["children"]
        ):
            for node in children_result.value[0]["children"]:
                if node:  # Skip None values
                    goal_data = node
                    children.append(self._to_domain_model(goal_data, GoalDTO, Goal))

        return Result.ok(
            {
                "ancestors": ancestors,
                "current": current_goal,
                "siblings": siblings,
                "children": children,
                "depth": len(ancestors),
            }
        )

    @with_error_handling("create_subgoal_relationship", error_type="database")
    async def create_subgoal_relationship(
        self, parent_uid: str, subgoal_uid: str, progress_weight: float = 1.0
    ) -> Result[bool]:
        """
        Create bidirectional parent-child relationship.

        Args:
            parent_uid: Parent goal UID
            subgoal_uid: Subgoal UID
            progress_weight: How much this subgoal contributes to parent progress (default: 1.0)

        Returns:
            Result indicating success

        Note:
            Creates both HAS_SUBGOAL (parent→child) and SUBGOAL_OF (child→parent)
            for efficient bidirectional queries.
        """
        # Validate no cycle (can't make parent a child of its descendant)
        cycle_check = await self._would_create_cycle(parent_uid, subgoal_uid)
        if cycle_check:
            return Result.fail(
                Errors.validation(
                    f"Cannot create subgoal relationship: would create cycle "
                    f"({subgoal_uid} is ancestor of {parent_uid})"
                )
            )

        query = """
        MATCH (parent:Entity {uid: $parent_uid})
        MATCH (subgoal:Entity {uid: $subgoal_uid})

        CREATE (parent)-[:HAS_SUBGOAL {
            progress_weight: $weight,
            created_at: datetime()
        }]->(subgoal)

        CREATE (subgoal)-[:SUBGOAL_OF {
            created_at: datetime()
        }]->(parent)

        RETURN true as success
        """

        result = await self.backend.execute_query(
            query, {"parent_uid": parent_uid, "subgoal_uid": subgoal_uid, "weight": progress_weight}
        )

        if result.is_error:
            return Result.fail(
                Errors.database(operation="create", message="Failed to create subgoal relationship")
            )
        if result.value:
            self.logger.info(
                f"Created subgoal relationship: {parent_uid} -> {subgoal_uid} (weight: {progress_weight})"
            )
            return Result.ok(True)

        return Result.fail(
            Errors.database(operation="create", message="Failed to create subgoal relationship")
        )

    @with_error_handling("remove_subgoal_relationship", error_type="database")
    async def remove_subgoal_relationship(self, parent_uid: str, subgoal_uid: str) -> Result[bool]:
        """
        Remove bidirectional parent-child relationship.

        Args:
            parent_uid: Parent goal UID
            subgoal_uid: Subgoal UID

        Returns:
            Result containing True if relationships were deleted
        """
        query = """
        MATCH (parent:Entity {uid: $parent_uid})-[r1:HAS_SUBGOAL]->(subgoal:Entity {uid: $subgoal_uid})
        MATCH (subgoal)-[r2:SUBGOAL_OF]->(parent)
        DELETE r1, r2
        RETURN count(r1) + count(r2) as deleted_count
        """

        result = await self.backend.execute_query(
            query, {"parent_uid": parent_uid, "subgoal_uid": subgoal_uid}
        )

        if not result.is_error and result.value:
            deleted = result.value[0]["deleted_count"]
            if deleted > 0:
                self.logger.info(f"Removed subgoal relationship: {parent_uid} -> {subgoal_uid}")
                return Result.ok(True)

        return Result.ok(False)

    async def _would_create_cycle(self, parent_uid: str, child_uid: str) -> bool:
        """Check if adding parent->child relationship would create a cycle."""
        query = """
        MATCH (child:Entity {uid: $child_uid})
        MATCH path = (child)-[:HAS_SUBGOAL*]->(parent:Entity {uid: $parent_uid})
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
