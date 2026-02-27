"""
Context-First Mixin - User-Aware Relationship Enrichment
=========================================================

This mixin provides context-aware enrichment methods that relationship
services can use to transform raw entities into contextual entities.

**Core Philosophy:** "Filter by readiness, rank by relevance, enrich with insights"

**Integration:**
```python
class TasksRelationshipService(
    ContextFirstMixin,
    GenericRelationshipService[TasksOperations, Task, TaskDTO]
):
    # Now has access to:
    # - _enrich_task_with_context()
    # - _calculate_readiness_score()
    # - _calculate_relevance_score()
    # - _generate_unblock_recommendation()
```

**Design Pattern:**
- Mixin provides protected methods (_prefix) for subclass use
- Each domain service uses these to implement *_for_user() methods
- UserContext provides the ~240 fields for enrichment

**Entity Type Dispatch (November 28, 2025):**

The `_build_contextual_dependencies()` method uses dictionary dispatch
based on the `entity_type` property instead of isinstance() chains:

```python
# Dictionary dispatch by entity_type property
type_categorizers = {
    "knowledge": knowledge_reqs,
    "task": task_reqs,
    "habit": habit_reqs,
}

for entity in enriched:
    if entity.entity_type in type_categorizers:
        type_categorizers[entity.entity_type].append(entity)
```

This pattern is extensible (add new types by adding dict entries) and
aligns with the entity_type discriminator in ContextualEntity subclasses.
"""

from __future__ import annotations

from abc import ABC
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.models.context_types import (
    ContextualDependencies,
    ContextualEntity,
    ContextualGoal,
    ContextualHabit,
    ContextualKnowledge,
    ContextualTask,
    _compute_blocking_reasons,
    _compute_readiness,
    _compute_relevance,
    _compute_urgency,
)
from core.models.enums.entity_enums import EntityType

if TYPE_CHECKING:
    import logging

    from core.services.user.unified_user_context import UserContext


def _get_attr(obj: Any, attr: str, default: Any = None) -> Any:
    """
    Extract attribute from object or dict.

    Provides type-safe attribute extraction without hasattr().
    Uses isinstance(obj, dict) to determine access pattern.

    Args:
        obj: Domain model object or dict
        attr: Attribute/key name to extract
        default: Default value if not found

    Returns:
        Attribute value or default
    """
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


