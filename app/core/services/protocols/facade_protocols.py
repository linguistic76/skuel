"""
Facade Protocols - Type declarations for dynamically delegated methods.
======================================================================

These protocols provide type declarations for methods that FacadeDelegationMixin
generates dynamically at class definition time. Since MyPy can't see dynamically
created methods, these protocols enable type-safe usage at CALL SITES.

**IMPORTANT: Do NOT inherit from these protocols in the facade classes.**
The protocols are for structural subtyping (duck typing) - use them as TYPE HINTS
for parameters that accept facade instances, not as base classes.

Usage Pattern - Type hints at call sites:
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from core.services.protocols.facade_protocols import GoalsFacadeProtocol

    async def analyze_goals(goals_service: GoalsFacadeProtocol) -> dict:
        # MyPy sees the protocol's method declarations
        milestones = await goals_service.get_goal_milestones(uid)
        progress = await goals_service.update_goal_progress(uid, 0.5)
        return {"milestones": milestones, "progress": progress}

Why Protocols work for dynamic methods:
    - Structural subtyping: GoalsService satisfies GoalsFacadeProtocol structurally
    - No inheritance required: Protocol matching is duck-typed at runtime
    - MyPy sees declarations: Even though methods are created dynamically

Why NOT to inherit from protocols:
    - MyPy expects explicit implementations when Protocol is a base class
    - Dynamic methods from FacadeDelegationMixin aren't visible to static analysis
    - Results in "Cannot instantiate abstract class" errors

See Also:
    - /core/services/mixins/facade_delegation_mixin.py - Runtime delegation
    - /docs/decisions/ADR-025-service-consolidation-patterns.md - Pattern context
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.services.protocols.query_types import (
    IntelligenceResult,
    ProgressResult,
)

if TYPE_CHECKING:
    from datetime import date

    from core.models.enums import Domain
    from core.models.ku.ku_request import KuChoiceCreateRequest, KuUpdateRequest
    from core.models.ku.ku import Ku
    from core.models.goal.goal_request import GoalCreateRequest
    from core.models.ku.ku import Ku as Habit
    from core.models.habit.habit_request import HabitCreateRequest
    from core.models.ku import Ku
    from core.models.enums.ku_enums import PrincipleCategory
    from core.models.ku.ku import Ku as Task
    from core.models.ku.ku_request import KuTaskCreateRequest as TaskCreateRequest
    from core.services.user import UserContext
    from core.utils.result_simplified import Result


# ============================================================================
# CORE SUB-SERVICE PROTOCOLS
# ============================================================================
# These protocols provide type-safe access to core sub-service methods.
# They enable proper typing when accessing facade.core.method()
# ============================================================================


@runtime_checkable
class TasksCoreOperations(Protocol):
    """Protocol for TasksCoreService methods accessed via TasksService.core"""

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[Task]:
        """Verify user owns the task, return task if owned."""
        ...

    async def create_task(self, task_request: TaskCreateRequest, user_uid: str) -> Result[Task]:
        """Create a new task."""
        ...

    async def get_task(self, task_uid: str) -> Result[Task]:
        """Get a task by UID."""
        ...

    async def get_user_tasks(self, user_uid: str) -> Result[list[Task]]:
        """Get all tasks for a user."""
        ...

    async def update_task(self, task_uid: str, updates: dict[str, Any]) -> Result[Task]:
        """Update a task."""
        ...

    async def delete_task(self, task_uid: str) -> Result[bool]:
        """Delete a task."""
        ...


@runtime_checkable
class GoalsCoreOperations(Protocol):
    """Protocol for GoalsCoreService methods accessed via GoalsService.core"""

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[Ku]:
        """Verify user owns the goal, return goal if owned."""
        ...

    async def create_goal(self, goal_request: GoalCreateRequest, user_uid: str) -> Result[Ku]:
        """Create a new goal."""
        ...

    async def get_goal(self, goal_uid: str) -> Result[Ku]:
        """Get a goal by UID."""
        ...

    async def get_user_goals(self, user_uid: str) -> Result[list[Ku]]:
        """Get all goals for a user."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Ku]:
        """Update a goal."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete a goal."""
        ...


@runtime_checkable
class HabitsCoreOperations(Protocol):
    """Protocol for HabitsCoreService methods accessed via HabitsService.core"""

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[Habit]:
        """Verify user owns the habit, return habit if owned."""
        ...

    async def create(self, entity: Habit) -> Result[Habit]:
        """Create a new habit."""
        ...

    async def create_habit(self, habit_request: HabitCreateRequest, user_uid: str) -> Result[Habit]:
        """Create a habit from a request with user_uid."""
        ...

    async def get_habit(self, uid: str) -> Result[Habit]:
        """Get a habit by UID."""
        ...

    async def get_user_habits(self, user_uid: str) -> Result[list[Habit]]:
        """Get all habits for a user."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Habit]:
        """Update a habit."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete a habit."""
        ...


@runtime_checkable
class EventsCoreOperations(Protocol):
    """Protocol for EventsCoreService methods accessed via EventsService.core.
    Uses unified Ku model with KuType.EVENT."""

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[Ku]:
        """Verify user owns the event, return event if owned."""
        ...

    async def create(self, entity: Ku) -> Result[Ku]:
        """Create a new event."""
        ...

    async def get_event(self, event_uid: str) -> Result[Ku]:
        """Get an event by UID."""
        ...

    async def get_user_events(self, user_uid: str) -> Result[list[Ku]]:
        """Get all events for a user."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Ku]:
        """Update an event."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete an event."""
        ...


@runtime_checkable
class PrinciplesCoreOperations(Protocol):
    """Protocol for PrinciplesCoreService methods accessed via PrinciplesService.core.
    Uses unified Ku model with KuType.PRINCIPLE."""

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[Ku]:
        """Verify user owns the principle, return principle if owned."""
        ...

    async def create_principle(
        self,
        label: str,
        description: str,
        category: "PrincipleCategory",
        why_matters: str,
        user_uid: str,
        **kwargs: Any,
    ) -> Result[Ku]:
        """Create a new principle."""
        ...

    async def get_principle(self, principle_uid: str) -> Result[Ku]:
        """Get a principle by UID."""
        ...

    async def get_user_principles(self, user_uid: str) -> Result[list[Ku]]:
        """Get all principles for a user."""
        ...

    async def update_principle(self, principle_uid: str, updates: dict[str, Any]) -> Result[Ku]:
        """Update a principle."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete a principle."""
        ...


