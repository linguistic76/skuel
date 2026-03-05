"""
Context Awareness Protocols - Explicit Dependencies for UserContext
====================================================================

These protocols define "slices" of UserContext that services can depend on,
making their actual dependencies explicit without breaking the unified model.

Philosophy:
-----------
UserContext has ~240 fields, but most services only need 5-10.
These protocols let services declare "I need task awareness" instead of
accepting the full context, which:

1. Makes dependencies explicit and testable
2. Documents what each service actually uses
3. Enables easier mocking (mock 5 fields, not 240)
4. Follows Interface Segregation Principle

Usage:
------
```python
# Before: unclear what's actually needed
async def get_ready_to_learn(self, context: UserContext) -> ...:

# After: explicit dependency
async def get_ready_to_learn(self, context: KnowledgeAwareness) -> ...:
```

UserContext implements ALL these protocols, so you can still pass it
anywhere. The protocols are purely for documentation and type checking.

Protocol Hierarchy:
-------------------
- CoreIdentity: user_uid, username (needed by everything)
- TaskAwareness: task UIDs, priorities, blockers
- KnowledgeAwareness: mastery, prerequisites, learning state
- HabitAwareness: habit UIDs, streaks, at-risk habits
- GoalAwareness: goal UIDs, progress, milestones
- EventAwareness: event UIDs, scheduling state
- PrincipleAwareness: principle UIDs, alignments
- ChoiceAwareness: pending choices, decision state
- LearningPathAwareness: learning paths, steps, progress
- FullAwareness: complete context (for Askesis, dashboards)
"""

from typing import Any, Protocol, runtime_checkable

# =============================================================================
# CORE IDENTITY - Every service needs at least this
# =============================================================================


@runtime_checkable
class CoreIdentity(Protocol):
    """
    Minimal user identification.

    Every service that operates on user data needs at least this.
    This is the foundation that all other awareness protocols extend.

    Fields:
        user_uid: Unique identifier for the user
        username: User's username for display/logging
    """

    user_uid: str
    username: str


# =============================================================================
# DOMAIN-SPECIFIC AWARENESS PROTOCOLS
# =============================================================================


