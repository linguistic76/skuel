"""
Domain Service Protocols
=========================

SKUEL's 14-Domain + 4-System Protocol Architecture
---------------------------------------------------

This module defines the service interfaces for SKUEL's complete architecture.
Each domain has an Operations protocol that services must implement.

THE 14 DOMAINS AND THEIR PROTOCOLS
----------------------------------

**Activity Domain Protocols (7):**
    1. TasksOperations[Task]           - Work items and dependencies
    2. GoalsOperations[Goal]           - Objectives and milestones
    3. HabitsOperations[Habit]         - Recurring behaviors and streaks
    4. EventsOperations[Event]         - Calendar items and scheduling
    5. ChoicesOperations[Choice]       - Decisions and outcomes
    6. PrinciplesOperations[Principle] - Values and alignment
    7. FinancesOperations[ExpensePure] - Expenses and budgets

**Curriculum Domain Protocols (3):**
    8. KuOperations[KnowledgeUnit]     - Knowledge Units (ku:)
    9. LearningStepOperations[LS]      - Learning Steps (ls:)
    10. LearningPathsOperations[LP]    - Learning Paths (lp:)

**Content/Organization Domain Protocols (4):**
    11. JournalsOperations[JournalPure] - File processing (via Assignments)
    12. MocOperations[Moc]              - Map of Content organization
    13. (ReportLifePathService)         - Life goal alignment (no protocol)
    14. (ReportService)                 - Statistical aggregation (no protocol)

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
    class TasksService(TasksOperations[Task]):
        def __init__(self, backend: BackendOperations[Task]):
            self.backend = backend  # UniversalNeo4jBackend[Task]

Architectural Note (Updated 2025-10-19):
    Protocols now use Result[T] return types to match actual implementations.
    This aligns with SKUEL's "Results Internally, Exceptions at Boundaries" pattern.
    The UniversalNeo4jBackend (and all backends) return Result[T], so protocols
    must declare Result[T] to maintain Liskov Substitution Principle.

See Also:
    /core/models/shared_enums.py - Domain enum definitions
    /core/utils/services_bootstrap.py - Service composition
    /adapters/persistence/neo4j/universal_backend.py - Generic backend
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.models.relationship_names import RelationshipName
from core.services.protocols.base_protocols import (
    BackendOperations,
    GraphRelationshipOperations,
)
from core.services.protocols.query_types import (
    GraphContextResult,
)

if TYPE_CHECKING:
    import builtins
    from datetime import date, datetime

    from core.models.choice.choice import Choice
    from core.models.event.event import Event
    from core.models.finance.finance_pure import BudgetPure, ExpensePure
    from core.models.goal.goal import Goal
    from core.models.habit.habit import Habit
    from core.models.journal.journal_pure import JournalPure
    from core.models.principle.principle import Principle
    from core.models.task.task import Task
    from core.models.type_hints import EntityUID, Metadata
    from core.utils.result_simplified import Result


@runtime_checkable
class TasksOperations(BackendOperations["Task"], GraphRelationshipOperations, Protocol):
    """Core task management operations.

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
        """Create task from request data. Use create() if you have a Task model."""
        ...

    async def update_task(self, task_id: EntityUID, data: Metadata) -> Result[bool]:
        """Update task from request data. Use update() if you have a Task model."""
        ...

    async def delete_task(self, task_id: EntityUID) -> Result[bool]:
        """Delete task by ID. Alias for delete() with semantic naming."""
        ...

    async def complete_task(self, task_id: EntityUID) -> Result[bool]:
        """Mark a task as completed. Domain-specific state transition."""
        ...

    # ========================================================================
    # QUERY METHODS
    # ========================================================================

    async def get_task(self, task_id: EntityUID) -> Result[Task]:
        """Get task by ID. Not found is an error."""
        ...

    async def get_user_tasks(self, user_uid: str) -> Result[list[Task]]:
        """Get all tasks for a user. Returns Result[list[Task]]."""
        ...

    async def get_tasks_batch(self, uids: list[str]) -> Result[list[Task | None]]:
        """Batch load multiple tasks by UIDs. Returns Result[list[Task | None]]."""
        ...

    async def get_user_assigned_tasks(self, user_uid: str) -> Result[list[Task]]:
        """Get tasks assigned to a user. Returns Result[list[Task]]."""
        ...

    async def get_tasks_requiring_knowledge(self, knowledge_uid: str) -> Result[list[Task]]:
        """Get tasks that require a specific knowledge unit. Returns Result[list[Task]]."""
        ...

    async def get_user_entities(
        self,
        user_uid: str,
        relationship_type: str | None = None,
        filters: dict[str, Any] | None = None,
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
            Result containing (list of Tasks, total count)

        Type Hint Example:
            filters: ActivityFilterSpec = {"status": "active", "priority": "high"}
            await service.get_user_entities(user_uid, filters=filters)
        """
        ...

    # ========================================================================
    # DEPENDENCY METHODS
    # ========================================================================

    async def get_task_dependencies(self, task_uid: str) -> Result[list[Task]]:
        """Get dependencies for a task. Returns Result[list[Task]]."""
        ...

    async def create_task_dependency(
        self, task_uid: str, depends_on_uid: str, dependency_type: str = "blocks"
    ) -> Result[bool]:
        """Create a dependency between tasks. Returns Result[bool]."""
        ...

    # ========================================================================
    # RELATIONSHIP METHODS
    # ========================================================================

    async def link_task_to_knowledge(
        self,
        task_uid: str,
        knowledge_uid: str,
        knowledge_score_required: float = 0.8,
        is_learning_opportunity: bool = False,
    ) -> Result[bool]:
        """
        Link task to required knowledge unit.
        Creates: (Task)-[:REQUIRES_KNOWLEDGE]->(Knowledge)
        """
        ...

    async def link_task_to_goal(
        self,
        task_uid: str,
        goal_uid: str,
        contribution_percentage: float = 0.1,
        milestone_uid: str | None = None,
    ) -> Result[bool]:
        """
        Link task to goal it contributes to.
        Creates: (Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)
        """
        ...

    async def get_task_cross_domain_context(
        self, task_uid: str, depth: int = 2
    ) -> Result[GraphContextResult]:
        """
        Get complete cross-domain context for a task with configurable graph traversal depth.

        Returns task with all its relationships:
        - Prerequisites (other tasks)
        - Required knowledge
        - Contributing goals
        - Applied knowledge
        - Dependencies

        Args:
            task_uid: Task UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)

        Returns:
            Result[GraphContextResult]: Type-safe cross-domain context
        """
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
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

        Returns:
            Result[list[Task]] filtered by user, date range, and completion status

        Implementation:
            Filters by user_uid, due_date field, and excludes completed status
            unless include_completed=True. Uses CypherGenerator.build_user_activity_query()

        Date Added: October 29, 2025 (Unified Query Pattern for Meta-Services)
        """
        ...

    # NOTE: get_related_uids() and count_related() inherited from GraphRelationshipOperations