@runtime_checkable
class ChoicesCoreOperations(Protocol):
    """Protocol for ChoicesCoreService methods accessed via ChoicesService.core"""

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[Ku]:
        """Verify user owns the choice, return choice if owned."""
        ...

    async def create_choice(
        self, choice_request: KuChoiceCreateRequest, user_uid: str
    ) -> Result[Ku]:
        """Create a new choice."""
        ...

    async def get_choice(self, choice_uid: str) -> Result[Ku]:
        """Get a choice by UID."""
        ...

    async def get_user_choices(self, user_uid: str) -> Result[list[Ku]]:
        """Get all choices for a user."""
        ...

    async def update_choice(self, choice_uid: str, choice_update: KuUpdateRequest) -> Result[Ku]:
        """Update a choice."""
        ...

    async def make_decision(
        self,
        choice_uid: str,
        selected_option_uid: str,
        decision_rationale: str | None = None,
        confidence: float = 0.5,
    ) -> Result[Ku]:
        """Make a decision on a choice."""
        ...

    async def evaluate_choice_outcome(self, choice_uid: str, evaluation: Any) -> Result[Ku]:
        """Record the outcome evaluation for a choice."""
        ...

    async def delete_choice(self, choice_uid: str) -> Result[bool]:
        """Delete a choice."""
        ...


# ============================================================================
# BACKEND OPERATIONS PROTOCOL
# ============================================================================


