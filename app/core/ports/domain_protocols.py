"""
Domain Service Protocols
=========================

SKUEL's Entity Type Protocol Architecture
------------------------------------------

This module defines the service interfaces for SKUEL's complete architecture.
Each entity type has an Operations protocol that services must implement.

ENTITY TYPE PROTOCOLS
---------------------

**Activity Domain Protocols (6):**
    1. TasksOperations[Task]               - Work items and dependencies
    2. GoalsOperations[Goal]               - Objectives and milestones
    3. HabitsOperations[Habit]             - Recurring behaviors and streaks
    4. EventsOperations[Event]             - Calendar items and scheduling
    5. ChoicesOperations[Choice]           - Decisions and outcomes
    6. PrinciplesOperations[Principle]     - Values and alignment

**Curriculum Domain Protocols (3):**
    8. PsOperations[PathStep]          - PathSteps (ps:)
    9. LpOperations[LearningPath]         - Learning Paths (lp:)
    10. (KU uses BackendOperations directly)

**Removed protocols (historical note):**
    - FinancesOperations removed May 2026 (ADR-052 Phase 5) — native expense/budget
      module demolished; invoice module uses the concrete FinanceService facade
    - JournalsOperations removed Feb 2026 — Journal merged into Reports domain
    - MocOperations removed Jan 2026 — MOC is emergent identity, uses PsOperations
    - AnalyticsLifePathService, AnalyticsService — no protocol (internal services)

THE 4 CROSS-CUTTING SYSTEMS
---------------------------

**Foundation & Infrastructure Protocols:**
    1. (UserContextBuilder)   - ~240 fields cross-domain state (no protocol)
    2. SearchOperations       - Unified search across all domains
    3. (AskesisService)       - Life context synthesis (no protocol)
    4. (Conversation)         - Turn-based chat interface (models only)

PROTOCOL DESIGN PATTERNS
------------------------

All protocols share these characteristics:
    - Generic over entity type (Operations[T])
    - Result[T] return types for error handling
    - Async methods for database operations
    - BackendOperations as base (CRUD + queries)

Implementation Pattern:
    # TasksOperations is a *backend-level* protocol — it types self.backend inside
    # BaseService[TasksOperations, Task]. It is NOT a service-level protocol; facade
    # services (TasksService, GoalsService, etc.) do not implement it directly.
    class TasksService(BaseService[TasksOperations, Task]):
        # self.backend: TasksOperations[Task]  (UniversalNeo4jBackend[Task])
        ...

Architectural Note (Updated 2025-10-19):
    Protocols now use Result[T] return types to match actual implementations.
    This aligns with SKUEL's "Results Internally, Exceptions at Boundaries" pattern.
    The UniversalNeo4jBackend (and all backends) return Result[T], so protocols
    must declare Result[T] to maintain Liskov Substitution Principle.

See Also:
    /core/models/enums/ - Domain enum definitions (entity_enums.py, activity_enums.py, etc.)
    /services_bootstrap.py - Service composition
    /adapters/persistence/neo4j/universal_backend.py - Generic backend
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.models.type_hints import UserUID
from core.ports.base_protocols import (
    BackendOperations,
    GraphRelationshipOperations,
    HierarchyOperations,
)
from core.ports.query_types import (
    AdaptiveLearningPathResult,
    AtRiskHabitsResult,
    ChoiceStats,
    ContextDashboard,
    ContextHealthResult,
    ContextSummary,
    EventStats,
    FutureContextStateResult,
    GoalStats,
    GraphContextResult,
    HabitStats,
    NextActionResult,
    ParentProgressResult,
    PrincipleStats,
    TaskStats,
)

if TYPE_CHECKING:
    import builtins
    from datetime import date

    from core.models.choice.choice import Choice
    from core.models.event.event import Event
    from core.models.event.event_update_intent import EventUpdateIntent
    from core.models.goal.goal import Goal
    from core.models.habit.habit import Habit
    from core.models.principle.principle import Principle
    from core.models.relationship_names import RelationshipName
    from core.models.task.task import Task
    from core.models.task.task_update_intent import TaskUpdateIntent
    from core.models.type_hints import EntityUID, FilterParams, Metadata, Neo4jProperties
    from core.utils.result_simplified import Result


@runtime_checkable
class TasksOperations(
    BackendOperations["Task"], GraphRelationshipOperations, HierarchyOperations, Protocol
):
    """Core task management operations. Uses Task domain model (EntityType.TASK).

    **Two Entry Point Patterns (by design):**

    1. **BackendOperations[Task] (Generic CRUD):**
       Use when you have a domain model instance.
       - `create(task: Task)` → `Result[Task]`
       - `get(uid: str)` → `Result[Task | None]`
       - `update(task: Task)` → `Result[Task]`
       - `delete(uid: str)` → `Result[bool]`

    2. **Domain Entry Points (Request Processing):**
       Use when processing raw API requests or dicts.
       - `create_task(data: Metadata)` → `Result[EntityUID]`
       - `get_task(task_id)` → Semantic alias for get()
       - `update_task(task_id, data: Metadata)` → `Result[bool]`
       - `delete_task(task_id)` → `Result[bool]`

    **Why both exist:**
    The domain-specific methods predate the generic pattern and serve as
    request-processing entry points. They accept dicts (Metadata) and handle
    validation/conversion internally. The generic methods expect pre-validated
    domain models.

    **Which to use:**
    - Services calling other services → use generic (create, get, update)
    - API routes processing requests → use domain (create_task, get_task)

    **Inherited from GraphRelationshipOperations:**
    - get_related_uids(uid, relationship_type, direction, limit, properties)
    - count_related(uid, relationship_type, direction, properties)

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_task(self, data: Metadata) -> Result[EntityUID]:
        """Create task from request data. Use create() if you have a domain model."""
        ...

    async def update_task(self, task_id: EntityUID, intent: TaskUpdateIntent) -> Result[Task]:
        """Update a task (ADR-066 typed update contract). Returns Result[Task] (the updated
        task). The intent's edge fields are split off and applied as graph-edge mutations;
        its remaining set fields are written as node properties."""
        ...

    async def delete_task(self, task_id: EntityUID) -> Result[bool]:
        """Delete task by ID. Alias for delete() with semantic naming."""
        ...

    # ========================================================================
    # QUERY METHODS
    # ========================================================================

    async def get_task(self, task_id: EntityUID) -> Result[Task]:
        """Get task by ID. Not found is an error."""
        ...

    async def get_user_tasks(self, user_uid: UserUID) -> Result[list[Task]]:
        """Get all tasks for a user."""
        ...

    async def complete_task(
        self,
        uid: str,
        actual_minutes: int | None = None,
        quality_score: int | None = None,
    ) -> Result[Task]:
        """Complete a task without a user_context (cascade derives the owner)."""
        ...

    async def get_user_assigned_tasks(self, user_uid: UserUID) -> Result[list[Task]]:
        """Get tasks assigned to a user."""
        ...

    async def get_assigned_tasks(
        self,
        user_uid: UserUID,
        include_completed: bool = False,
        limit: int = 100,
    ) -> Result[list[Neo4jProperties]]:
        """Get tasks assigned to a user via ASSIGNED_TO relationship (raw properties)."""
        ...

    async def get_tasks_requiring_knowledge(self, knowledge_uid: str) -> Result[list[Task]]:
        """Get tasks that require a specific knowledge unit."""
        ...

    async def get_tasks_reinforcing_habit(self, habit_uid: str) -> Result[list[Neo4jProperties]]:
        """Get raw node props for tasks linked to a habit via REINFORCES_HABIT."""
        ...

    async def get_habit_links_for_tasks(self, task_uids: list[str]) -> Result[dict[str, str]]:
        """Map task_uid → reinforced habit_uid via REINFORCES_HABIT edges (batch)."""
        ...

    async def get_user_entities(
        self,
        user_uid: UserUID,
        relationship_type: RelationshipName | None = None,
        filters: FilterParams | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        sort_order: str = "desc",
    ) -> Result[tuple[list[Task], int]]:
        """
        Get all tasks for a user via relationship traversal.

        This is the PRIMARY method for user-specific entity queries.
        Replaces property-based filtering with graph relationship traversal.

        Args:
            user_uid: User UID to query for
            relationship_type: Override relationship type (default uses OWNS)
            filters: Filter specification (use ActivityFilterSpec for type hints)
            limit: Maximum results (default 100)
            offset: Skip first N results (default 0)
            sort_by: Field to sort by
            sort_order: "asc" or "desc" (default "desc")

        Returns:
            Result containing (list of Task, total count)

        Type Hint Example:
            filters: ActivityFilterSpec = {"status": "active", "priority": "high"}
            await service.get_user_entities(user_uid, filters=filters)
        """
        ...

    async def get_user_items_in_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
        date_field: str | list[str] | None = None,
    ) -> Result[list[Task]]:
        """
        Get user's tasks in date range - unified interface for meta-services.

        Standard query pattern used by Calendar and Reports services for
        efficient Cypher-level filtering (10-100x faster than in-memory).

        Args:
            user_uid: User identifier
            start_date: Range start date
            end_date: Range end date
            include_completed: Include completed tasks (default: False)
            date_field: Optional override of the configured due_date field;
                a list means OR semantics across fields — the calendar asks for
                ["due_date", "scheduled_date"] so scheduled-only tasks render

        Returns:
            Result[list[Task]] filtered by user, date range, and completion status

        Implementation:
            Filters by user_uid, the requested date field(s), and excludes completed
            status unless include_completed=True. Uses build_user_activity_query()

        Date Added: October 29, 2025 (Unified Query Pattern for Meta-Services)
        """
        ...

    # NOTE: get_related_uids() and count_related() inherited from GraphRelationshipOperations

    # ========================================================================
    # LEARNING LOOP METHODS (ADR-048)
    # ========================================================================

    async def get_user_learning_state(self, user_uid: UserUID) -> Result[Neo4jProperties]:
        """Get learning state properties from User node."""
        ...

    async def update_user_learning_state(
        self, user_uid: UserUID, properties: Neo4jProperties
    ) -> Result[bool]:
        """Update learning state properties on User node."""
        ...

    # ========================================================================
    # HIERARCHY EXTENSIONS (Task-specific, beyond generic HierarchyOperations)
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[TaskStats]:
        """Count task stats: total, completed, overdue."""
        ...

    async def calculate_parent_progress(self, parent_uid: str) -> Result[ParentProgressResult]:
        """Calculate weighted subtask completion percentage."""
        ...

    async def get_transitive_dependencies(
        self, task_uid: str, rel_type: RelationshipName, max_depth: int
    ) -> Result[builtins.list[str]]:
        """Get transitive dependency UIDs via variable-length path traversal."""
        ...

    async def dependency_path_exists(
        self, from_uid: str, to_uid: str, rel_type: RelationshipName
    ) -> Result[bool]:
        """Report whether a directed ``rel_type`` path exists from one task to another
        (unbounded reachability — powers the dependency cycle guard)."""
        ...