class ContextFirstMixin(ABC):
    """
    Mixin providing context-aware enrichment for relationship services.

    **Methods Provided:**

    Score Calculation:
    - _calculate_readiness_score(): Based on prerequisites met
    - _calculate_relevance_score(): Based on goal alignment
    - _calculate_urgency_score(): Based on deadlines, streaks at risk
    - _calculate_priority_score(): Combined weighted score

    Enrichment:
    - _enrich_task_with_context(): Task -> ContextualTask
    - _enrich_knowledge_with_context(): KU -> ContextualKnowledge
    - _enrich_goal_with_context(): Goal -> ContextualGoal
    - _enrich_habit_with_context(): Habit -> ContextualHabit

    Insights:
    - _identify_blocking_reasons(): What's preventing engagement?
    - _identify_unlocks(): What does completing this enable?
    - _generate_unblock_recommendation(): Most impactful action

    **Usage:**
    Subclasses call these methods in their *_for_user() implementations:

    ```python
    async def get_task_dependencies_for_user(
        self,
        task_uid: str,
        context: UserContext,
    ) -> Result[ContextualDependencies]:
        # Get raw dependencies
        raw_deps = await self.get_task_dependencies(task_uid)

        # Enrich each with context
        enriched = []
        for dep in raw_deps.value:
            contextual = await self._enrich_task_with_context(dep, context)
            enriched.append(contextual)

        # Categorize and return
        return Result.ok(
            self._build_contextual_dependencies(
                entity_uid=task_uid,
                entity_type="Task",
                enriched=enriched,
                context=context,
            )
        )
    ```
    """

    # Subclasses must have a logger
    logger: logging.Logger

    # ==========================================================================
    # SCORE CALCULATION METHODS
    # ==========================================================================

    def _calculate_readiness_score(
        self,
        required_knowledge_uids: list[str],
        required_task_uids: list[str],
        context: UserContext,
        mastery_threshold: float = 0.7,
    ) -> float:
        """Calculate readiness score. Delegates to module-level scoring engine."""
        return _compute_readiness(
            required_knowledge_uids,
            required_task_uids,
            context.knowledge_mastery,
            context.completed_task_uids,
            mastery_threshold,
        )

    def _calculate_relevance_score(
        self,
        entity_goal_uids: list[str],
        entity_principle_uids: list[str],
        context: UserContext,
    ) -> float:
        """Calculate relevance score. Delegates to module-level scoring engine."""
        return _compute_relevance(
            entity_goal_uids,
            entity_principle_uids,
            context.active_goal_uids,
            context.primary_goal_focus,
            context.core_principle_uids,
            context.principle_priorities,
        )

    def _calculate_urgency_score(
        self,
        deadline: date | None,
        is_at_risk: bool,
        streak_at_risk: bool,
        context: UserContext,
    ) -> float:
        """Calculate urgency score. Delegates to module-level scoring engine."""
        return _compute_urgency(deadline, is_at_risk, streak_at_risk)

    def _calculate_priority_score(
        self,
        readiness: float,
        relevance: float,
        urgency: float,
        weights: tuple[float, float, float] = (0.4, 0.4, 0.2),
    ) -> float:
        """Calculate combined priority score. Delegates to module-level scoring engine."""
        from core.models.context_types import _compute_priority

        return _compute_priority((readiness, relevance, urgency), weights)

    # ==========================================================================
    # ENRICHMENT METHODS
    # ==========================================================================

    async def _enrich_task_with_context(
        self,
        task: Any,
        context: UserContext,
        goal_uids: list[str] | None = None,
        knowledge_uids: list[str] | None = None,
        prerequisite_knowledge: list[str] | None = None,
        prerequisite_tasks: list[str] | None = None,
    ) -> ContextualTask:
        """Enrich a task with user context. Delegates to factory classmethod."""
        uid = _get_attr(task, "uid", "")
        title = _get_attr(task, "title", "")
        deadline = _get_attr(task, "due_date")

        return ContextualTask.from_entity_and_context(
            uid=uid,
            title=title,
            context=context,
            goal_uids=goal_uids,
            knowledge_uids=knowledge_uids,
            prerequisite_knowledge=prerequisite_knowledge,
            prerequisite_tasks=prerequisite_tasks,
            deadline=deadline,
        )

    async def _enrich_knowledge_with_context(
        self,
        knowledge: Any,
        context: UserContext,
        prerequisite_uids: list[str] | None = None,
        application_task_uids: list[str] | None = None,
    ) -> ContextualKnowledge:
        """Enrich a knowledge unit with user context. Delegates to factory classmethod."""
        uid = _get_attr(knowledge, "uid", "")
        title = _get_attr(knowledge, "title", "")

        return ContextualKnowledge.from_entity_and_context(
            uid=uid,
            title=title,
            context=context,
            prerequisite_uids=prerequisite_uids,
            application_task_uids=application_task_uids,
        )

    async def _enrich_goal_with_context(
        self,
        goal: Any,
        context: UserContext,
        contributing_task_uids: list[str] | None = None,
        contributing_habit_uids: list[str] | None = None,
        required_knowledge_uids: list[str] | None = None,
    ) -> ContextualGoal:
        """Enrich a goal with user context. Delegates to factory classmethod."""
        uid = _get_attr(goal, "uid", "")
        title = _get_attr(goal, "title", "")

        return ContextualGoal.from_entity_and_context(
            uid=uid,
            title=title,
            context=context,
            contributing_task_uids=contributing_task_uids,
            contributing_habit_uids=contributing_habit_uids,
            required_knowledge_uids=required_knowledge_uids,
        )

    async def _enrich_habit_with_context(
        self,
        habit: Any,
        context: UserContext,
        supported_goal_uids: list[str] | None = None,
        applied_knowledge_uids: list[str] | None = None,
    ) -> ContextualHabit:
        """Enrich a habit with user context. Delegates to factory classmethod."""
        uid = _get_attr(habit, "uid", "")
        title = _get_attr(habit, "title", "")
        return ContextualHabit.from_entity_and_context(
            uid=uid,
            title=title,
            context=context,
            supported_goal_uids=supported_goal_uids,
            applied_knowledge_uids=applied_knowledge_uids,
        )

    # ==========================================================================
    # INSIGHT METHODS
    # ==========================================================================

    def _identify_blocking_reasons(
        self,
        required_knowledge: list[str],
        required_tasks: list[str],
        context: UserContext,
        max_reasons: int = 3,
    ) -> list[str]:
        """Identify reasons blocking engagement. Delegates to module-level scoring engine."""
        return _compute_blocking_reasons(
            required_knowledge,
            required_tasks,
            context.knowledge_mastery,
            context.completed_task_uids,
            max_reasons,
        )

    def _identify_unlocks(
        self,
        entity_uid: str,
        entity_type: str,
        context: UserContext,
    ) -> list[str]:
        """
        Identify what completing this entity unlocks.

        Note: This is a simplified version. Full implementation would
        query the graph for dependent entities.

        Returns:
            List of UIDs that would be unblocked
        """
        unlocks = []

        if entity_type == EntityType.TASK.value:
            # Check if any blocked tasks depend on this one
            for _blocked_uid in context.blocked_task_uids:
                # Would need graph query to verify dependency
                # For now, return empty - implemented in relationship service
                pass

        elif entity_type == EntityType.KU.value:
            # Check context for entities waiting on this knowledge
            # Would need graph query
            pass

        return unlocks

    def _generate_unblock_recommendation(
        self,
        blocked_entities: list[ContextualEntity],
        context: UserContext,
    ) -> str:
        """
        Generate actionable recommendation for unblocking progress.

        Args:
            blocked_entities: List of blocked contextual entities
            context: User's complete context

        Returns:
            Actionable recommendation string
        """
        if not blocked_entities:
            return "All items are ready - proceed with highest priority!"

        # Find highest-impact blocker (most relevant)
        from core.utils.sort_functions import get_relevance_score

        highest = max(blocked_entities, key=get_relevance_score)

        # Generate recommendation based on blocking reason
        if highest.learning_gaps:
            gap = highest.learning_gaps[0]
            return f"Learn '{gap}' to unblock '{highest.title}'"

        if highest.blocking_reasons:
            reason = highest.blocking_reasons[0]
            return f"Resolve: {reason}"

        return f"Complete prerequisites for '{highest.title}'"

    # ==========================================================================
    # AGGREGATE BUILDERS
    # ==========================================================================

    def _build_contextual_dependencies(
        self,
        entity_uid: str,
        entity_type: str,
        enriched: list[ContextualEntity],
        context: UserContext,
    ) -> ContextualDependencies:
        """
        Build a ContextualDependencies aggregate from enriched entities.

        Args:
            entity_uid: Source entity UID
            entity_type: Source entity type ("Task", "Goal", etc.)
            enriched: List of enriched contextual entities
            context: User's complete context

        Returns:
            ContextualDependencies aggregate
        """
        ready = []
        blocked = []
        knowledge_reqs: list[ContextualKnowledge] = []
        task_reqs: list[ContextualTask] = []
        habit_reqs: list[ContextualHabit] = []

        # Dictionary dispatch by entity_type property
        type_categorizers: dict[str, list] = {
            "knowledge": knowledge_reqs,
            "task": task_reqs,
            "habit": habit_reqs,
        }

        for entity in enriched:
            # Categorize by readiness
            if entity.is_ready():
                ready.append(entity)
            else:
                blocked.append(entity)

            # Categorize by type using entity_type property
            if entity.entity_type in type_categorizers:
                type_categorizers[entity.entity_type].append(entity)

        # Sort by priority
        from core.utils.sort_functions import get_priority_score, get_relevance_score

        ready.sort(key=get_priority_score, reverse=True)
        blocked.sort(key=get_relevance_score, reverse=True)

        # Generate recommendation
        recommendation = self._generate_unblock_recommendation(blocked, context)

        # Find highest priority blocker
        highest_blocker = blocked[0].uid if blocked else None

        # Estimate unblock time (simplified: 30 min per blocker)
        estimated_time = len(blocked) * 30

        # Build learning path suggestion (knowledge gaps first)
        learning_path = [k.uid for k in knowledge_reqs if not k.prerequisites_met][:5]

        return ContextualDependencies(
            entity_uid=entity_uid,
            entity_type=entity_type,
            ready_dependencies=tuple(ready),
            blocked_dependencies=tuple(blocked),
            knowledge_requirements=tuple(knowledge_reqs),
            task_requirements=tuple(task_reqs),
            habit_requirements=tuple(habit_reqs),
            total_blocking_items=len(blocked),
            estimated_unblock_time_minutes=estimated_time,
            highest_priority_blocker=highest_blocker,
            recommended_next_action=recommendation,
            learning_path_suggestion=tuple(learning_path),
        )

    # =============================================================================
    # ENTITY RETRIEVAL FROM RICH CONTEXT (November 26, 2025)
    # =============================================================================
    #
    # These methods provide standardized access to entities from UserContext
    # rich fields, avoiding unnecessary Neo4j queries when data is already available.
    #
    # **Pattern:** Check rich context first, fall back to Neo4j query only if needed.
    #
    # **Configuration:**
    # Each domain service should configure these via _configure_rich_context()
    # in __init__:
    #
    # ```python
    # def __init__(self, backend, ...):
    #     self._configure_rich_context(
    #         domain_name="Choice",
    #         rich_field_name="recent_choices_rich",
    #         entity_key="choice",
    #     )
    # ```
    #
    # **Domain Mappings:**
    # - Tasks: active_tasks_rich, "task"
    # - Goals: active_goals_rich, "goal"
    # - Habits: active_habits_rich, "habit"
    # - Events: active_events_rich, "event"
    # - Choices: recent_choices_rich, "choice"
    # - Principles: core_principles_rich, "principle"
    # - KU: knowledge_units_rich, "ku" (dict format)
    # - LS: active_learning_steps_rich, "step"
    # - LP: enrolled_paths_rich, "path"
    # =============================================================================

    # Configuration attributes for rich context access
    _rc_domain_name: str = ""
    _rc_rich_field_name: str = ""
    _rc_entity_key: str = ""
    _rc_is_dict_format: bool = False  # True for knowledge_units_rich

    def _configure_rich_context(
        self,
        domain_name: str,
        rich_field_name: str,
        entity_key: str,
        is_dict_format: bool = False,
    ) -> None:
        """
        Configure rich context access for this domain.

        Call this in __init__ of your service:
        ```python
        def __init__(self, backend, ...):
            self._configure_rich_context(
                domain_name="Choice",
                rich_field_name="recent_choices_rich",
                entity_key="choice",
            )
        ```

        Args:
            domain_name: Human-readable name for logging (e.g., "Choice", "Task")
            rich_field_name: UserContext field containing rich data
            entity_key: Key in rich data dict for entity properties
            is_dict_format: True if rich field is dict (knowledge_units_rich)
        """
        self._rc_domain_name = domain_name
        self._rc_rich_field_name = rich_field_name
        self._rc_entity_key = entity_key
        self._rc_is_dict_format = is_dict_format

    def _get_entity_dict_from_rich_context(
        self, uid: str, context: UserContext
    ) -> dict[str, Any] | None:
        """
        Get entity dictionary from UserContext rich data.

        Returns the raw dict from MEGA-QUERY - use domain-specific _dict_to_X()
        method to convert to domain model if needed.

        Args:
            uid: Entity identifier
            context: User's context (may contain rich data)

        Returns:
            Dict with entity properties if found, None otherwise

        Example:
            ```python
            entity_dict = self._get_entity_dict_from_rich_context(uid, context)
            if entity_dict:
                entity = self._dict_to_choice(entity_dict)
            else:
                entity = await self.backend.get_choice(uid)
            ```
        """
        if not self._rc_rich_field_name:
            return None

        rich_data = getattr(context, self._rc_rich_field_name, None)
        if not rich_data:
            return None

        if self._rc_is_dict_format:
            # Dict format: {uid: {ku: {...}, graph_context: {...}}}
            entity_data = rich_data.get(uid)
            if entity_data:
                return entity_data.get(self._rc_entity_key, {})
            return None
        else:
            # List format: [{task: {...}, graph_context: {...}}, ...]
            for item in rich_data:
                entity_dict = item.get(self._rc_entity_key, {})
                if entity_dict.get("uid") == uid:
                    return entity_dict
            return None

    def _get_graph_context_from_rich(self, uid: str, context: UserContext) -> dict[str, Any] | None:
        """
        Get graph context (relationships) from UserContext rich data.

        Args:
            uid: Entity identifier
            context: User's context

        Returns:
            Dict with graph_context if found, None otherwise

        Example:
            ```python
            graph_ctx = self._get_graph_context_from_rich(uid, context)
            if graph_ctx:
                related_uids = extract_uids_from_graph_context(
                    graph_ctx, "aligned_principles"
                )
            ```
        """
        if not self._rc_rich_field_name:
            return None

        rich_data = getattr(context, self._rc_rich_field_name, None)
        if not rich_data:
            return None

        if self._rc_is_dict_format:
            # Dict format
            entity_data = rich_data.get(uid)
            if entity_data:
                return entity_data.get("graph_context", {})
            return None
        else:
            # List format
            for item in rich_data:
                entity_dict = item.get(self._rc_entity_key, {})
                if entity_dict.get("uid") == uid:
                    return item.get("graph_context", {})
            return None

    def _log_rich_context_hit(self, uid: str, hit: bool, operation: str = "") -> None:
        """Log whether entity was found in rich context."""
        if hit:
            self.logger.debug(
                f"{self._rc_domain_name} {uid} found in rich context "
                f"(no Neo4j query needed){' for ' + operation if operation else ''}"
            )
        else:
            self.logger.debug(
                f"{self._rc_domain_name} {uid} not in rich context, "
                f"querying Neo4j{' for ' + operation if operation else ''}"
            )

    def _log_rich_context_efficiency(self, uid: str, operation: str) -> None:
        """Log context efficiency for an operation."""
        self.logger.info(
            f"Context-first: {self._rc_domain_name} {uid} {operation} "
            "used rich context (saved queries)"
        )