@runtime_checkable
class BackendCrudOperations(Protocol):
    """Protocol for backend CRUD operations accessed via service.backend"""

    async def create(self, entity: Any) -> Result[Any]:
        """Create an entity."""
        ...

    async def get(self, uid: str) -> Result[Any]:
        """Get an entity by UID."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Any]:
        """Update an entity."""
        ...

    async def delete(self, uid: str) -> Result[bool]:
        """Delete an entity."""
        ...


# ============================================================================
# FACADE PROTOCOLS
# ============================================================================


@runtime_checkable
class GoalsFacadeProtocol(Protocol):
    """
    Type declarations for GoalsService delegated methods.

    These methods are auto-generated by FacadeDelegationMixin from _delegations.
    This protocol makes them visible to MyPy for static type checking.
    """

    # ========================================================================
    # Sub-service access (for direct sub-service method calls)
    # ========================================================================

    @property
    def core(self) -> GoalsCoreOperations:
        """Access to core sub-service for methods like verify_ownership."""
        ...

    @property
    def intelligence(self) -> Any:
        """Access to intelligence sub-service."""
        ...

    # ========================================================================
    # Explicit facade methods (not delegated)
    # ========================================================================

    async def create_goal(self, request: Any, user_uid: str) -> Result[Ku]:
        """Create a new goal."""
        ...

    async def get(self, uid: str) -> Result[Ku | None]:
        """Get a goal by UID (direct access)."""
        ...

    async def get_for_user(self, uid: str, user_uid: str) -> Result[Ku | None]:
        """Get a goal with ownership verification."""
        ...

    # ========================================================================
    # Progress delegations (→ GoalsProgressService)
    # ========================================================================

    async def update_goal_progress(
        self, uid: str, progress_value: float, notes: str = "", update_date: str | None = None
    ) -> Result[ProgressResult]:
        """Update goal progress manually."""
        ...

    async def get_goal_milestones(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Get all milestones for a goal."""
        ...

    async def get_goal_progress(self, uid: str, period: str = "month") -> Result[ProgressResult]:
        """Get goal progress history for a period."""
        ...

    async def complete_milestone(
        self, uid: str, milestone_id: str, completion_date: str | None = None
    ) -> Result[ProgressResult]:
        """Mark a milestone as complete."""
        ...

    async def create_goal_milestone(
        self,
        uid: str,
        title: str,
        description: str | None = None,
        due_date: str | None = None,
        progress_contribution: float = 0.0,
    ) -> Result[dict[str, Any]]:
        """Create a new milestone for a goal."""
        ...

    async def calculate_goal_progress_with_context(
        self, uid: str, user_context: UserContext | None = None
    ) -> Result[ProgressResult]:
        """Calculate goal progress with full context awareness."""
        ...

    # ========================================================================
    # Search delegations (→ GoalsSearchService)
    # ========================================================================

    async def search_goals(self, query: str, limit: int = 50) -> Result[list[Ku]]:
        """Text search on goal title/description."""
        ...

    async def get_goals_by_status(self, status: str, limit: int = 100) -> Result[list[Ku]]:
        """Filter goals by status."""
        ...

    async def get_goals_by_category(
        self, category: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[Ku]]:
        """Filter goals by category."""
        ...

    async def get_goals_due_soon(self, days_ahead: int = 7) -> Result[list[Ku]]:
        """Get goals with target dates within specified days."""
        ...

    async def get_overdue_goals(self, limit: int = 100) -> Result[list[Ku]]:
        """Get goals past their target date."""
        ...

    async def get_goals_by_domain(self, domain: Domain, limit: int = 100) -> Result[list[Ku]]:
        """Filter goals by domain."""
        ...

    async def get_prioritized_goals(
        self, user_context: UserContext | None, limit: int = 10
    ) -> Result[list[Ku]]:
        """Get goals prioritized for user's context."""
        ...

    async def list_goal_categories(self, user_uid: str | None = None) -> Result[list[str]]:
        """List unique goal categories."""
        ...

    async def list_all_goal_categories(self) -> Result[list[str]]:
        """List all goal categories system-wide."""
        ...

    # ========================================================================
    # Core delegations (→ GoalsCoreService)
    # ========================================================================

    async def get_goal(self, uid: str) -> Result[Ku | None]:
        """Get a goal by UID."""
        ...

    async def get_user_goals(self, user_uid: str, limit: int = 100) -> Result[list[Ku]]:
        """Get goals for a specific user."""
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Ku]]:
        """Get user goals within date range."""
        ...

    async def activate_goal(self, uid: str) -> Result[Ku]:
        """Activate a goal."""
        ...

    async def pause_goal(self, uid: str) -> Result[Ku]:
        """Pause a goal."""
        ...

    async def complete_goal(self, uid: str) -> Result[Ku]:
        """Mark goal as completed."""
        ...

    async def archive_goal(self, uid: str) -> Result[Ku]:
        """Archive a goal."""
        ...

    # ========================================================================
    # Intelligence delegations (→ GoalsIntelligenceService)
    # ========================================================================

    async def get_goal_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Ku, Any]]:
        """Get goal with full graph context."""
        ...

    async def get_goal_progress_dashboard(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[IntelligenceResult]:
        """Get comprehensive goal progress dashboard."""
        ...

    async def get_goal_completion_forecast(self, uid: str) -> Result[IntelligenceResult]:
        """Forecast goal completion date based on velocity."""
        ...

    async def get_goal_learning_requirements(self, uid: str) -> Result[IntelligenceResult]:
        """Get knowledge requirements for goal achievement."""
        ...

    # ========================================================================
    # Additional Goal operations (Added 2026-02-02)
    # ========================================================================

    async def link_goal_to_habit(
        self,
        goal_uid: str,
        habit_uid: str,
        weight: float = 1.0,
        contribution_type: str = "consistency",
    ) -> Result[bool]:
        """Link a goal to a supporting habit."""
        ...

    async def unlink_goal_from_habit(self, goal_uid: str, habit_uid: str) -> Result[bool]:
        """Unlink a habit from a goal."""
        ...

    async def get_goal_habits(self, goal_uid: str) -> Result[list[Any]]:
        """Get all habits supporting a goal."""
        ...


@runtime_checkable
class PrinciplesFacadeProtocol(Protocol):
    """
    Type declarations for PrinciplesService delegated methods.

    These methods are auto-generated by FacadeDelegationMixin from _delegations.
    This protocol makes them visible to MyPy for static type checking.
    """

    # ========================================================================
    # Sub-service access (for direct sub-service method calls)
    # ========================================================================

    @property
    def core(self) -> PrinciplesCoreOperations:
        """Access to core sub-service for methods like verify_ownership, create_principle, update_principle."""
        ...

    @property
    def intelligence(self) -> Any:
        """Access to intelligence sub-service."""
        ...

    @property
    def reflection(self) -> Any:
        """Access to reflection sub-service for reflection-related operations."""
        ...

    @property
    def alignment(self) -> Any:
        """Access to alignment sub-service for alignment assessment operations."""
        ...

    # ========================================================================
    # Intelligence delegations (→ PrinciplesIntelligenceService)
    # ========================================================================

    async def assess_principle_alignment(
        self, principle_uid: str, min_confidence: float = 0.7
    ) -> Result[IntelligenceResult]:
        """Assess how well user is living by a principle."""
        ...

    async def get_principle_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Ku, Any]]:
        """Get principle with full graph context."""
        ...

    async def get_principle_adherence_trends(
        self, principle_uid: str, days: int = 90
    ) -> Result[IntelligenceResult]:
        """Analyze principle adherence trends over time."""
        ...

    async def get_principle_conflict_analysis(self, user_uid: str) -> Result[IntelligenceResult]:
        """Analyze conflicts between user's principles."""
        ...

    # ========================================================================
    # Search delegations (→ PrinciplesSearchService)
    # ========================================================================

    async def get_related_principles(
        self, principle_uid: str, depth: int = 2, limit: int = 10
    ) -> Result[list[Ku]]:
        """Get principles related via RELATED_TO or category."""
        ...

    async def get_principles_by_status(self, status: str, limit: int = 100) -> Result[list[Ku]]:
        """Filter principles by active/inactive status."""
        ...

    async def get_principles_by_strength(self, strength: Any, limit: int = 100) -> Result[list[Ku]]:
        """Filter principles by strength level."""
        ...

    async def get_principles_by_category(
        self, category: Any, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[Ku]]:
        """Filter principles by category."""
        ...

    async def get_principles_needing_review(
        self, days_threshold: int = 90, limit: int = 20
    ) -> Result[list[Ku]]:
        """Get principles past review threshold."""
        ...

    async def get_principles_for_goal(self, goal_uid: str, limit: int = 10) -> Result[list[Ku]]:
        """Get principles guiding a specific goal."""
        ...

    async def get_principles_for_choice(self, choice_uid: str, limit: int = 10) -> Result[list[Ku]]:
        """Get principles relevant to a choice/decision."""
        ...

    async def get_principle_categories(self, user_uid: str | None = None) -> Result[list[str]]:
        """List user's principle categories."""
        ...

    async def list_all_principle_categories(self) -> Result[list[str]]:
        """List all principle categories."""
        ...

    async def search_principles(
        self, query: str, filters: dict[str, Any] | None = None, limit: int = 50
    ) -> Result[list[Ku]]:
        """Search principles by text query."""
        ...

    async def get_principle_sources(self) -> Result[list[str]]:
        """List all principle sources (where principles come from)."""
        ...

    async def get_principle_links(
        self, principle_uid: str, link_type: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        """Get links for a principle (relationships to other principles)."""
        ...

    # ========================================================================
    # Core delegations (→ PrinciplesCoreService)
    # ========================================================================

    async def get_principle(self, uid: str) -> Result[Ku | None]:
        """Get a principle by UID."""
        ...

    async def get_for_user(self, uid: str, user_uid: str) -> Result[Any]:
        """Get a principle by UID with ownership verification."""
        ...

    async def get_user_principles(self, user_uid: str, limit: int = 100) -> Result[list[Ku]]:
        """Get principles for a specific user."""
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Ku]]:
        """Get user principles within date range."""
        ...

    # ========================================================================
    # Alignment delegations (→ PrinciplesAlignmentService)
    # ========================================================================

    async def assess_goal_alignment(
        self, principle_uid: str, goal_uid: str
    ) -> Result[IntelligenceResult]:
        """Assess alignment between principle and goal."""
        ...

    async def assess_habit_alignment(
        self, principle_uid: str, habit_uid: str
    ) -> Result[IntelligenceResult]:
        """Assess alignment between principle and habit."""
        ...

    async def get_motivational_profile(self, user_uid: str) -> Result[IntelligenceResult]:
        """Get user's motivational profile based on principles."""
        ...

    async def make_principle_based_decision(
        self, choice_uid: str, user_uid: str
    ) -> Result[IntelligenceResult]:
        """Recommend decision based on user's principles."""
        ...

    # ========================================================================
    # Expression & Linking methods (→ PrinciplesService explicit methods)
    # ========================================================================

    async def create_principle_expression(self, dto: Any) -> Result[dict[str, Any]]:
        """Create a principle expression (how principle was lived out)."""
        ...

    async def get_principle_expressions(self, principle_uid: str) -> Result[list[dict[str, Any]]]:
        """Get expressions of a principle (instances where it was lived out)."""
        ...

    async def get_principle_alignment_history(
        self, principle_uid: str, limit: int = 50, days: int = 90
    ) -> Result[list[dict[str, Any]]]:
        """Get principle alignment history."""
        ...

    async def create_principle_link(self, dto: Any) -> Result[dict[str, Any]]:
        """Create a link between principles (e.g., supports, conflicts with)."""
        ...