@runtime_checkable
class EventsOperations(BackendOperations["Event"], GraphRelationshipOperations, Protocol):
    """Core event management operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, DETACH DELETE, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Adds event-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_event(self, data: Metadata) -> Result[EntityUID]:
        """Create a new event and return its ID. Returns Result[str]."""
        ...

    async def update_event(self, event_id: EntityUID, data: Metadata) -> Result[bool]:
        """Update an existing event. Returns Result[bool]."""
        ...

    async def cancel_event(self, event_id: EntityUID) -> Result[bool]:
        """Cancel an event. Returns Result[bool]."""
        ...

    async def get_event(self, event_id: EntityUID) -> Result[Metadata]:
        """Get an event by ID. Not found is an error."""
        ...

    async def get_user_events(self, user_uid: str) -> Result[list[Metadata]]:
        """Get all events for a user. Returns Result[list[Event]]."""
        ...

    async def list_events(
        self, limit: int = 100, filters: Metadata | None = None, offset: int = 0
    ) -> Result[tuple[list[Metadata], int]]:
        """List events with optional filters and pagination. Returns Result[(events, total_count)]."""
        ...

    async def count_events(self, filters: Metadata | None = None) -> Result[int]:
        """Count events matching filters efficiently. Returns Result[int]."""
        ...

    # ========================================================================
    # RELATIONSHIP METHODS
    # ========================================================================

    async def link_event_to_goal(
        self, event_uid: str, goal_uid: str, contribution_weight: float = 1.0
    ) -> Result[bool]:
        """
        Link event to goal it supports.
        Creates: (Event)-[:SUPPORTS_GOAL {contribution_weight}]->(Goal)
        """
        ...

    async def link_event_to_habit(self, event_uid: str, habit_uid: str) -> Result[bool]:
        """
        Link event to habit it reinforces.
        Creates: (Event)-[:REINFORCES_HABIT]->(Habit)
        """
        ...

    async def link_event_to_knowledge(
        self, event_uid: str, knowledge_uids: list[str]
    ) -> Result[bool]:
        """
        Link event to knowledge units it reinforces.
        Creates: (Event)-[:REINFORCES_KNOWLEDGE]->(Knowledge) for each UID
        """
        ...

    async def get_event_cross_domain_context(
        self, event_uid: str, depth: int = 2
    ) -> Result[GraphContextResult]:
        """
        Get complete cross-domain context for an event with configurable graph traversal depth.

        Returns event with all its relationships:
        - Supporting goals
        - Reinforcing habits
        - Related knowledge units
        - Learning path connections

        Args:
            event_uid: Event UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)

        Returns:
            Result[GraphContextResult]: Type-safe cross-domain context
        """
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
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

    # NOTE: get_related_uids() and count_related() inherited from GraphRelationshipOperations


@runtime_checkable
class HabitsOperations(BackendOperations["Habit"], GraphRelationshipOperations, Protocol):
    """Core habit tracking operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, DETACH DELETE, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Adds habit-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_habit(self, data: Metadata) -> Result[EntityUID]:
        """Create a new habit and return its ID. Returns Result[str]."""
        ...

    async def record_completion(self, habit_id: str, date: datetime) -> Result[bool]:
        """
        Record habit completion for a date.

        Args:
            habit_id: The habit identifier
            date: When the habit was completed (caller provides explicit datetime)

        Returns:
            Result[bool] indicating success
        """
        ...

    async def update_habit(self, habit_id: str, data: dict[str, Any]) -> Result[bool]:
        """Update habit details. Returns Result[bool]."""
        ...

    async def archive_habit(self, habit_id: str) -> Result[bool]:
        """Archive a habit. Returns Result[bool]."""
        ...

    async def get_habit(self, habit_id: str) -> Result[Habit]:
        """Get a habit by ID. Not found is an error."""
        ...

    async def get(self, habit_id: str) -> Result[Habit | None]:
        """Get a habit by ID. Returns None if not found."""
        ...

    async def get_user_habits(self, user_uid: str) -> Result[list[Habit]]:
        """Get all habits for a user. Returns Result[list[Habit]]."""
        ...

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> Result[tuple[builtins.list[Habit], int]]:
        """List habits with optional filters. Returns Result[(habits, total_count)]."""
        ...

    async def list_by_user(self, user_uid: str, limit: int = 100) -> Result[builtins.list[Habit]]:
        """List all habits for a user. Returns Result[list[Habit]]."""
        ...

    async def create_user_habit_relationship(self, user_uid: str, habit_uid: str) -> bool:
        """Create User→Habit relationship in graph."""
        ...

    async def link_habit_to_knowledge(self, habit_uid: str, knowledge_uid: str) -> bool:
        """Link habit to knowledge it practices."""
        ...

    async def link_habit_to_principle(self, habit_uid: str, principle_uid: str) -> bool:
        """Link habit to principle it embodies."""
        ...

    async def get_habit_cross_domain_context(
        self, habit_uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> dict[str, Any]:
        """
        Get complete cross-domain context for habit with configurable graph traversal depth.

        Args:
            habit_uid: Habit UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)
            min_confidence: Minimum confidence threshold for relationships (default=0.7)
        """
        ...

    async def get_skills_developed_by_habits(self, user_uid: str) -> dict[str, Any]:
        """Get skills developed through user's habits."""
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
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


@runtime_checkable
class FinancesOperations(BackendOperations["ExpensePure"], Protocol):
    """Core finance management operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, DETACH DELETE, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Adds finance-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_transaction(self, data: dict[str, Any]) -> Result[str]:
        """Create a financial transaction. Returns Result[str]."""
        ...

    async def update_transaction(self, transaction_id: str, data: dict[str, Any]) -> Result[bool]:
        """Update a transaction. Returns Result[bool]."""
        ...

    async def categorize_transaction(self, transaction_id: str, category: str) -> Result[bool]:
        """Categorize a transaction. Returns Result[bool]."""
        ...

    # ========================================================================
    # EXPENSE-SPECIFIC QUERY METHODS
    # ========================================================================

    async def find_expenses_by_date_range(
        self, start: datetime, end: datetime
    ) -> Result[list[ExpensePure]]:
        """Find expenses within a date range. Returns Result[list[ExpensePure]]."""
        ...

    async def find_expenses_by_category(self, category: str) -> Result[list[ExpensePure]]:
        """Find expenses by category. Returns Result[list[ExpensePure]]."""
        ...

    # ========================================================================
    # BUDGET MANAGEMENT METHODS
    # ========================================================================

    async def create_budget(self, data: dict[str, Any]) -> Result[str]:
        """Create a new budget. Returns Result[str] (budget UID)."""
        ...

    async def get_budget(self, budget_uid: str) -> Result[BudgetPure | None]:
        """Get a budget by UID. Returns Result[BudgetPure | None]."""
        ...

    async def get_active_budgets(self) -> Result[list[BudgetPure]]:
        """Get all active budgets. Returns Result[list[BudgetPure]]."""
        ...

    async def find_budgets_by_category(self, category: str) -> Result[list[BudgetPure]]:
        """Find budgets by category. Returns Result[list[BudgetPure]]."""
        ...

    # ========================================================================
    # RELATIONSHIP METHODS
    # ========================================================================

    async def link_expense_to_goal(
        self, expense_uid: str, goal_uid: str, contribution_type: str = "investment"
    ) -> Result[bool]:
        """
        Link expense to goal it supports.
        Creates: (Expense)-[:SUPPORTS_GOAL {contribution_type}]->(Goal)

        Args:
            expense_uid: UID of the expense
            goal_uid: UID of the goal
            contribution_type: Type of contribution (investment, tool, resource, etc.)
        """
        ...

    async def link_expense_to_knowledge(
        self, expense_uid: str, knowledge_uid: str, learning_investment: bool = True
    ) -> Result[bool]:
        """
        Link expense to knowledge unit it invests in.
        Creates: (Expense)-[:INVESTS_IN_KNOWLEDGE {learning_investment}]->(Knowledge)

        Args:
            expense_uid: UID of the expense
            knowledge_uid: UID of the knowledge unit
            learning_investment: Whether this is a learning investment
        """
        ...

    async def link_expense_to_project(
        self, expense_uid: str, project_uid: str, allocation_percentage: float = 100.0
    ) -> Result[bool]:
        """
        Link expense to project/task it funds.
        Creates: (Expense)-[:FUNDS_PROJECT {allocation_percentage}]->(Task)

        Args:
            expense_uid: UID of the expense
            project_uid: UID of the project/task
            allocation_percentage: Percentage of expense allocated to project (0-100)
        """
        ...

    async def get_expense_cross_domain_context(
        self, expense_uid: str, depth: int = 2
    ) -> Result[GraphContextResult]:
        """
        Get complete cross-domain context for an expense with configurable graph traversal depth.

        Returns expense with all its relationships:
        - Goals (SUPPORTS_GOAL)
        - Knowledge units (INVESTS_IN_KNOWLEDGE)
        - Projects/Tasks (FUNDS_PROJECT)

        Args:
            expense_uid: UID of the expense
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)

        Returns:
            Result[GraphContextResult]: Type-safe cross-domain context
        """
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[ExpensePure]]:
        """
        Get user's expenses in date range - unified interface for meta-services.

        Args:
            user_uid: User identifier
            start_date: Range start date
            end_date: Range end date
            include_completed: Not applicable for expenses (always included)

        Returns:
            Result[list[Expense]] filtered by user and expense_date

        Implementation:
            Filters by user_uid and expense_date field

        Date Added: October 29, 2025 (Unified Query Pattern for Meta-Services)
        """
        ...

    # ========================================================================
    # ADDITIONAL FINANCE OPERATIONS (Added 2026-02-02)
    # ========================================================================

    async def get_expenses_by_date_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        category: Any = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Result[tuple[list[Any], int]]:
        """Get expenses for user in date range."""
        ...

    async def search_expenses(
        self, user_uid: str, query: str, limit: int = 100, offset: int = 0
    ) -> Result[tuple[list[Any], int]]:
        """Search expenses by text query."""
        ...

    async def attach_receipt(self, expense_uid: str, receipt_url: str) -> Result[bool]:
        """Attach receipt to expense."""
        ...

    async def clear_expense(self, expense_uid: str) -> Result[bool]:
        """Mark expense as cleared/reconciled."""
        ...

    async def reconcile_expense(
        self, expense_uid: str, reconciliation_data: dict[str, Any]
    ) -> Result[bool]:
        """Reconcile expense with bank statement."""
        ...

    async def bulk_categorize(
        self,
        expense_uids: list[str],
        category: Any,  # ExpenseCategory enum
        subcategory: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Bulk categorize multiple expenses. Returns dict with updated expenses."""
        ...

    async def recalculate_budget(self, budget_uid: str) -> Result[bool]:
        """Recalculate budget totals and status."""
        ...

    async def create_invoice(self, invoice_data: dict[str, Any]) -> Result[str]:
        """Create invoice. Returns invoice UID."""
        ...

    async def get_invoice(self, invoice_uid: str) -> Result[dict[str, Any] | None]:
        """Get invoice by UID."""
        ...

    async def list_invoices(
        self, limit: int = 50, invoice_type: str | None = None, status: str | None = None
    ) -> Result[list[Any]]:
        """List invoices for user, optionally filtered by status."""
        ...

    async def get_invoice_stats(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get invoice statistics for user."""
        ...

    async def generate_invoice_pdf(self, invoice_uid: str) -> Result[bytes]:
        """Generate PDF for invoice. Returns PDF bytes."""
        ...


# NOTE: FinancesQueryOperations removed - unused, duplicates FinancesOperations methods
# Use FinancesOperations directly for all finance query needs


@runtime_checkable
class GoalsOperations(BackendOperations["Goal"], GraphRelationshipOperations, Protocol):
    """Core goal management operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, DETACH DELETE, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Inherits from GraphRelationshipOperations:
    - get_related_uids(uid, relationship_type, direction, limit, properties)
    - count_related(uid, relationship_type, direction, properties)

    Adds goal-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_goal(self, data: dict[str, Any]) -> Result[str]:
        """Create a new goal and return its ID. Returns Result[str]."""
        ...

    async def update_goal(self, goal_id: str, data: dict[str, Any]) -> Result[bool]:
        """Update an existing goal. Returns Result[bool]."""
        ...

    async def delete_goal(self, goal_id: str) -> Result[bool]:
        """DETACH DELETE a goal. Returns Result[bool]."""
        ...

    async def complete_goal(self, goal_id: str) -> Result[bool]:
        """Mark a goal as completed. Returns Result[bool]."""
        ...

    async def add_milestone(self, goal_id: str, milestone: dict[str, Any]) -> Result[bool]:
        """Add a milestone to a goal. Returns Result[bool]."""
        ...

    async def get_goal(self, goal_id: str) -> Result[Any]:
        """Get a goal by ID. Not found is an error."""
        ...

    async def create_user_goal_relationship(self, user_uid: str, goal_uid: str) -> Result[bool]:
        """Create User→Goal relationship in graph. Returns Result[bool]."""
        ...

    async def link_goal_to_habit(self, goal_uid: str, habit_uid: str) -> Result[bool]:
        """Link goal to supporting habit. Returns Result[bool]."""
        ...

    async def link_goal_to_knowledge(self, goal_uid: str, knowledge_uid: str) -> Result[bool]:
        """Link goal to required knowledge. Returns Result[bool]."""
        ...

    async def link_goal_to_principle(self, goal_uid: str, principle_uid: str) -> Result[bool]:
        """Link goal to guiding principle. Returns Result[bool]."""
        ...

    async def get_goal_cross_domain_context(
        self, goal_uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[GraphContextResult]:
        """
        Get complete cross-domain context for goal with configurable graph traversal depth.

        Args:
            goal_uid: Goal UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)
            min_confidence: Minimum confidence threshold for relationships (default=0.7)

        Returns:
            Result[GraphContextResult]: Type-safe cross-domain context
        """
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
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


@runtime_checkable
class JournalsOperations(BackendOperations["JournalPure"], Protocol):
    """Core journal management operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, DETACH DELETE, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Adds journal-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_journal(self, journal: Any) -> Result[JournalPure]:
        """Create a new journal entry. Returns Result[Journal]."""
        ...

    async def get_journal_by_uid(self, uid: str) -> Result[JournalPure | None]:
        """Get a journal by UID. Returns Result[Journal | None]."""
        ...

    async def update_journal(self, uid: str, updates: Metadata) -> Result[JournalPure | None]:
        """Update an existing journal. Returns Result[Journal | None]."""
        ...

    async def delete_journal(self, uid: str) -> Result[bool]:
        """DETACH DELETE a journal. Returns Result[bool]."""
        ...

    async def find_journals(
        self,
        filters: Metadata | None = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[JournalPure]]:
        """Find journals with filters. Returns Result[list[Journal]]."""
        ...

    async def get_journals_by_date(self, date: datetime) -> Result[list[JournalPure]]:
        """Get all journals for a specific date. Returns Result[list[Journal]]."""
        ...

    async def get_journals_by_category(self, category: str) -> Result[list[JournalPure]]:
        """Get all journals for a specific category. Returns Result[list[Journal]]."""
        ...

    async def get_journal_count(self, filters: Metadata | None = None) -> Result[int]:
        """Get count of journals matching filters. Returns Result[int]."""
        ...

    async def get_recent_journals(self, limit: int = 10) -> Result[list[JournalPure]]:
        """Get most recent journal entries. Returns Result[list[Journal]]."""
        ...


@runtime_checkable
class ChoicesOperations(BackendOperations["Choice"], GraphRelationshipOperations, Protocol):
    """Core choice management operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, DETACH DELETE, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Inherits from GraphRelationshipOperations:
    - get_related_uids(uid, relationship_type, direction, limit, properties)
    - count_related(uid, relationship_type, direction, properties)

    Adds choice-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create_choice(self, data: dict[str, Any]) -> Result[str]:
        """Create a new choice and return its ID. Returns Result[str]."""
        ...

    async def update_choice(self, choice_id: str, data: dict[str, Any]) -> Result[bool]:
        """Update an existing choice. Returns Result[bool]."""
        ...

    async def delete_choice(self, choice_id: str) -> Result[bool]:
        """DETACH DELETE a choice. Returns Result[bool]."""
        ...

    async def resolve_choice(self, choice_id: str, resolution: dict[str, Any]) -> Result[bool]:
        """Mark a choice as resolved with outcome data. Returns Result[bool]."""
        ...

    async def get(self, choice_id: str) -> Result[Choice | None]:
        """Get a choice by ID. Returns None if not found."""
        ...

    async def get_choice(self, choice_id: str) -> Result[Choice]:
        """Get a choice by ID. Alias for get(). Not found is an error."""
        ...

    async def find_by(self, limit: int = 100, **filters: Any) -> Result[list[Choice]]:
        """Find choices matching filters. Returns Result[list[Choice]]."""
        ...

    async def find_choices(
        self, filters: dict[str, Any] | None = None, limit: int = 100
    ) -> Result[list[Choice]]:
        """Find choices with filters and limit. Returns Result[list[Choice]]."""
        ...

    async def get_user_choices(self, user_id: str) -> Result[list[Choice]]:
        """Get all choices for a user. Returns Result[list[Choice]]."""
        ...

    async def count_choices(self, filters: dict[str, Any] | None = None) -> Result[int]:
        """Count choices matching filters. Returns Result[int]."""
        ...

    async def link_choice_to_goal(self, choice_uid: str, goal_uid: str) -> bool:
        """Link choice to related goal."""
        ...

    async def link_choice_to_habit(self, choice_uid: str, habit_uid: str) -> bool:
        """Link choice to habit it affects."""
        ...

    async def link_choice_to_principle(self, choice_uid: str, principle_uid: str) -> bool:
        """Link choice to guiding principle."""
        ...

    async def get_choice_cross_domain_context(
        self, choice_uid: str, depth: int = 2
    ) -> dict[str, Any]:
        """
        Get complete cross-domain context for choice with configurable graph traversal depth.

        Args:
            choice_uid: Choice UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)
        """
        ...

    async def analyze_decision_patterns(
        self, user_uid: str, timeframe_days: int = 90
    ) -> dict[str, Any]:
        """Analyze user's decision-making patterns."""
        ...

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> Result[builtins.list[dict[str, Any]]]:
        """Execute a low-level database query. Should not be in protocol - architectural issue."""
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
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


@runtime_checkable
class PrinciplesOperations(BackendOperations["Principle"], GraphRelationshipOperations, Protocol):
    """Core principle management operations.

    Inherits base CRUD operations from BackendOperations:
    - create, get, update, DETACH DELETE, list
    - find_by, count, search
    - add_relationship, get_relationships, traverse
    - health_check

    Adds principle-specific operations below.

    Returns Result[T] for all operations to match UniversalNeo4jBackend implementation.
    """

    async def create(self, principle: Any) -> Result[Principle]:
        """Create a new principle. Returns Result[Principle]."""
        ...

    async def get(self, principle_uid: str) -> Result[Principle | None]:
        """Get a principle by UID. Returns Result[Principle | None]."""
        ...

    async def find_by(self, limit: int = 100, **filters: Any) -> Result[builtins.list[Principle]]:
        """Find principles matching filters. Returns Result[list[Principle]]."""
        ...

    async def update(self, principle_uid: str, updates: dict[str, Any]) -> Result[Principle]:
        """Update a principle. Returns Result[Principle]."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """DETACH DELETE a principle. Returns Result[bool]."""
        ...

    # ========================================================================
    # RELATIONSHIP METHODS
    # ========================================================================

    async def create_user_principle_relationship(
        self,
        user_uid: str,
        principle_uid: str,
        strength: str = "core",
        adoption_date: str | None = None,
    ) -> Result[bool]:
        """
        Create User→Principle relationship in graph.
        Creates: (User)-[:HOLDS_PRINCIPLE {strength, adoption_date}]->(Principle)
        """
        ...

    async def link_principle_to_knowledge(
        self, principle_uid: str, knowledge_uid: str, relevance: str = "fundamental"
    ) -> Result[bool]:
        """
        Link principle to knowledge it's based on.
        Creates: (Principle)-[:BASED_ON_KNOWLEDGE {relevance}]->(Knowledge)
        """
        ...

    async def get_principle_cross_domain_context(
        self, principle_uid: str, depth: int = 2
    ) -> Result[GraphContextResult]:
        """
        Get complete cross-domain context for a principle with configurable graph traversal depth.

        Args:
            principle_uid: Principle UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)

        Returns:
            Result[GraphContextResult] with comprehensive context including:
            - Users who hold this principle
            - Goals guided by principle
            - Habits embodying principle
            - Knowledge foundations
            - Alignment metrics
        """
        ...

    async def get_user_principle_portfolio(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get user's complete principle portfolio with integrity analysis.

        Returns:
        - All principles user holds
        - Strength distribution (core/strong/developing/aspirational)
        - Goals/habits aligned with principles
        - Integrity score (actions match values)
        - Conflicts and opportunities
        """
        ...

    async def calculate_principle_integrity(
        self, user_uid: str, principle_uid: str
    ) -> Result[dict[str, Any]]:
        """
        Calculate how well user's actions align with stated principle.

        Uses:
        - Goals guided by principle (alignment)
        - Habits embodying principle (practice)
        - Consistency over time

        Returns integrity score 0.0-1.0 with breakdown
        """
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Principle]]:
        """
        Get user's principles in date range - unified interface for meta-services.

        Args:
            user_uid: User identifier
            start_date: Range start date (not applicable for principles)
            end_date: Range end date (not applicable for principles)
            include_completed: Not applicable for principles (always included)

        Returns:
            Result[list[Principle]] filtered by user

        Implementation:
            Filters by user_uid only (principles are timeless)
            Included for consistency with unified query pattern

        Date Added: October 29, 2025 (Unified Query Pattern for Meta-Services)
        """
        ...

    # NOTE: get_related_uids() and count_related() inherited from GraphRelationshipOperations