# =============================================================================
# STANDARDIZED PARSING HELPERS
# =============================================================================


def parse_date_field(value: Any) -> date | None:
    """
    Parse a date value from Neo4j (string, date, or Neo4j date object).

    Args:
        value: Date value in various formats

    Returns:
        Python date object or None
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    # Neo4j date objects — detect via module name (no import needed)
    if getattr(type(value), "__module__", "") == "neo4j.time":
        return date(value.year, value.month, value.day)
    return None


def parse_datetime_field(value: Any) -> datetime | None:
    """
    Parse a datetime value from Neo4j.

    Args:
        value: Datetime value in various formats

    Returns:
        Python datetime object or None
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    # Neo4j datetime objects — detect via module name (no import needed)
    if getattr(type(value), "__module__", "") == "neo4j.time":
        return datetime(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            getattr(value, "nanosecond", 0) // 1000,  # Convert nanoseconds to microseconds
        )
    return None


def parse_enum_field(value: Any, enum_class: type, default: Any = None) -> Any:
    """
    Parse an enum value from Neo4j (string or enum).

    Args:
        value: Enum value (string or enum instance)
        enum_class: The enum class to convert to
        default: Default value if parsing fails

    Returns:
        Enum instance or default
    """
    if value is None:
        return default
    if isinstance(value, enum_class):
        return value
    if isinstance(value, str):
        try:
            return enum_class(value)
        except ValueError:
            return default
    return default


def extract_uids_from_graph_context(
    graph_ctx: dict[str, Any], key: str, uid_field: str = "uid"
) -> list[str]:
    """
    Extract UIDs from a graph context relationship list.

    Args:
        graph_ctx: Graph context dict
        key: Key in graph_ctx containing list of dicts
        uid_field: Field name containing UID in each dict

    Returns:
        List of UIDs

    Example:
        ```python
        graph_ctx = {
            "supporting_habits": [{"uid": "h1"}, {"uid": "h2"}],
            "required_knowledge": [{"uid": "ku1"}],
        }
        uids = extract_uids_from_graph_context(graph_ctx, "supporting_habits")
        # Returns: ["h1", "h2"]
        ```
    """
    items = graph_ctx.get(key, [])
    return [item.get(uid_field) for item in items if item and item.get(uid_field)]


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "ContextFirstMixin",
    "extract_uids_from_graph_context",
    "parse_date_field",
    "parse_datetime_field",
    "parse_enum_field",
]