@runtime_checkable
class LpFacadeProtocol(Protocol):
    """
    Type declarations for LpService delegated methods.

    These methods are auto-generated by FacadeDelegationMixin from _delegations.
    This protocol makes them visible to MyPy for static type checking.
    """

    # ========================================================================
    # Sub-service access (for direct sub-service method calls)
    # ========================================================================

    @property
    def intelligence(self) -> Any:
        """Access to intelligence sub-service."""
        ...

    # ========================================================================
    # Core delegations (→ LpCoreService)
    # ========================================================================

    async def create_path(
        self,
        user_uid: str,
        title: str,
        description: str,
        steps: list[Ku],
        domain: Domain = ...,
    ) -> Result[Ku]:
        """Create and persist a learning path."""
        ...

    async def create_path_from_knowledge_units(
        self,
        user_uid: str,
        knowledge_units: list[Any],
        title: str | None = None,
        description: str | None = None,
    ) -> Result[Ku]:
        """Create path from knowledge units."""
        ...

    async def get_learning_path(self, path_uid: str) -> Result[Ku | None]:
        """Get a single learning path by UID."""
        ...

    async def get_learning_paths_batch(self, uids: list[str]) -> Result[list[Ku | None]]:
        """Get multiple learning paths in one batched query."""
        ...

    async def list_user_paths(self, user_uid: str, limit: int | None = None) -> Result[list[Ku]]:
        """List all learning paths for a specific user."""
        ...

    async def list_all_paths(
        self,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[Ku]]:
        """List all learning paths with pagination."""
        ...

    async def get_path_steps(self, path_uid: str) -> Result[list[Ku]]:
        """Get all steps for a learning path."""
        ...

    async def get_current_step(self, path_uid: str) -> Result[Ku | None]:
        """Get the current (first incomplete) step."""
        ...

    async def update_path(self, path_uid: str, updates: dict[str, Any]) -> Result[Ku]:
        """Update learning path properties."""
        ...

    async def delete_path(self, path_uid: str) -> Result[bool]:
        """Delete a learning path."""
        ...

    # ========================================================================
    # Intelligence delegations (→ LpIntelligenceService)
    # ========================================================================

    async def validate_path_prerequisites(self, path_uid: str) -> Result[dict[str, Any]]:
        """Validate prerequisite ordering and detect issues."""
        ...

    async def identify_path_blockers(
        self, path_uid: str, user_uid: str | None = None
    ) -> Result[dict[str, Any]]:
        """Find steps blocked by unmet prerequisites."""
        ...

    async def get_optimal_path_recommendation(
        self, user_uid: str, goal: str | None = None
    ) -> Result[dict[str, Any]]:
        """Recommend best path for user by readiness score."""
        ...

    async def get_path_with_context(self, path_uid: str, depth: int = 2) -> Result[tuple[Ku, Any]]:
        """Get path with full graph context."""
        ...

    async def analyze_path_knowledge_scope(self, path_uid: str) -> Result[dict[str, Any]]:
        """Analyze KU coverage, complexity, practice in path."""
        ...

    async def identify_practice_gaps(self, path_uid: str) -> Result[dict[str, Any]]:
        """Find steps lacking complete practice opportunities."""
        ...

    async def find_learning_sequence(
        self, user_uid: str, target_knowledge_uids: list[str]
    ) -> Result[list[Ku]]:
        """Generate optimal learning sequence for knowledge targets."""
        ...

    async def get_next_adaptive_step(self, path_uid: str, user_uid: str) -> Result[dict[str, Any]]:
        """Get next recommended step with adaptation."""
        ...

    async def get_recommended_learning_steps(
        self, user_uid: str, limit: int = 5
    ) -> Result[list[dict[str, Any]]]:
        """Get full set of learning step recommendations."""
        ...