@runtime_checkable
class TaskAwareness(Protocol):
    """
    Task-related context for services that work with tasks.

    Use when:
    - Checking task completion status
    - Finding blocked tasks
    - Getting today's tasks
    - Analyzing task-goal relationships

    Example services:
    - TasksProgressService
    - TasksRelationshipService
    - GoalTaskGenerator (partial)
    """

    # Core identity (inherited conceptually)
    user_uid: str

    # Active task state
    active_task_uids: list[str]
    blocked_task_uids: set[str]
    completed_task_uids: set[str]

    # Task scheduling
    overdue_task_uids: list[str]
    today_task_uids: list[str]
    this_week_task_uids: list[str]

    # Task relationships
    task_priorities: dict[str, float]
    tasks_by_goal: dict[str, list[str]]

    # Knowledge (needed for prerequisite checks in task planning)
    knowledge_mastery: dict[str, float]

    # Rich context (required for domain planning methods)
    is_rich_context: bool
    entities_rich: dict[str, list[dict[str, Any]]]

    def get_rich_entities(
        self, domain: str, filter_uids: set[str] | None = None
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class KnowledgeAwareness(Protocol):
    """
    Knowledge-related context for learning services.

    Use when:
    - Checking mastery levels
    - Finding prerequisites
    - Recommending what to learn
    - Analyzing learning gaps

    Example services:
    - KuGraphService
    - LpIntelligenceService
    - GoalsLearningService
    """

    # Core identity
    user_uid: str

    # Mastery state
    knowledge_mastery: dict[str, float]  # uid -> mastery (0.0-1.0)
    mastered_knowledge_uids: set[str]
    in_progress_knowledge_uids: set[str]

    # Prerequisites
    prerequisites_needed: dict[str, list[str]]  # blocked_uid -> [prereq_uids]

    # Learning velocity
    learning_velocity_by_domain: dict[str, float]

    # Rich context (optional)
    knowledge_units_rich: dict[str, dict[str, Any]]


@runtime_checkable
class HabitAwareness(Protocol):
    """
    Habit-related context for habit tracking services.

    Use when:
    - Checking habit streaks
    - Finding at-risk habits
    - Analyzing habit-goal relationships
    - Recommending habit maintenance

    Example services:
    - HabitsProgressService
    - HabitsEventIntegrationService
    - EventsHabitIntegrationService
    """

    # Core identity
    user_uid: str

    # Habit state
    active_habit_uids: set[str]
    habit_streaks: dict[str, int]  # uid -> streak count
    at_risk_habits: list[str]  # habits at risk of breaking

    # Habit relationships
    habits_by_goal: dict[str, list[str]]  # goal_uid -> habit_uids
    keystone_habits: list[str]  # keystone habits (high-impact habits)

    # Rich context (required for domain planning methods)
    is_rich_context: bool
    entities_rich: dict[str, list[dict[str, Any]]]

    def get_rich_entities(
        self, domain: str, filter_uids: set[str] | None = None
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class GoalAwareness(Protocol):
    """
    Goal-related context for goal tracking services.

    Use when:
    - Checking goal progress
    - Finding milestone status
    - Analyzing goal hierarchies
    - Recommending next steps

    Example services:
    - GoalsProgressService
    - GoalsRelationshipService
    - GoalTaskGenerator
    """

    # Core identity
    user_uid: str

    # Goal state
    active_goal_uids: set[str]
    completed_goal_uids: set[str]
    goal_progress: dict[str, float]  # uid -> progress (0.0-1.0)

    # Goal relationships
    tasks_by_goal: dict[str, list[str]]
    habits_by_goal: dict[str, list[str]]

    # Milestone tracking
    goal_milestones_completed: dict[str, list[str]]  # goal_uid -> milestone UIDs completed

    # Goal risk tracking
    at_risk_goals: list[str]

    # Goal methods
    def get_stalled_goals(self, _threshold_days: int = 14) -> list[str]: ...

    # Rich context (required for domain planning methods)
    is_rich_context: bool
    entities_rich: dict[str, list[dict[str, Any]]]

    def get_rich_entities(
        self, domain: str, filter_uids: set[str] | None = None
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class EventAwareness(Protocol):
    """
    Event-related context for calendar/scheduling services.

    Use when:
    - Getting upcoming events
    - Checking event conflicts
    - Analyzing event patterns
    - Scheduling recommendations

    Example services:
    - EventsRelationshipService
    - EventsHabitIntegrationService
    - CalendarService
    """

    # Core identity
    user_uid: str

    # Event state
    upcoming_event_uids: list[str]
    today_event_uids: list[str]
    scheduled_event_uids: list[str]
    recurring_event_uids: list[str]

    # Event tracking
    event_attendance: dict[str, int]
    event_streaks: dict[str, int]

    # Rich context (required for domain planning methods)
    is_rich_context: bool
    entities_rich: dict[str, list[dict[str, Any]]]

    def get_rich_entities(
        self, domain: str, filter_uids: set[str] | None = None
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class PrincipleAwareness(Protocol):
    """
    Principle-related context for value alignment services.

    Use when:
    - Checking principle alignment
    - Finding goals guided by principles
    - Analyzing decision alignment

    Example services:
    - PrinciplesRelationshipService
    - ChoicesRelationshipService (partial)
    """

    # Core identity
    user_uid: str

    # Principle state
    core_principle_uids: set[str]

    # Rich context (required for domain planning methods)
    is_rich_context: bool
    entities_rich: dict[str, list[dict[str, Any]]]

    def get_rich_entities(
        self, domain: str, filter_uids: set[str] | None = None
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class ChoiceAwareness(Protocol):
    """
    Choice-related context for decision-making services.

    Use when:
    - Getting pending decisions
    - Analyzing choice patterns
    - Checking principle alignment of choices

    Example services:
    - ChoicesRelationshipService
    """

    # Core identity
    user_uid: str

    # Choice state
    pending_choice_uids: list[str]
    resolved_choice_uids: set[str]

    # For alignment checking
    core_principle_uids: set[str]
    knowledge_mastery: dict[str, float]

    # Rich context (required for domain planning methods)
    is_rich_context: bool
    entities_rich: dict[str, list[dict[str, Any]]]

    def get_rich_entities(
        self, domain: str, filter_uids: set[str] | None = None
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class LearningPathAwareness(Protocol):
    """
    Learning path context for curriculum services.

    Use when:
    - Tracking learning path progress
    - Finding next learning steps
    - Analyzing learning state

    Example services:
    - LpIntelligenceService
    - LsProgressService
    """

    # Core identity
    user_uid: str

    # Learning path state
    enrolled_path_uids: list[str]
    completed_path_uids: set[str]  # completed learning paths
    learning_path_step_uids: list[str]  # current step UIDs

    # Knowledge (for prerequisites)
    knowledge_mastery: dict[str, float]
    mastered_knowledge_uids: set[str]

    # Rich context (optional)
    enrolled_paths_rich: list[dict[str, Any]]
    active_learning_steps_rich: list[dict[str, Any]]


# =============================================================================
# COMPOSITE AWARENESS PROTOCOLS
# =============================================================================


@runtime_checkable
class CrossDomainAwareness(Protocol):
    """
    Multi-domain context for services that span domains.

    Use when:
    - Analyzing task-goal-habit relationships
    - Finding cross-domain patterns
    - Computing life alignment

    Example services:
    - UserContextIntelligence
    - ReportMetricsService
    """

    # Core identity
    user_uid: str

    # Task awareness
    active_task_uids: list[str]
    blocked_task_uids: set[str]
    overdue_task_uids: list[str]
    tasks_by_goal: dict[str, list[str]]

    # Goal awareness
    active_goal_uids: set[str]
    goal_progress: dict[str, float]

    # Habit awareness
    active_habit_uids: set[str]
    habit_streaks: dict[str, int]
    at_risk_habits: list[str]

    # Knowledge awareness
    knowledge_mastery: dict[str, float]
    mastered_knowledge_uids: set[str]


@runtime_checkable
class FullAwareness(Protocol):
    """
    Complete user context - use sparingly.

    Use ONLY when:
    - Building dashboards (need everything)
    - Askesis recommendations (cross-domain intelligence)
    - Life path alignment (needs full state)
    - ProfileHubData generation

    Example services:
    - AskesisService
    - UserService.get_profile_hub_data()
    - UserContextIntelligence

    WARNING: If you're using FullAwareness, ask yourself if a smaller
    protocol would suffice. Most services don't need 240 fields.
    """

    # Core identity
    user_uid: str
    username: str

    # Task awareness
    active_task_uids: list[str]
    blocked_task_uids: set[str]
    completed_task_uids: set[str]
    overdue_task_uids: list[str]
    today_task_uids: list[str]
    this_week_task_uids: list[str]
    task_priorities: dict[str, float]
    tasks_by_goal: dict[str, list[str]]

    # Goal awareness
    active_goal_uids: set[str]
    completed_goal_uids: set[str]
    goal_progress: dict[str, float]

    # Habit awareness
    active_habit_uids: set[str]
    habit_streaks: dict[str, int]
    at_risk_habits: list[str]
    habits_by_goal: dict[str, list[str]]

    # Knowledge awareness
    knowledge_mastery: dict[str, float]
    mastered_knowledge_uids: set[str]
    in_progress_knowledge_uids: set[str]
    prerequisites_needed: dict[str, list[str]]

    # Event awareness
    upcoming_event_uids: list[str]
    today_event_uids: list[str]
    scheduled_event_uids: list[str]

    # Principle awareness
    core_principle_uids: set[str]

    # Choice awareness
    pending_choice_uids: list[str]

    # Learning path awareness
    enrolled_path_uids: list[str]
    completed_path_uids: set[str]
    learning_path_step_uids: list[str]

    # User state
    is_overwhelmed: bool
    is_blocked: bool

    # Rich context (all activity domains)
    is_rich_context: bool
    entities_rich: dict[str, list[dict[str, Any]]]
    knowledge_units_rich: dict[str, dict[str, Any]]

    def get_rich_entities(
        self, domain: str, filter_uids: set[str] | None = None
    ) -> list[dict[str, Any]]: ...


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "ChoiceAwareness",
    # Core
    "CoreIdentity",
    # Composite
    "CrossDomainAwareness",
    "EventAwareness",
    "FullAwareness",
    "GoalAwareness",
    "HabitAwareness",
    "KnowledgeAwareness",
    "LearningPathAwareness",
    "PrincipleAwareness",
    # Domain-specific
    "TaskAwareness",
]