@runtime_checkable
class EventsOperations(
    BackendOperations["Event"], GraphRelationshipOperations, HierarchyOperations, Protocol
):
    """Core event management operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, delete, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Adds event-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_event(self, data: Metadata) -> Result[EntityUID]:
        """Create a new event and return its ID. Returns Result[str]."""
        ...

    async def update_event(self, event_id: EntityUID, intent: EventUpdateIntent) -> Result[Event]:
        """Update an existing event (ADR-066 typed update contract). Returns Result[Event]
        (the updated event). The intent's two edge fields are split off and applied as
        graph-edge mutations; its remaining set fields are written as node properties."""
        ...

    async def get_event(self, event_id: EntityUID) -> Result[Event]:
        """Get an event by ID. Not found is an error."""
        ...

    async def get_user_events(self, user_uid: UserUID) -> Result[list[Event]]:
        """Get all events for a user."""
        ...

    async def list_events(
        self, limit: int = 100, filters: Metadata | None = None, offset: int = 0
    ) -> Result[tuple[list[Event], int]]:
        """List events with optional filters and pagination. Returns Result[(events, total_count)]."""
        ...

    async def count_events(self, filters: Metadata | None = None) -> Result[int]:
        """Count events matching filters efficiently. Returns Result[int]."""
        ...

    async def get_user_items_in_range(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Event]]:
        """
        Get user's events in date range - unified interface for meta-services.

        Args:
            user_uid: User identifier
            start_date: Range start date
            end_date: Range end date
            include_completed: Include completed/cancelled events (default: False)

        Returns:
            Result[list[Event]] filtered by user, event_date, and completion status

        Implementation:
            Filters by user_uid, event_date field, excludes completed/cancelled
            unless include_completed=True

        Date Added: October 29, 2025 (Unified Query Pattern for Meta-Services)
        """
        ...

    async def add_attendee(
        self,
        event_uid: str,
        attendee_uid: UserUID,
        actor_uid: UserUID,
        role: str,
        status: str,
        set_status_on_match: bool = False,
    ) -> Result[str]:
        """Upsert one user's attendance of an event (ADR-086, staged).

        Idempotent — a repeated add never rewrites when the attendance began.
        ``set_status_on_match`` additionally applies ``status`` to an existing
        attendance (the target user consenting to their own invite). Returns
        the attendance status after the write.
        """
        ...

    async def remove_attendee(
        self,
        event_uid: str,
        attendee_uid: UserUID,
        only_if_status: str | None = None,
    ) -> Result[bool]:
        """Remove one user's attendance of an event (ADR-086, staged).

        ``only_if_status`` guards the removal to attendances in that status
        (the organizer's revoke-pending-invite path). Returns whether an
        attendance was removed.
        """
        ...

    # NOTE: get_related_uids() and count_related() inherited from GraphRelationshipOperations

    async def get_events_in_range(
        self,
        start_date: str,
        end_date: str,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Neo4jProperties]]:
        """Get events within a date range (raw properties)."""
        ...

    async def get_recurring_events(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get events with a recurrence pattern (raw properties)."""
        ...

    async def get_events_on_date(
        self, event_date: str, user_uid: UserUID, exclude_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get events on a date for conflict detection (raw properties)."""
        ...

    async def get_events_reinforcing_habit(
        self, habit_uid: str, user_uid: UserUID | None = None
    ) -> Result[list[Neo4jProperties]]:
        """Get raw node props for events linked to a habit via REINFORCES_HABIT."""
        ...

    async def get_habit_links_for_events(self, event_uids: list[str]) -> Result[dict[str, str]]:
        """Map event_uid → reinforced habit_uid via REINFORCES_HABIT edges (batch)."""
        ...

    async def get_goal_links_for_events(
        self, event_uids: list[str]
    ) -> Result[dict[str, list[str]]]:
        """Map event_uid → list of contributed goal_uids via CONTRIBUTES_TO_GOAL edges (batch)."""
        ...

    async def get_goal_celebration_stats(
        self, user_uid: UserUID, start_date: str
    ) -> Result[dict[str, Any]]:
        """Aggregate completed events that celebrate goals via CELEBRATES_GOAL."""
        ...

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[EventStats]:
        """Count event stats: total, scheduled, today."""
        ...

    async def count_recent_reschedules(self, user_uid: UserUID) -> Result[int]:
        """Count events rescheduled in last 30 days."""
        ...

    async def count_events_in_date_range(
        self, user_uid: UserUID, start_date: str, end_date: str
    ) -> Result[int]:
        """Count events in a date range."""
        ...


@runtime_checkable
class HabitsOperations(
    BackendOperations["Habit"], GraphRelationshipOperations, HierarchyOperations, Protocol
):
    """Core habit tracking operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, delete, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Adds habit-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_habit(self, data: Metadata) -> Result[EntityUID]:
        """Create a new habit and return its ID. Returns Result[str]."""
        ...

    async def update_habit(self, habit_id: str, data: Metadata) -> Result[bool]:
        """Update habit details. Returns Result[bool]."""
        ...

    async def archive_habit(self, habit_id: str) -> Result[bool]:
        """
        Archive a habit (soft delete — status transition to "archived").

        This is intentional domain logic: habits represent behavioral patterns
        and are archived, not destroyed. Use delete() from BackendOperations
        only for test cleanup. Returns Result[bool].
        """
        ...

    async def get_habit(self, habit_id: str) -> Result[Habit]:
        """Get a habit by ID. Not found is an error."""
        ...

    async def get_user_habits(self, user_uid: UserUID) -> Result[list[Habit]]:
        """Get all habits for a user. Returns Result[list[Habit]]."""
        ...

    async def list_by_user(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[builtins.list[Habit]]:
        """List all habits for a user. Returns Result[list[Habit]]."""
        ...

    async def get_user_items_in_range(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[builtins.list[Habit]]:
        """
        Get user's habits in date range - unified interface for meta-services.

        Args:
            user_uid: User identifier
            start_date: Range start date (for display, habits are recurring)
            end_date: Range end date
            include_completed: Include archived habits (default: False)

        Returns:
            Result[list[Habit]] filtered by user and archived status

        Implementation:
            Filters by user_uid, excludes archived habits unless include_completed=True
            Note: Habits don't have specific dates but are included for consistency

        Date Added: October 29, 2025 (Unified Query Pattern for Meta-Services)
        """
        ...

    # NOTE: get_related_uids() and count_related() inherited from GraphRelationshipOperations

    async def get_active_habits_prioritized(
        self,
        user_uid: UserUID,
        terminal_statuses: list[str],
        limit: int = 20,
    ) -> Result[builtins.list[Neo4jProperties]]:
        """Get active habits pre-sorted for prioritization (raw properties)."""
        ...

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[HabitStats]:
        """Count habit stats: total, active, streaks."""
        ...

    # Badge operations
    async def get_user_badges(self, user_uid: UserUID) -> Result[builtins.list[Neo4jProperties]]:
        """Get all badges earned by a user via EARNED_BADGE relationships."""
        ...

    async def get_habit_badges(self, habit_uid: str) -> Result[builtins.list[Neo4jProperties]]:
        """Get all badges unlocked by a specific habit."""
        ...

    async def check_badge_already_earned(
        self, user_uid: UserUID, habit_uid: str, badge_id: str
    ) -> Result[bool]:
        """Check if user has already earned this badge for this habit."""
        ...

    async def award_badge(
        self,
        user_uid: UserUID,
        habit_uid: str,
        badge_id: str,
        badge_name: str,
        badge_description: str,
        badge_tier: str,
        streak_length: int,
        occurred_at: str,
    ) -> Result[bool]:
        """Create achievement record and link to user and habit."""
        ...

    async def check_user_badge_earned(self, user_uid: UserUID, badge_id: str) -> Result[bool]:
        """Check if user has earned a badge (cross-habit, no habit_uid filter)."""
        ...

    async def award_user_badge(
        self,
        user_uid: UserUID,
        badge_id: str,
        badge_name: str,
        badge_description: str,
        badge_tier: str,
        badge_category: str,
        threshold_value: int,
        occurred_at: str,
    ) -> Result[bool]:
        """Create achievement record linked to user only (cross-habit badges)."""
        ...

    async def get_user_badge_stats(self, user_uid: UserUID) -> Result[Neo4jProperties]:
        """Get aggregated habit stats for badge evaluation."""
        ...

    async def get_goal_links_for_habits(
        self, habit_uids: list[str]
    ) -> Result[dict[str, list[str]]]:
        """Map habit_uid → list of supporting goal_uids via SUPPORTS_GOAL edges (batch)."""
        ...


# NOTE: FinancesOperations removed (ADR-052 Phase 5) — native expense/budget
# module demolished. The surviving invoice module is wrapped by the concrete
# FinanceService facade (core.services.finance_service), which routes type
# against directly (facade-tier convention) — no route-facing protocol needed.


@runtime_checkable
class GoalsOperations(
    BackendOperations["Goal"], GraphRelationshipOperations, HierarchyOperations, Protocol
):
    """Core goal management operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, delete, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Inherits from GraphRelationshipOperations:
    - get_related_uids(uid, relationship_type, direction, limit, properties)
    - count_related(uid, relationship_type, direction, properties)

    Adds goal-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_goal(self, data: Metadata) -> Result[str]:
        """Create a new goal and return its ID. Returns Result[str]."""
        ...

    async def update_goal(self, goal_id: str, data: Metadata) -> Result[bool]:
        """Update an existing goal. Returns Result[bool]."""
        ...

    async def delete_goal(self, goal_id: str) -> Result[bool]:
        """Delete a goal. Returns Result[bool]."""
        ...

    async def get_goal(self, goal_id: str) -> Result[Goal]:
        """Get a goal by ID. Not found is an error."""
        ...

    async def get_user_goals(self, user_uid: UserUID) -> Result[list[Goal]]:
        """Get all goals for a user. Returns flat list (not paginated tuple)."""
        ...

    async def get_user_items_in_range(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Goal]]:
        """
        Get user's goals in date range - unified interface for meta-services.

        Args:
            user_uid: User identifier
            start_date: Range start date
            end_date: Range end date
            include_completed: Include completed/abandoned goals (default: False)

        Returns:
            Result[list[Goal]] filtered by user, target_date, and completion status

        Implementation:
            Filters by user_uid, target_date field, excludes completed/abandoned
            unless include_completed=True

        Date Added: October 29, 2025 (Unified Query Pattern for Meta-Services)
        """
        ...

    # NOTE: get_related_uids() and count_related() inherited from GraphRelationshipOperations

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[GoalStats]:
        """Count goal stats: total, active, completed."""
        ...

    async def find_linked_goals_for_task(
        self, task_uid: str, user_uid: UserUID
    ) -> Result[list[str]]:
        """Find goal UIDs linked to a task via SUPPORTS_GOAL."""
        ...

    async def count_linked_tasks(self, goal_uid: str, user_uid: UserUID) -> Result[dict[str, int]]:
        """Count total and completed tasks linked to a goal."""
        ...

    async def find_linked_goals_for_habit(
        self, habit_uid: str, user_uid: UserUID
    ) -> Result[list[str]]:
        """Find goal UIDs linked to a habit via SUPPORTS_GOAL."""
        ...

    async def count_linked_habits_avg_streak(
        self, goal_uid: str, user_uid: UserUID
    ) -> Result[dict[str, Any]]:
        """Count habits linked to a goal and compute their average streak."""
        ...

    async def get_achievement_context(
        self, goal_uid: str, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:
        """Fetch goal properties and related entities for recommendation generation."""
        ...


# NOTE: JournalsOperations REMOVED (February 2026) - Journal merged into Reports
# Use SubmissionsCoreService for journal CRUD (report_type=JOURNAL)


@runtime_checkable
class ChoicesOperations(
    BackendOperations["Choice"], GraphRelationshipOperations, HierarchyOperations, Protocol
):
    """Core choice management operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, delete, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Inherits from GraphRelationshipOperations:
    - get_related_uids(uid, relationship_type, direction, limit, properties)
    - count_related(uid, relationship_type, direction, properties)

    Adds choice-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_choice(self, data: Metadata) -> Result[str]:
        """Create a new choice and return its ID. Returns Result[str]."""
        ...

    async def delete_choice(self, choice_id: str) -> Result[bool]:
        """Delete a choice. Returns Result[bool]."""
        ...

    async def resolve_choice(self, choice_id: str, resolution: Metadata) -> Result[bool]:
        """Mark a choice as resolved with outcome data. Returns Result[bool]."""
        ...

    async def get_choice(self, choice_id: str) -> Result[Choice]:
        """Get a choice by ID. Not found is an error."""
        ...

    async def find_choices(
        self, filters: FilterParams | None = None, limit: int = 100
    ) -> Result[list[Choice]]:
        """Find choices with filters and limit."""
        ...

    async def get_user_choices(self, user_id: UserUID) -> Result[list[Choice]]:
        """Get all choices for a user."""
        ...

    async def get_pending_choices(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get pending/undecided choices for a user (raw properties)."""
        ...

    async def get_choices_needing_decision(
        self, user_uid: UserUID, end_date: str
    ) -> Result[list[Neo4jProperties]]:
        """Get choices needing decision by deadline (raw properties)."""
        ...

    async def count_choices(self, filters: FilterParams | None = None) -> Result[int]:
        """Count choices matching filters. Returns Result[int]."""
        ...

    async def get_user_items_in_range(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Choice]]:
        """
        Get user's choices in date range - unified interface for meta-services.

        Args:
            user_uid: User identifier
            start_date: Range start date
            end_date: Range end date
            include_completed: Include archived choices (default: False)

        Returns:
            Result[list[Choice]] filtered by user and archived status

        Implementation:
            Filters by user_uid, excludes archived choices unless include_completed=True
            Note: Choices may not have specific dates but are included for consistency

        Date Added: October 29, 2025 (Unified Query Pattern for Meta-Services)
        """
        ...

    # NOTE: get_related_uids() and count_related() inherited from GraphRelationshipOperations

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[ChoiceStats]:
        """Count choice stats: total, pending, decided."""
        ...


@runtime_checkable
class PrinciplesOperations(
    BackendOperations["Principle"], GraphRelationshipOperations, HierarchyOperations, Protocol
):
    """Core principle management operations. Uses Principle domain model (EntityType.PRINCIPLE).

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, delete, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Adds principle-specific operations below.

    Deactivation note: deactivate via the facade's typed-intent update path
    (PrincipleUpdateIntent(is_active=False), ADR-066) rather than removing the
    principle from the graph. delete_principle() performs a hard delete — only
    use for test cleanup or permanent removal.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    # ========================================================================
    # CRUD METHODS
    # ========================================================================

    async def create_principle(self, data: Metadata) -> Result[EntityUID]:
        """Create a new principle and return its ID."""
        ...

    async def delete_principle(self, principle_uid: EntityUID) -> Result[bool]:
        """Delete a principle. Principles have no soft-delete; deactivate via the
        typed-intent update path (is_active=False) for removal-free deactivation."""
        ...

    async def get_principle(self, principle_uid: str) -> Result[Principle]:
        """Get a principle by ID. Not found is an error."""
        ...

    async def get_user_principles(self, user_uid: UserUID) -> Result[list[Principle]]:
        """Get all principles for a user."""
        ...

    async def get_user_items_in_range(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Principle]]:
        """Get user's principles adopted within a date range.

        Unified interface for meta-services (Calendar, Reports) that query across
        all activity domains. Principles filter on adopted_date and is_active (bool)
        rather than the status enum used by other activity domains.

        Args:
            user_uid: User identifier
            start_date: Lower bound on adopted_date (inclusive)
            end_date: Upper bound on adopted_date (inclusive)
            include_completed: When True, inactive (is_active=False) principles are included

        Returns:
            Result[list[Principle]] filtered by adopted_date range and active state
        """
        ...

    # NOTE: get_related_uids() and count_related() inherited from GraphRelationshipOperations

    async def get_principles_needing_review(
        self,
        cutoff_date: str,
        user_uid: UserUID | None = None,
        limit: int = 100,
        prioritize_never_reviewed: bool = False,
    ) -> Result[list[Neo4jProperties]]:
        """Get active principles whose last_review_date is before cutoff (raw properties)."""
        ...

    async def get_principles_due_for_review(
        self,
        cutoff_date: str,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Neo4jProperties]]:
        """Get active principles due for review — last_review_date <= cutoff (raw properties)."""
        ...

    async def get_related_principles_by_traversal(
        self, uid: str, depth: int, limit: int = 10
    ) -> Result[list[Neo4jProperties]]:
        """Get principles related via RELATED_TO traversal (raw properties)."""
        ...

    async def get_principles_by_category(
        self, category: str, exclude_uid: str, limit: int = 10
    ) -> Result[list[Neo4jProperties]]:
        """Get active principles in a category, excluding one UID (raw properties)."""
        ...

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[PrincipleStats]:
        """Count principle stats: total, core, active."""
        ...

    async def get_choice_influence_stats(
        self, principle_uid: str, user_uid: UserUID, period_days: int
    ) -> Result[Neo4jProperties]:
        """Get stats on how a principle has influenced choices."""
        ...


# ============================================================================
# RELATIONSHIP SERVICE PROTOCOL
# ============================================================================
# Added: November 11, 2025
# Purpose: Protocol interface for the relationship service injected into
# domain services (satisfied by UnifiedRelationshipService). The per-domain
# *RelationshipOperations children were contract residue of the pre-
# CrossDomainQueryService design (every member phantom) and were deleted
# 2026-06 — cross-domain reads live on CrossDomainQueryService / the typed
# cross-context readers; registry reads go through get_related_uids.


@runtime_checkable
class BaseRelationshipOperations(Protocol):
    """
    Protocol for the relationship service consumed by domain services.

    Satisfied by UnifiedRelationshipService: cross-domain context retrieval
    plus registry-keyed related-UID reads.
    """

    async def get_cross_domain_context(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[GraphContextResult]:
        """
        Get cross-domain relationship context for an entity.

        Args:
            uid: Entity UID
            depth: Graph traversal depth (default 2)
            min_confidence: Minimum path confidence filter (default 0.7)

        Returns dict with keys like "goals", "knowledge", "principles", etc.
        Each value is a list of related entity UIDs or entity objects.
        """
        ...

    async def get_related_uids(
        self, relationship_key: str, entity_uid: EntityUID
    ) -> Result[builtins.list[str]]:
        """
        Get UIDs of related entities by relationship key.

        Args:
            relationship_key: Key from config (e.g., "knowledge", "principles", "subtasks")
            entity_uid: Entity UID

        Returns:
            Result[list[str]] of related UIDs
        """
        ...


@runtime_checkable
class UserContextOperations(Protocol):
    """User context operations for context-aware dashboard/summary reads.

    Cache invalidation is NOT part of this protocol: every real invalidation
    routes through UserActivityService.invalidate_context / UserService via the
    event bus, never services.context. Declaring it here was dead (UserContextService
    does not implement it) and would invite a second invalidation path.
    """

    async def get_context_dashboard(
        self,
        user_uid: UserUID,
        include_predictions: bool = True,
        time_window: str = "7d",
    ) -> Result[ContextDashboard]:
        """Get unified context dashboard for user."""
        ...

    async def get_context_summary(
        self,
        user_uid: UserUID,
        include_insights: bool = True,
    ) -> Result[ContextSummary]:
        """Get concise context summary for user."""
        ...

    async def get_next_action(self, user_uid: UserUID) -> Result[NextActionResult]:
        """Get AI-recommended next action based on context."""
        ...

    async def get_at_risk_habits(self, user_uid: UserUID) -> Result[AtRiskHabitsResult]:
        """Get habits at risk of breaking streaks."""
        ...

    async def get_adaptive_learning_path(
        self, user_uid: UserUID
    ) -> Result[AdaptiveLearningPathResult]:
        """Get adaptive learning path recommendations."""
        ...

    async def predict_future_context_state(
        self, user_uid: UserUID
    ) -> Result[FutureContextStateResult]:
        """Predict future context state based on current patterns."""
        ...

    async def get_context_health(self, user_uid: UserUID) -> Result[ContextHealthResult]:
        """Get overall context health metrics."""
        ...

    async def complete_task_with_context(
        self,
        task_uid: str,
        user_uid: UserUID,
        completion_context: dict[str, Any] | None = None,
        reflection_notes: str = "",
    ) -> Result[Task]:
        """Complete task with context awareness."""
        ...

    async def create_tasks_from_goal_context(
        self,
        goal_uid: str,
        user_uid: UserUID,
        context_preferences: dict[str, Any] | None = None,
        auto_create: bool = True,
    ) -> Result[list[Task]]:
        """Create contextually relevant tasks from goal."""
        ...

    async def complete_habit_with_context(
        self,
        habit_uid: str,
        user_uid: UserUID,
        completion_quality: str = "good",
        environmental_factors: dict[str, Any] | None = None,
    ) -> Result[Habit]:
        """Complete habit with context awareness."""
        ...
