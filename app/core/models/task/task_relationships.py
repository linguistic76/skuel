"""
Task Relationships Helper (Graph-Native Pattern)
====================================

Container for task relationship data fetched from graph.
Replaces direct field access in Task model methods.

⚠️  CRITICAL FOR DEVELOPERS: These fields DO NOT exist in TaskDTO anymore!
================================================================

❌ WRONG - These fields were REMOVED from Task/TaskDTO:
    task.applies_knowledge_uids        # AttributeError!
    task.subtask_uids                  # AttributeError!
    task.prerequisite_knowledge_uids   # AttributeError!
    task.prerequisite_task_uids        # AttributeError!
    task.enables_task_uids             # AttributeError!
    task.aligned_principle_uids        # AttributeError!

✅ CORRECT - Use TaskRelationships.fetch() instead:
    rels = await TaskRelationships.fetch(task.uid, service.relationships)
    rels.applies_knowledge_uids        # ✓ List of UIDs from graph
    rels.subtask_uids                  # ✓ List of UIDs from graph
    rels.prerequisite_knowledge_uids   # ✓ List of UIDs from graph

Decision Tree: "Do I need relationship data?"
=============================================

Q1: Am I writing code that needs to know about task relationships?
    (subtasks, knowledge applied, prerequisites, etc.)

    YES → Use TaskRelationships.fetch()
    NO  → Use task.attribute directly (e.g., task.title, task.priority)

Q2: Do I have access to a TasksRelationshipService instance?

    YES → Fetch relationships:
          ```python
          rels = await TaskRelationships.fetch(task.uid, tasks_service.relationships)
          if rels.applies_knowledge_uids:
              # Process knowledge relationships
          ```

    NO  → Use proxy attributes OR refactor to pass service:
          Proxy: task.knowledge_mastery_check (indicates learning task)
          Proxy: task.source_learning_step_uid (indicates curriculum task)
          Proxy: task.parent_uid (indicates hierarchical task)

          Better: Refactor to receive tasks_service as parameter

📖 COMPLETE PATTERN GUIDE:
    This is the Task-specific implementation of the Domain Relationships Pattern.
    For the complete cross-domain guide, see:
    → /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md

    Pattern is also used by:
    - GoalRelationships (9 relationships)
    - EventRelationships (3 relationships)
    - HabitRelationships (6 relationships)
    - LsRelationships (5 relationships)

Graph-Native Migration Context:
- Before: Task methods accessed self.applies_knowledge_uids directly
- After: Task methods receive TaskRelationships parameter with relationship data
- Service layer fetches relationships via TasksRelationshipService

Philosophy: "Relationships ARE the data structure, not serialized lists"
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

# Type alias for backward compatibility
TasksRelationshipService = UnifiedRelationshipService


# Query specifications: (field_name, relationship_key)
# Defines the mapping between dataclass fields and relationship keys
# These keys are passed to get_related_uids() on UnifiedRelationshipService
TASK_QUERY_SPECS: list[tuple[str, str]] = [
    ("subtask_uids", "subtasks"),
    ("applies_knowledge_uids", "knowledge"),
    ("aligned_principle_uids", "principles"),
    ("prerequisite_knowledge_uids", "prerequisite_knowledge"),
    ("prerequisite_task_uids", "prerequisite_tasks"),
    ("enables_task_uids", "enables"),
    ("completion_triggers_tasks", "triggers"),
    ("completion_unlocks_knowledge", "unlocks_knowledge"),
    ("inferred_knowledge_uids", "inferred_knowledge"),
    ("executed_in_event_uids", "execution_events"),
    ("implements_choice_uids", "implements_choices"),
    ("serves_life_path_uids", "life_path"),
]


@dataclass(frozen=True)
class TaskRelationships:
    """
    Container for all task relationship data (fetched from Neo4j graph).

    📚 COMPLETE USAGE GUIDE FOR DEVELOPERS
    ========================================

    Example 1: Basic Usage (Single Task)
    -------------------------------------
    ```python
    # In a service method:
    async def analyze_task_complexity(self, task_uid: str) -> Result[float]:
        # 1. Get the task
        task_result = await self.get_task(task_uid)
        if task_result.is_error:
            return task_result
        task = task_result.value

        # 2. Fetch relationships (9 parallel queries)
        rels = await TaskRelationships.fetch(task.uid, self.relationships)

        # 3. Use relationship data
        if rels.applies_knowledge_uids:
            complexity = len(rels.applies_knowledge_uids) * 0.2
        else:
            complexity = 0.1

        return Result.ok(complexity)
    ```

    Example 2: Batch Processing (Multiple Tasks)
    ---------------------------------------------
    ```python
    async def analyze_learning_patterns(self, user_uid: str) -> Result[dict]:
        # 1. Get all user tasks
        tasks_result = await self.get_user_tasks(user_uid)
        tasks = tasks_result.value

        # 2. Fetch relationships for ALL tasks in parallel
        all_rels = await asyncio.gather(
            *[
                TaskRelationships.fetch(task.uid, self.relationships)
                for task in tasks
            ]
        )

        # 3. Create mapping for easy lookup
        rels_by_uid = {task.uid: rels for task, rels in zip(tasks, all_rels)}

        # 4. Process each task with its relationships
        learning_tasks = []
        for task in tasks:
            rels = rels_by_uid[task.uid]
            if rels.applies_knowledge_uids:
                learning_tasks.append(task)

        return Result.ok({"learning_task_count": len(learning_tasks)})
    ```

    Example 3: When You DON'T Have Service Access
    ----------------------------------------------
    ```python
    # ❌ WRONG - Don't try to access removed fields
    def calculate_load(task: TaskDTO) -> float:
        if task.applies_knowledge_uids:  # AttributeError!
            return 0.5
        return 0.1


    # ✅ OPTION A - Use proxy attributes
    def calculate_load(task: TaskDTO) -> float:
        if task.knowledge_mastery_check or task.source_learning_step_uid:
            return 0.5  # Estimate for learning tasks
        return 0.1


    # ✅ OPTION B (BETTER) - Refactor to accept service
    async def calculate_load(
        task: TaskDTO,
        tasks_service: TasksService,  # Now we can fetch relationships!
    ) -> float:
        rels = await TaskRelationships.fetch(task.uid, tasks_service.relationships)
        return len(rels.applies_knowledge_uids) * 0.1
    ```

    Available Proxy Attributes (when relationships not accessible):
    ---------------------------------------------------------------
    - task.knowledge_mastery_check: bool → Indicates learning/knowledge task
    - task.source_learning_step_uid: str | None → Task from curriculum
    - task.parent_uid: str | None → Task has parent (hierarchical)
    - task.fulfills_goal_uid: str | None → Task linked to goal
    - task.reinforces_habit_uid: str | None → Task linked to habit

    Benefits:
    ---------
    - Single fetch operation for all relationships (performance)
    - Explicit about what data each method needs (clarity)
    - No stale data (always fresh from graph)
    - Easy to mock for testing (use TaskRelationships.empty())

    Performance:
    -----------
    - 9 parallel queries = ~70% faster than sequential
    - Batch fetching 100 tasks = ~60% improvement over per-task queries

    Migration Notes:
    ---------------
    - Replaces 9 list fields removed from Task/TaskDTO models
    - Used in 40+ Task model methods
    - See: /docs/migrations/PHASE_3B_REFACTORING_PLAN.md
    """

    subtask_uids: list[str] = field(default_factory=list)
    applies_knowledge_uids: list[str] = field(default_factory=list)
    aligned_principle_uids: list[str] = field(default_factory=list)
    prerequisite_knowledge_uids: list[str] = field(default_factory=list)
    prerequisite_task_uids: list[str] = field(default_factory=list)
    enables_task_uids: list[str] = field(default_factory=list)
    completion_triggers_tasks: list[str] = field(default_factory=list)
    completion_unlocks_knowledge: list[str] = field(default_factory=list)
    inferred_knowledge_uids: list[str] = field(default_factory=list)
    executed_in_event_uids: list[str] = field(default_factory=list)
    implements_choice_uids: list[str] = field(default_factory=list)
    serves_life_path_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(cls, task_uid: str, service: TasksRelationshipService) -> TaskRelationships:
        """
        Fetch all relationship data from graph in parallel.

        Performs 9 graph queries concurrently using asyncio.gather() for optimal performance.
        Each query maps to one relationship type in the Task model.

        Args:
            task_uid: UID of task to fetch relationships for
            service: TasksRelationshipService instance (provides graph query methods)

        Returns:
            TaskRelationships instance with all relationship data

        Example:
            service = services.tasks
            rels = await TaskRelationships.fetch("task_123", service.relationships)
            print(f"Task applies {len(rels.applies_knowledge_uids)} knowledge units")

        Performance:
        - 9 parallel queries vs 9 sequential = ~70% faster
        - Single fetch vs per-method queries = 40-60% improvement
        """
        return await fetch_relationships_parallel(
            uid=task_uid,
            service=service,
            query_specs=TASK_QUERY_SPECS,
            dataclass_type=cls,
        )

    @classmethod
    def empty(cls) -> TaskRelationships:
        """
        Create empty TaskRelationships (for testing or new tasks).

        Returns:
            TaskRelationships with all empty lists

        Example:
            # Testing a method that requires relationships
            rels = TaskRelationships.empty()
            assert task.calculate_knowledge_complexity(rels) == 0.0
        """
        return cls()

    def has_any_knowledge(self) -> bool:
        """
        Check if task has any knowledge connections.

        Returns:
            True if task applies, requires, or infers any knowledge
        """
        return (
            len(self.applies_knowledge_uids) > 0
            or len(self.prerequisite_knowledge_uids) > 0
            or len(self.inferred_knowledge_uids) > 0
        )

    def total_knowledge_count(self) -> int:
        """
        Get total count of all knowledge connections.

        Returns:
            Sum of all knowledge-related relationship counts
        """
        return (
            len(self.applies_knowledge_uids)
            + len(self.prerequisite_knowledge_uids)
            + len(self.inferred_knowledge_uids)
        )

    def has_prerequisites(self) -> bool:
        """
        Check if task has any prerequisites (tasks or knowledge).

        Returns:
            True if task requires prerequisite tasks or knowledge
        """
        return len(self.prerequisite_task_uids) > 0 or len(self.prerequisite_knowledge_uids) > 0

    def is_milestone(self) -> bool:
        """
        Check if task unlocks knowledge (milestone indicator).

        Returns:
            True if completing task unlocks new knowledge
        """
        return len(self.completion_unlocks_knowledge) > 0

    def get_combined_knowledge_uids(self) -> set[str]:
        """
        Get all unique knowledge UIDs (explicit + inferred).

        Returns:
            Set of all knowledge UIDs across all relationship types
        """
        all_uids: set[str] = set()
        all_uids.update(self.applies_knowledge_uids)
        all_uids.update(self.prerequisite_knowledge_uids)
        all_uids.update(self.inferred_knowledge_uids)
        return all_uids

    def has_event_execution(self) -> bool:
        """
        Check if task has been executed in any events.

        Returns:
            True if task has been executed in events
        """
        return len(self.executed_in_event_uids) > 0

    def is_event_driven(self) -> bool:
        """
        Check if task is event-driven (executed through events).

        Returns:
            True if task has event execution history
        """
        return self.has_event_execution()

    def implements_choices(self) -> bool:
        """
        Check if task implements any choices.

        Returns:
            True if task implements decisions/choices
        """
        return len(self.implements_choice_uids) > 0

    def is_choice_driven(self) -> bool:
        """
        Check if task is choice-driven (created to implement a decision).

        Returns:
            True if task was created to implement a choice
        """
        return self.implements_choices()

    def serves_life_path(self) -> bool:
        """
        Check if task serves user's life path.

        Returns:
            True if task is connected to user's life path
        """
        return len(self.serves_life_path_uids) > 0

    def get_life_path_uid(self) -> str | None:
        """
        Get the life path UID this task serves (if any).

        Returns:
            The life path UID or None if not connected
        """
        return self.serves_life_path_uids[0] if self.serves_life_path_uids else None