@runtime_checkable
class TasksFacadeProtocol(Protocol):
    """
    Type declarations for TasksService delegated methods.

    These methods are auto-generated by FacadeDelegationMixin from _delegations.
    This protocol makes them visible to MyPy for static type checking.
    """

    # ========================================================================
    # Sub-service access (for direct sub-service method calls)
    # ========================================================================

    @property
    def core(self) -> TasksCoreOperations:
        """Access to core sub-service for methods like verify_ownership."""
        ...

    @property
    def intelligence(self) -> Any:
        """Access to intelligence sub-service."""
        ...

    # ========================================================================
    # Explicit facade methods (not delegated)
    # ========================================================================

    async def create_task(self, request: Any, user_uid: str) -> Result[Task]:
        """Create a new task."""
        ...

    async def update_task(self, uid: str, updates: dict[str, Any]) -> Result[Any]:
        """Update a task."""
        ...

    # ========================================================================
    # Core delegations (→ TasksCoreService)
    # ========================================================================

    async def get_task(self, uid: str) -> Result[Any]:
        """Get a task by UID."""
        ...

    async def get_user_tasks(self, user_uid: str, limit: int = 100) -> Result[list[Any]]:
        """Get tasks for a specific user."""
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Any]]:
        """Get user tasks within date range."""
        ...

    async def get_for_user(self, uid: str, user_uid: str) -> Result[Any]:
        """Get task for user with ownership verification."""
        ...

    # ========================================================================
    # Search delegations (→ TasksSearchService)
    # ========================================================================

    async def get_tasks_for_goal(self, goal_uid: str, limit: int = 100) -> Result[list[Any]]:
        """Get tasks linked to a specific goal."""
        ...

    async def get_tasks_for_habit(self, habit_uid: str, limit: int = 100) -> Result[list[Any]]:
        """Get tasks linked to a specific habit."""
        ...

    async def get_tasks_applying_knowledge(
        self, knowledge_uid: str, limit: int = 100
    ) -> Result[list[Any]]:
        """Get tasks applying specific knowledge."""
        ...

    async def get_prioritized_tasks(
        self, user_context: UserContext | None, limit: int = 10
    ) -> Result[list[Any]]:
        """Get tasks prioritized for user's context."""
        ...

    # ========================================================================
    # Progress delegations (→ TasksProgressService)
    # ========================================================================

    async def assign_task_to_user(
        self,
        task_uid: str,
        target_user_uid: str,
        assigned_by: str | None = None,
        priority_override: str | None = None,
    ) -> Result[Any]:
        """Assign a task to a user."""
        ...

    async def check_prerequisites(self, task_uid: str) -> Result[dict[str, Any]]:
        """Check if task prerequisites are met."""
        ...

    async def record_task_completion(
        self, task_uid: str, completion_data: dict[str, Any] | None = None
    ) -> Result[Any]:
        """Record task completion."""
        ...

    # ========================================================================
    # Relationship delegations (→ UnifiedRelationshipService)
    # ========================================================================

    async def get_task_completion_impact(self, entity_uid: str) -> Result[dict[str, Any]]:
        """Get impact of completing this task."""
        ...

    async def get_task_with_semantic_context(
        self, entity_uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """Get task with semantic relationship context."""
        ...

    # ========================================================================
    # Analytics delegations (→ TasksService direct / TasksIntelligenceService)
    # ========================================================================

    async def get_learning_opportunities(
        self, _filters: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]]]:
        """Get learning opportunities from tasks."""
        ...

    async def generate_task_insights(self, task_uid: str) -> Result[dict[str, Any]]:
        """Generate insights for a specific task."""
        ...

    # ========================================================================
    # Additional Task operations (Added 2026-02-02)
    # ========================================================================

    @property
    def search(self) -> Any:
        """Access to search sub-service."""
        ...

    async def create_task_dependency(
        self,
        dependent_task_uid: str,
        blocks_task_uid: str,
        is_hard_dependency: bool = True,
        dependency_type: str = "blocks",
    ) -> Result[bool]:
        """Create dependency between tasks."""
        ...

    async def get_task_dependencies(self, task_uid: str) -> Result[list[Any]]:
        """Get dependencies for a task."""
        ...

    async def get_task_practice_opportunities(
        self, task_uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """Get practice opportunities related to a task."""
        ...

    async def get_user_assigned_tasks(
        self, user_uid: str, include_completed: bool = False, limit: int = 100
    ) -> Result[list[Any]]:
        """Get tasks assigned to a user."""
        ...


@runtime_checkable
class EventsFacadeProtocol(Protocol):
    """
    Type declarations for EventsService delegated methods.

    These methods are auto-generated by FacadeDelegationMixin from _delegations.
    This protocol makes them visible to MyPy for static type checking.
    """

    # ========================================================================
    # Sub-service access (for direct sub-service method calls)
    # ========================================================================

    @property
    def core(self) -> EventsCoreOperations:
        """Access to core sub-service for methods like verify_ownership, create."""
        ...

    @property
    def intelligence(self) -> Any:
        """Access to intelligence sub-service."""
        ...

    @property
    def backend(self) -> BackendCrudOperations:
        """Access to backend for direct operations like update."""
        ...

    # ========================================================================
    # Core delegations (→ EventsCoreService)
    # ========================================================================

    async def get_event(self, uid: str) -> Result[Any]:
        """Get an event by UID."""
        ...

    async def get_user_events(self, user_uid: str, limit: int = 100) -> Result[list[Any]]:
        """Get events for a specific user."""
        ...

    async def get_for_user(self, uid: str, user_uid: str) -> Result[Any]:
        """Get event for user with ownership verification."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Ku]:
        """Update an event."""
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Any]]:
        """Get user events within date range."""
        ...

    # ========================================================================
    # Search delegations (→ EventsSearchService)
    # ========================================================================

    async def search_events(self, query: str, limit: int = 50) -> Result[list[Any]]:
        """Text search on event title/description."""
        ...

    async def get_calendar_events(
        self, start_date: str | None = None, end_date: str | None = None, view: str = "month"
    ) -> Result[list[Any]]:
        """Get events for calendar view."""
        ...

    async def get_events_in_range(
        self, start_date: Any, end_date: Any, user_uid: str | None = None
    ) -> Result[list[Any]]:
        """Get events within date range."""
        ...

    async def get_prioritized_events(
        self, user_context: UserContext | None, limit: int = 10
    ) -> Result[list[Any]]:
        """Get events prioritized for user's context."""
        ...

    # ========================================================================
    # Intelligence delegations (→ EventsIntelligenceService)
    # ========================================================================

    async def get_event_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Any, Any]]:
        """Get event with full graph context."""
        ...

    async def analyze_event_performance(self, event_uid: str) -> Result[dict[str, Any]]:
        """Analyze event performance and outcomes."""
        ...

    # ========================================================================
    # Additional Event operations (Added 2026-02-02)
    # ========================================================================

    async def add_attendee(self, event_uid: str, attendee_data: dict[str, Any]) -> Result[str]:
        """Add attendee to event. Returns attendee UID."""
        ...

    async def remove_attendee(self, event_uid: str, attendee_uid: str) -> Result[bool]:
        """Remove attendee from event."""
        ...

    async def get_event_attendees(self, event_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all attendees for an event."""
        ...

    async def update_event_status(self, request: Any) -> Result[Any]:
        """Update event status."""
        ...

    async def check_conflicts(
        self, start_time: Any, end_time: Any, user_uid: str | None = None
    ) -> Result[list[Any]]:
        """Check for scheduling conflicts."""
        ...

    async def create_recurring_instances(
        self, event_uid: str, recurrence_data: dict[str, Any]
    ) -> Result[list[str]]:
        """Create recurring event instances. Returns list of created event UIDs."""
        ...

    async def get_recurring_events(self, parent_uid: str, limit: int = 100) -> Result[list[Any]]:
        """Get all instances of a recurring event."""
        ...


@runtime_checkable
class HabitsFacadeProtocol(Protocol):
    """
    Type declarations for HabitsService delegated methods.

    These methods are auto-generated by FacadeDelegationMixin from _delegations.
    This protocol makes them visible to MyPy for static type checking.
    """

    # ========================================================================
    # Sub-service access (for direct sub-service method calls)
    # ========================================================================

    @property
    def core(self) -> HabitsCoreOperations:
        """Access to core sub-service for methods like verify_ownership, create_habit."""
        ...

    @property
    def intelligence(self) -> Any:
        """Access to intelligence sub-service."""
        ...

    @property
    def backend(self) -> BackendCrudOperations:
        """Access to backend for direct operations like create, get, update."""
        ...

    @property
    def completions(self) -> Any:
        """Access to completions sub-service for habit completion tracking."""
        ...

    # ========================================================================
    # Explicit facade methods (not delegated)
    # ========================================================================

    async def create_habit(self, habit_request: HabitCreateRequest, user_uid: str) -> Result[Habit]:
        """Create a habit from a request with user_uid."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Any]:
        """Update a habit."""
        ...

    # ========================================================================
    # Core delegations (→ HabitsCoreService)
    # ========================================================================

    async def get_habit(self, uid: str) -> Result[Any]:
        """Get a habit by UID."""
        ...

    async def get_user_habits(self, user_uid: str, limit: int = 100) -> Result[list[Any]]:
        """Get habits for a specific user."""
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Any]]:
        """Get user habits within date range."""
        ...

    async def get_for_user(self, uid: str, user_uid: str) -> Result[Any]:
        """Get habit for user with ownership verification."""
        ...

    # ========================================================================
    # Search delegations (→ HabitSearchService)
    # ========================================================================

    async def search_habits(self, query: str, limit: int = 50) -> Result[list[Any]]:
        """Text search on habit name/description."""
        ...

    async def list_habit_categories(self, user_uid: str | None = None) -> Result[list[str]]:
        """List user's habit categories."""
        ...

    async def list_all_habit_categories(self) -> Result[list[str]]:
        """List all habit categories."""
        ...

    async def get_habits_by_category(
        self, category: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[Any]]:
        """Filter habits by category."""
        ...

    async def get_habits_due_today(self, user_uid: str) -> Result[list[Any]]:
        """Get habits due today for user."""
        ...

    async def get_overdue_habits(self, limit: int = 100) -> Result[list[Any]]:
        """Get overdue habits."""
        ...

    async def get_prioritized_habits(
        self, user_context: UserContext | None, limit: int = 10
    ) -> Result[list[Any]]:
        """Get habits prioritized for user's context."""
        ...

    # ========================================================================
    # Intelligence delegations (→ HabitsIntelligenceService)
    # ========================================================================

    async def get_habit_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Any, Any]]:
        """Get habit with full graph context."""
        ...

    async def analyze_habit_performance(self, habit_uid: str) -> Result[dict[str, Any]]:
        """Analyze habit performance and consistency."""
        ...

    # ========================================================================
    # Additional Habit operations (Added 2026-02-02)
    # ========================================================================

    async def track_habit(self, habit_uid: str, tracked_at: Any = None) -> Result[bool]:
        """Track a habit completion."""
        ...

    async def untrack_habit(self, habit_uid: str, tracked_at: Any = None) -> Result[bool]:
        """Remove a habit tracking entry."""
        ...

    async def get_habit_progress(self, habit_uid: str, days: int = 30) -> Result[dict[str, Any]]:
        """Get habit progress over time period."""
        ...

    async def get_habit_streak(self, habit_uid: str) -> Result[dict[str, Any]]:
        """Get current habit streak information."""
        ...

    async def set_habit_reminder(
        self, habit_uid: str, reminder_data: dict[str, Any]
    ) -> Result[str]:
        """Set reminder for habit. Returns reminder UID."""
        ...

    async def get_habit_reminders(self, habit_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all reminders for a habit."""
        ...

    async def delete_habit_reminder(self, habit_uid: str, reminder_uid: str) -> Result[bool]:
        """Delete a habit reminder."""
        ...


# =============================================================================
# MocFacadeProtocol - REMOVED JANUARY 2026
# =============================================================================
#
# MocFacadeProtocol removed January 2026 - MOC is now KU-based.
# A KU "is" a MOC when it has outgoing ORGANIZES relationships to other KUs.
# See: /docs/domains/moc.md for architecture documentation


@runtime_checkable
class LsFacadeProtocol(Protocol):
    """
    Type declarations for LsService delegated methods.

    These methods are auto-generated by FacadeDelegationMixin from _delegations.
    This protocol makes them visible to MyPy for static type checking.
    """

    # ========================================================================
    # Sub-service access (for direct sub-service method calls)
    # ========================================================================

    @property
    def intelligence(self) -> Any:
        """Access to intelligence sub-service."""
        ...

    # ========================================================================
    # Core delegations (→ LsCoreService)
    # ========================================================================

    async def create_step(self, entity: Ku, path_uid: str | None = None) -> Result[Ku]:
        """Create a new learning step."""
        ...

    async def get_step(self, uid: str) -> Result[Ku | None]:
        """Get a learning step by UID."""
        ...

    async def update_step(self, uid: str, updates: dict[str, Any]) -> Result[Ku]:
        """Update a learning step."""
        ...

    async def delete_step(self, uid: str) -> Result[bool]:
        """Delete a learning step."""
        ...

    async def list_steps(
        self,
        path_uid: str | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
        user_uid: str | None = None,
    ) -> Result[list[Ku]]:
        """List learning steps with pagination."""
        ...

    # ========================================================================
    # Additional LS operations (Added 2026-02-02)
    # ========================================================================

    @property
    def relationships(self) -> Any:
        """Access to relationships service."""
        ...

    async def attach_step_to_path(
        self, step_uid: str, path_uid: str, sequence: int
    ) -> Result[bool]:
        """Attach a learning step to a learning path."""
        ...

    async def detach_step_from_path(self, step_uid: str, path_uid: str) -> Result[bool]:
        """Detach a learning step from a learning path."""
        ...


@runtime_checkable
class ChoicesFacadeProtocol(Protocol):
    """
    Type declarations for ChoicesService delegated methods.

    These methods are auto-generated by FacadeDelegationMixin from _delegations.
    This protocol makes them visible to MyPy for static type checking.
    """

    # ========================================================================
    # Sub-service access (for direct sub-service method calls)
    # ========================================================================

    @property
    def core(self) -> ChoicesCoreOperations:
        """Access to core sub-service for methods like verify_ownership, create_choice, make_decision."""
        ...

    @property
    def intelligence(self) -> Any:
        """Access to intelligence sub-service."""
        ...

    # ========================================================================
    # Explicit facade methods (not delegated)
    # ========================================================================

    async def update_choice(self, uid: str, request: Any) -> Result[Any]:
        """Update a choice."""
        ...

    async def add_option(
        self,
        choice_uid: str,
        title: str,
        description: str,
        feasibility_score: float = 0.5,
        risk_level: float = 0.5,
        potential_impact: float = 0.5,
        resource_requirement: float = 0.5,
        estimated_duration: int | None = None,
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Result[Any]:
        """Add an option to a choice."""
        ...

    # ========================================================================
    # Core delegations (→ ChoicesCoreService)
    # ========================================================================

    async def get_choice(self, uid: str) -> Result[Any]:
        """Get a choice by UID."""
        ...

    async def get_user_choices(self, user_uid: str, limit: int = 100) -> Result[list[Any]]:
        """Get choices for a specific user."""
        ...

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Any]]:
        """Get user choices within date range."""
        ...

    # ========================================================================
    # Learning delegations (→ ChoicesLearningService)
    # ========================================================================

    async def create_choice_with_learning_guidance(
        self, request: Any, user_uid: str
    ) -> Result[dict[str, Any]]:
        """Create choice with learning path guidance."""
        ...

    async def get_learning_informed_guidance(
        self, choice_uid: str, user_uid: str
    ) -> Result[dict[str, Any]]:
        """Get learning-informed guidance for a choice."""
        ...

    async def track_choice_learning_outcomes(
        self, choice_uid: str, outcome_data: dict[str, Any]
    ) -> Result[dict[str, Any]]:
        """Track learning outcomes from a choice."""
        ...

    async def suggest_learning_aligned_choices(
        self, user_uid: str, limit: int = 5
    ) -> Result[list[dict[str, Any]]]:
        """Suggest choices aligned with learning goals."""
        ...

    # ========================================================================
    # Intelligence delegations (→ ChoicesIntelligenceService)
    # ========================================================================

    async def get_choice_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Any, Any]]:
        """Get choice with full graph context."""
        ...

    async def get_decision_intelligence(
        self, choice_uid: str, user_uid: str
    ) -> Result[dict[str, Any]]:
        """Get decision intelligence for a choice."""
        ...

    async def analyze_choice_impact(self, choice_uid: str) -> Result[dict[str, Any]]:
        """Analyze potential impact of a choice."""
        ...

    async def get_decision_patterns(self, user_uid: str, days: int = 90) -> Result[dict[str, Any]]:
        """Get user's decision patterns over time."""
        ...

    async def get_choice_quality_correlations(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get correlations between choice factors and outcomes."""
        ...

    async def get_domain_decision_patterns(
        self, user_uid: str, domain: str
    ) -> Result[dict[str, Any]]:
        """Get decision patterns for a specific domain."""
        ...

    # ========================================================================
    # Search delegations (→ ChoicesSearchService)
    # ========================================================================

    async def search_choices(self, query: str, limit: int = 50) -> Result[list[Any]]:
        """Text search on choice title/description."""
        ...

    async def get_choices_by_status(self, status: str, limit: int = 100) -> Result[list[Any]]:
        """Filter choices by status."""
        ...

    async def get_choices_by_domain(self, domain: Any, limit: int = 100) -> Result[list[Any]]:
        """Filter choices by domain."""
        ...

    async def get_pending_choices(self, limit: int = 100) -> Result[list[Any]]:
        """Get pending choices."""
        ...

    async def get_choices_due_soon(self, days_ahead: int = 7) -> Result[list[Any]]:
        """Get choices with deadlines within specified days."""
        ...

    async def get_overdue_choices(self, limit: int = 100) -> Result[list[Any]]:
        """Get choices past their deadline."""
        ...

    async def get_choices_by_urgency(self, urgency: str, limit: int = 100) -> Result[list[Any]]:
        """Filter choices by urgency level."""
        ...

    async def get_choices_needing_decision(self, limit: int = 100) -> Result[list[Any]]:
        """Get choices that need a decision."""
        ...

    async def get_prioritized_choices(
        self, user_context: UserContext | None, limit: int = 10
    ) -> Result[list[Any]]:
        """Get choices prioritized for user's context."""
        ...

    async def list_choice_categories(self, user_uid: str | None = None) -> Result[list[str]]:
        """List user's choice categories."""
        ...

    async def list_all_choice_categories(self) -> Result[list[str]]:
        """List all choice categories."""
        ...

    # ========================================================================
    # Additional Choice operations (Added 2026-02-02)
    # ========================================================================

    async def make_decision(
        self,
        choice_uid: str,
        selected_option_uid: str,
        decision_rationale: str | None = None,
        confidence: float = 0.5,
    ) -> Result[Any]:
        """Make a decision by selecting an option."""
        ...

    async def update_option(
        self,
        choice_uid: str,
        option_uid: str,
        title: str | None = None,
        description: str | None = None,
        feasibility_score: float | None = None,
        risk_level: float | None = None,
        potential_impact: float | None = None,
        resource_requirement: float | None = None,
        estimated_duration: int | None = None,
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Result[Any]:
        """Update a choice option."""
        ...

    async def get_for_user(self, uid: str, user_uid: str) -> Result[Any]:
        """Get choice for user with ownership verification."""
        ...


@runtime_checkable
class KuFacadeProtocol(Protocol):
    """
    Type declarations for KuService delegated methods.

    These methods are auto-generated by FacadeDelegationMixin from _delegations.
    This protocol makes them visible to MyPy for static type checking.
    """

    # ========================================================================
    # Core delegations (→ KuCoreService)
    # ========================================================================

    async def create(self, data: dict[str, Any]) -> Result[Any]:
        """Create a new knowledge unit."""
        ...

    async def get(self, uid: str) -> Result[Any | None]:
        """Get a knowledge unit by UID."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Any]:
        """Update a knowledge unit."""
        ...

    async def delete(self, uid: str) -> Result[bool]:
        """Delete a knowledge unit."""
        ...

    async def publish(self, uid: str) -> Result[Any]:
        """Publish a knowledge unit."""
        ...

    async def archive(self, uid: str) -> Result[Any]:
        """Archive a knowledge unit."""
        ...

    async def get_user_mastery(self, uid: str, user_uid: str) -> Result[Any]:
        """Get user's mastery level for this KU."""
        ...

    async def get_chunks(self, uid: str) -> Result[list[Any]]:
        """Get content chunks for a KU."""
        ...

    async def analyze_content(self, uid: str) -> Result[dict[str, Any]]:
        """Analyze KU content for insights."""
        ...

    async def get_with_template(self, uid: str) -> Result[Any | None]:
        """Get KU with template (alias for get)."""
        ...

    # ========================================================================
    # Search delegations (→ KuSearchService)
    # ========================================================================

    async def search_by_title_template(self, query: str, limit: int = 50) -> Result[list[Any]]:
        """Search KUs by title pattern."""
        ...

    async def search_with_user_context(
        self, query: str, user_uid: str, limit: int = 50
    ) -> Result[list[Any]]:
        """Search KUs with user context."""
        ...

    async def find_similar_content(self, uid: str, limit: int = 10) -> Result[list[Any]]:
        """Find KUs with similar content."""
        ...

    async def search_by_tags(self, tags: list[str], limit: int = 50) -> Result[list[Any]]:
        """Search KUs by tags."""
        ...

    async def search_by_facets(self, facets: dict[str, Any], limit: int = 50) -> Result[list[Any]]:
        """Search KUs using faceted search."""
        ...

    async def search_chunks_with_facets(
        self, facets: dict[str, Any], limit: int = 50
    ) -> Result[list[Any]]:
        """Search KU chunks using faceted search."""
        ...

    async def search_chunks(self, query: str, limit: int = 50) -> Result[list[Any]]:
        """Search within KU chunks."""
        ...

    async def search_by_features(
        self, features: dict[str, Any], limit: int = 50
    ) -> Result[list[Any]]:
        """Search KUs by features."""
        ...

    async def search_with_semantic_intent(
        self, query: str, intent: str, limit: int = 50
    ) -> Result[list[Any]]:
        """Search KUs with semantic intent."""
        ...

    async def get_content_chunks(self, uid: str) -> Result[list[Any]]:
        """Get content chunks for a KU (search service method)."""
        ...

    # ========================================================================
    # Graph delegations (→ KuGraphService)
    # ========================================================================

    async def find_prerequisites(self, uid: str, depth: int = 2) -> Result[list[Any]]:
        """Find prerequisite KUs for this KU."""
        ...

    async def find_next_steps(self, uid: str, depth: int = 2) -> Result[list[Any]]:
        """Find next KUs after this one."""
        ...

    async def get_knowledge_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Any, Any]]:
        """Get KU with full graph context."""
        ...

    async def link_prerequisite(self, uid: str, prerequisite_uid: str) -> Result[bool]:
        """Link a prerequisite to this KU."""
        ...

    async def link_parent_child(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Link parent-child relationship."""
        ...

    async def get_prerequisite_chain(self, uid: str) -> Result[list[Any]]:
        """Get full prerequisite chain for a KU."""
        ...

    async def analyze_knowledge_gaps(self, user_uid: str) -> Result[dict[str, Any]]:
        """Analyze user's knowledge gaps."""
        ...

    async def get_learning_recommendations(
        self, user_uid: str, limit: int = 10
    ) -> Result[list[Any]]:
        """Get learning recommendations for user."""
        ...

    async def find_time_aware_learning_path(
        self, goal_uid: str, available_hours: int
    ) -> Result[list[Any]]:
        """Find time-aware learning path."""
        ...

    async def update_hub_scores(self) -> Result[bool]:
        """Update hub scores for all KUs."""
        ...

    async def get_foundational_knowledge(self, limit: int = 20) -> Result[list[Any]]:
        """Get foundational KUs."""
        ...

    async def find_events_applying_knowledge(self, uid: str) -> Result[list[Any]]:
        """Find events that apply this KU."""
        ...

    async def find_habits_reinforcing_knowledge(self, uid: str) -> Result[list[Any]]:
        """Find habits that reinforce this KU."""
        ...

    async def find_learning_steps_containing(self, uid: str) -> Result[list[Any]]:
        """Find learning steps that contain this KU."""
        ...

    async def find_learning_paths_teaching(self, uid: str) -> Result[list[Any]]:
        """Find learning paths that teach this KU."""
        ...

    async def find_tasks_applying_knowledge(self, uid: str) -> Result[list[Any]]:
        """Find tasks that apply this KU."""
        ...

    async def find_goals_requiring_knowledge(self, uid: str) -> Result[list[Any]]:
        """Find goals that require this KU."""
        ...

    async def find_choices_informed_by_knowledge(self, uid: str) -> Result[list[Any]]:
        """Find choices informed by this KU."""
        ...

    async def find_principles_embodying_knowledge(self, uid: str) -> Result[list[Any]]:
        """Find principles that embody this KU."""
        ...

    # ========================================================================
    # Semantic delegations (→ KuSemanticService)
    # ========================================================================

    async def create_with_semantic_relationships(
        self, data: dict[str, Any], relationships: dict[str, list[str]]
    ) -> Result[Any]:
        """Create KU with semantic relationships."""
        ...

    async def get_semantic_neighborhood(self, uid: str, radius: int = 2) -> Result[dict[str, Any]]:
        """Get semantic neighborhood around a KU."""
        ...

    # ========================================================================
    # Additional KU operations (Added 2026-02-02)
    # ========================================================================

    async def create_knowledge_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: Any,
        confidence: float = 0.9,
        strength: float = 1.0,
        notes: str | None = None,
    ) -> Result[bool]:
        """Create relationship between two KUs."""
        ...

    async def get_knowledge_relationships(
        self, uid: str, relationship_type: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        """Get relationships for a KU."""
        ...

    async def get_knowledge_prerequisites(self, uid: str) -> Result[list[Any]]:
        """Get prerequisites for a KU."""
        ...

    async def get_knowledge_dependencies(self, uid: str, limit: int = 10) -> Result[list[Any]]:
        """Get dependencies for a KU."""
        ...

    async def update_ku_content(
        self, uid: str, content: str, title: str | None = None
    ) -> Result[Any]:
        """Update KU content and optionally title."""
        ...

    async def add_knowledge_tags(self, uid: str, tags: list[str]) -> Result[Any]:
        """Add tags to a KU."""
        ...

    async def remove_knowledge_tags(self, uid: str, tags: list[str]) -> Result[Any]:
        """Remove tags from a KU."""
        ...

    async def search_knowledge_units(self, query: str, limit: int = 50) -> Result[list[Any]]:
        """Search KUs by text query."""
        ...

    async def find_related_knowledge(
        self, uid: str, similarity_threshold: float = 0.7, limit: int = 10
    ) -> Result[list[Any]]:
        """Find related KUs based on similarity."""
        ...

    async def get_knowledge_recommendations(
        self, uid: str, user_uid: str, recommendation_type: str | None = None
    ) -> Result[list[Any]]:
        """Get knowledge recommendations for user."""
        ...

    async def list_knowledge_domains(self) -> Result[list[str]]:
        """List all knowledge domains."""
        ...

    async def get_knowledge_by_domain(self, domain: str, limit: int = 50) -> Result[list[Any]]:
        """Get KUs in a specific domain."""
        ...

    async def list_knowledge_categories(self) -> Result[list[str]]:
        """List all knowledge categories."""
        ...

    async def list_knowledge_tags(self, min_usage: int = 1) -> Result[list[dict[str, Any]]]:
        """List all knowledge tags with usage counts."""
        ...

    async def get_knowledge_stats(self, uid: str) -> Result[dict[str, Any]]:
        """Get statistics for a knowledge unit."""
        ...

    async def get_user_knowledge_context(
        self, uid: str, user_context: Any
    ) -> Result[dict[str, Any]]:
        """Get KU with user-specific context."""
        ...

    # ========================================================================
    # Adaptive curriculum delegations (→ KuAdaptiveService)
    # ========================================================================

    async def get_personalized_curriculum(
        self, user_uid: str, sel_category: Any, limit: int = 10
    ) -> Result[list[Any]]:
        """Get personalized KU curriculum for an SEL category."""
        ...

    async def get_sel_journey(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get user's SEL learning journey across all categories."""
        ...

    async def track_curriculum_completion(self, user_uid: str, ku_uid: str) -> Result[bool]:
        """Track that a user completed a KU in the curriculum."""
        ...

    @property
    def intelligence(self) -> Any:
        """Access to intelligence sub-service."""
        ...

    @property
    def user_service(self) -> Any:
        """Access to user service for context."""
        ...