# ============================================================================
# RELATIONSHIP SERVICE PROTOCOLS
# ============================================================================
# Added: November 11, 2025
# Purpose: Protocol interfaces for domain relationship services
# Architecture: "Protocol-Based Architecture" - all services use protocols


@runtime_checkable
class BaseRelationshipOperations(Protocol):
    """
    Base protocol for domain relationship services.

    All relationship services must implement cross-domain context retrieval.
    Domain-specific protocols extend this with additional methods.
    """

    async def get_cross_domain_context(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[dict[str, Any]]:
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
        self, relationship_key: str, entity_uid: str
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
class TasksRelationshipOperations(BaseRelationshipOperations, Protocol):
    """Tasks relationship operations protocol."""

    async def get_task_cross_domain_context(
        self, task_uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Get cross-domain context for a task with configurable graph traversal depth.

        Args:
            task_uid: Task UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)
        """
        ...

    async def get_task_knowledge(self, task_uid: str) -> Result[builtins.list[str]]:
        """Get knowledge UIDs applied by this task."""
        ...

    async def get_task_dependencies(self, task_uid: str) -> Result[dict[str, Any]]:
        """Get task dependency information."""
        ...

    async def link_task_to_knowledge(
        self,
        task_uid: str,
        knowledge_uid: str,
        relationship_type: RelationshipName = RelationshipName.APPLIES_KNOWLEDGE,
    ) -> Result[bool]:
        """Link task to knowledge unit."""
        ...


@runtime_checkable
class HabitsRelationshipOperations(BaseRelationshipOperations, Protocol):
    """Habits relationship operations protocol."""

    async def get_habit_cross_domain_context(
        self, habit_uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get cross-domain context for a habit with configurable graph traversal depth.

        Args:
            habit_uid: Habit UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)
            min_confidence: Minimum confidence threshold for relationships (default=0.7)
        """
        ...

    async def get_habit_knowledge(self, habit_uid: str) -> Result[builtins.list[str]]:
        """Get knowledge UIDs reinforced by this habit."""
        ...

    async def get_habit_goals(self, habit_uid: str) -> Result[builtins.list[str]]:
        """Get goal UIDs supported by this habit."""
        ...

    async def get_habit_principles(self, habit_uid: str) -> Result[builtins.list[str]]:
        """Get principle UIDs aligned with this habit."""
        ...

    async def link_habit_to_knowledge(
        self, habit_uid: str, knowledge_uid: str, confidence: float = 0.9
    ) -> Result[bool]:
        """Link habit to knowledge unit."""
        ...


@runtime_checkable
class EventsRelationshipOperations(BaseRelationshipOperations, Protocol):
    """Events relationship operations protocol."""

    async def get_event_cross_domain_context(
        self, event_uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Get cross-domain context for an event with configurable graph traversal depth.

        Args:
            event_uid: Event UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)
        """
        ...

    async def get_event_knowledge(self, event_uid: str) -> Result[builtins.list[str]]:
        """Get knowledge UIDs practiced in this event."""
        ...

    async def get_event_goals(self, event_uid: str) -> Result[builtins.list[str]]:
        """Get goal UIDs supported by this event."""
        ...

    async def link_event_to_goal(self, event_uid: str, goal_uid: str) -> Result[bool]:
        """Link event to goal."""
        ...

    async def link_event_to_knowledge(
        self, event_uid: str, knowledge_uid: str, confidence: float = 0.9
    ) -> Result[bool]:
        """Link event to knowledge unit."""
        ...


@runtime_checkable
class GoalsRelationshipOperations(BaseRelationshipOperations, Protocol):
    """Goals relationship operations protocol."""

    async def get_goal_cross_domain_context(
        self, goal_uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get cross-domain context for a goal with configurable graph traversal depth.

        Args:
            goal_uid: Goal UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)
            min_confidence: Minimum confidence threshold for relationships (default=0.7)
        """
        ...

    async def get_goal_tasks(self, goal_uid: str) -> Result[builtins.list[str]]:
        """Get task UIDs fulfilling this goal."""
        ...

    async def get_goal_habits(self, goal_uid: str) -> Result[builtins.list[str]]:
        """Get habit UIDs supporting this goal."""
        ...

    async def get_goal_knowledge(self, goal_uid: str) -> Result[builtins.list[str]]:
        """Get knowledge UIDs required for this goal."""
        ...

    async def link_task_to_goal(self, task_uid: str, goal_uid: str) -> Result[bool]:
        """Link task to goal."""
        ...


@runtime_checkable
class PrinciplesRelationshipOperations(BaseRelationshipOperations, Protocol):
    """Principles relationship operations protocol."""

    async def get_principle_cross_domain_context(
        self, principle_uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Get cross-domain context for a principle with configurable graph traversal depth.

        Args:
            principle_uid: Principle UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)
        """
        ...

    async def get_principle_goals(self, principle_uid: str) -> Result[builtins.list[str]]:
        """Get goal UIDs guided by this principle."""
        ...

    async def get_principle_choices(self, principle_uid: str) -> Result[builtins.list[str]]:
        """Get choice UIDs informed by this principle."""
        ...

    async def get_principle_knowledge(self, principle_uid: str) -> Result[builtins.list[str]]:
        """Get knowledge UIDs grounding this principle."""
        ...


@runtime_checkable
class ChoicesRelationshipOperations(BaseRelationshipOperations, Protocol):
    """Choices relationship operations protocol."""

    async def get_choice_cross_domain_context(
        self, choice_uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get cross-domain context for a choice with configurable graph traversal depth.

        Args:
            choice_uid: Choice UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop, default=2)
            min_confidence: Minimum confidence threshold for relationships (default=0.7)
        """
        ...

    async def get_choice_principles(self, choice_uid: str) -> Result[builtins.list[str]]:
        """Get principle UIDs informing this choice."""
        ...

    async def get_choice_goals(self, choice_uid: str) -> Result[builtins.list[str]]:
        """Get goal UIDs influenced by this choice."""
        ...

    async def link_choice_to_principle(self, choice_uid: str, principle_uid: str) -> Result[bool]:
        """Link choice to principle."""
        ...


@runtime_checkable
class UserContextOperations(Protocol):
    """User context operations for cache invalidation and context-aware operations."""

    async def invalidate_context(self, user_uid: str) -> None:
        """
        Invalidate cached user context after state-changing operations.

        Args:
            user_uid: User whose context cache should be invalidated
        """
        ...

    async def get_context_dashboard(
        self,
        user_uid: str,
        include_predictions: bool = True,
        time_window: str = "7d",
    ) -> Result[Any]:  # Result[ContextDashboard]
        """Get unified context dashboard for user."""
        ...

    async def get_context_summary(
        self,
        user_uid: str,
        include_insights: bool = True,
    ) -> Result[Any]:  # Result[ContextSummary]
        """Get concise context summary for user."""
        ...

    async def get_next_action(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get AI-recommended next action based on context."""
        ...

    async def get_at_risk_habits(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get habits at risk of breaking streaks."""
        ...

    async def get_adaptive_learning_path(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get adaptive learning path recommendations."""
        ...

    async def get_context_health(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get overall context health metrics."""
        ...

    async def complete_task_with_context(
        self,
        task_uid: str,
        completion_context: dict[str, Any] | None = None,
        reflection_notes: str = "",
    ) -> Result[Any]:  # Result[Task]
        """Complete task with context awareness."""
        ...

    async def create_tasks_from_goal_context(
        self,
        goal_uid: str,
        context_preferences: dict[str, Any] | None = None,
        auto_create: bool = True,
    ) -> Result[list[Any]]:  # Result[list[Task]]
        """Create contextually relevant tasks from goal."""
        ...

    async def complete_habit_with_context(
        self,
        habit_uid: str,
        completion_quality: str = "good",
        environmental_factors: dict[str, Any] | None = None,
    ) -> Result[Any]:  # Result[Habit]
        """Complete habit with context awareness."""
        ...
