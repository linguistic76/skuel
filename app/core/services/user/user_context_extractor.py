"""
User Context Extractor - Parse Query Results into Structured Data
=================================================================

**EXTRACTED (December 2025):** From user_context_builder.py for separation of concerns.

This module contains:
- Data classes for typed extraction results
- UserContextExtractor class for parsing MEGA-QUERY results

Architecture:
- Pure data extraction, no database queries
- Converts raw query results into typed structures
- Used by UserContextBuilder after query execution
"""

from dataclasses import dataclass, field
from typing import Any

from core.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# DATA CLASSES - Typed extraction results
# =============================================================================


@dataclass
class TaskRelationshipData:
    """Extracted task relationship data from MEGA-QUERY."""

    dependencies: dict[str, list[str]] = field(default_factory=dict)
    blockers: dict[str, list[str]] = field(default_factory=dict)
    knowledge_applied: dict[str, list[str]] = field(default_factory=dict)
    goal_associations: dict[str, str] = field(default_factory=dict)


@dataclass
class GoalRelationshipData:
    """Extracted goal relationship data from MEGA-QUERY."""

    knowledge_required: dict[str, list[str]] = field(default_factory=dict)
    knowledge_mastered: dict[str, list[str]] = field(default_factory=dict)
    completion_from_graph: dict[str, float] = field(default_factory=dict)
    supporting_tasks: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class HabitRelationshipData:
    """Extracted habit relationship data from MEGA-QUERY."""

    knowledge_applied: dict[str, list[str]] = field(default_factory=dict)
    prerequisites: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class KnowledgeRelationshipData:
    """Extracted knowledge relationship data from MEGA-QUERY."""

    prerequisite_counts: dict[str, int] = field(default_factory=dict)
    ready_to_learn_uids: set[str] = field(default_factory=set)


@dataclass
class GraphSourcedData:
    """
    Complete graph-sourced relationship data extracted from MEGA-QUERY.

    This replaces 4 separate database round-trips with pure Python extraction.
    The MEGA-QUERY already fetches all this data in graph_context fields.
    """

    tasks: TaskRelationshipData = field(default_factory=TaskRelationshipData)
    goals: GoalRelationshipData = field(default_factory=GoalRelationshipData)
    habits: HabitRelationshipData = field(default_factory=HabitRelationshipData)
    knowledge: KnowledgeRelationshipData = field(default_factory=KnowledgeRelationshipData)


# =============================================================================
# EXTRACTOR CLASS
# =============================================================================


class UserContextExtractor:
    """
    Extract relationship data from MEGA-QUERY rich results.

    **OPTIMIZATION (December 2025):**
    Replaces 4 separate database round-trips with pure Python extraction.
    The MEGA-QUERY already fetches all this data in graph_context fields.

    Before: 5 database round-trips (1 MEGA-QUERY + 4 graph-sourced queries)
    After:  1 database round-trip (MEGA-QUERY only)

    Philosophy: "The data is already here - extract, don't re-query"

    **MEGA-QUERY Result Shapes (January 2026):**
    Tasks/Goals/Habits use: {"entity": {...}, "graph_context": {...}}
    Knowledge uses: {"uid": "...", "graph_context": {...}} (direct UID, no nesting)
    """

    # Track domains with shape warnings (log once per domain per session)
    _shape_warnings_logged: set[str] = set()

    def _as_list(self, value: Any, domain: str) -> list[dict[str, Any]]:
        """
        Validate and coerce value to list of dicts.

        Shape guard that prevents silent corruption from query shape mismatches.
        Logs a warning once per domain if the shape is unexpected.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            if domain not in self._shape_warnings_logged:
                logger.warning(
                    f"Expected list for {domain}, got {type(value).__name__}. "
                    "Check MEGA-QUERY shape."
                )
                self._shape_warnings_logged.add(domain)
            return []
        return value

    def _uids(self, items: list[dict[str, Any]] | None, *, dedupe: bool = True) -> list[str]:
        """
        Extract UIDs from list of dicts, with optional deduplication.

        Preserves order while removing duplicates (if dedupe=True).
        Handles None/empty gracefully.
        """
        if not items:
            return []
        raw = [i["uid"] for i in items if isinstance(i, dict) and i.get("uid")]
        if dedupe:
            # Preserve order, remove duplicates
            return list(dict.fromkeys(raw))
        return raw

    def extract_graph_sourced_data(
        self, mega_data: dict[str, Any], mastered_uids: set[str]
    ) -> GraphSourcedData:
        """
        Extract all graph-sourced relationship data from MEGA-QUERY results.

        Args:
            mega_data: Raw MEGA-QUERY results with "uids" and "rich" keys
            mastered_uids: Set of mastered knowledge UIDs (for computing goal mastery)

        Returns:
            GraphSourcedData with all relationship data extracted
        """
        rich_data = mega_data.get("rich", {})

        # Use shape guards to validate and coerce each domain's data
        tasks_data = self._as_list(rich_data.get("tasks"), "tasks")
        goals_data = self._as_list(rich_data.get("goals"), "goals")
        habits_data = self._as_list(rich_data.get("habits"), "habits")
        knowledge_data = self._as_list(rich_data.get("knowledge"), "knowledge")

        return GraphSourcedData(
            tasks=self.extract_task_relationships(tasks_data),
            goals=self.extract_goal_relationships(goals_data, mastered_uids),
            habits=self.extract_habit_relationships(habits_data),
            knowledge=self.extract_knowledge_relationships(knowledge_data, mastered_uids),
        )

    def extract_task_relationships(self, tasks_rich: list[dict[str, Any]]) -> TaskRelationshipData:
        """
        Extract task relationship data from tasks_rich[].graph_context.

        Extracts:
        - Task dependencies (DEPENDS_ON relationships)
        - Task blockers (inverse of dependencies, deduplicated)
        - Applied knowledge (APPLIES_KNOWLEDGE relationships)
        - Goal associations (FULFILLS_GOAL relationships)

        Args:
            tasks_rich: List of task items with graph_context
                       Shape: [{"task": {...}, "graph_context": {...}}, ...]

        Returns:
            TaskRelationshipData with all task relationships
        """
        dependencies: dict[str, list[str]] = {}
        blockers_sets: dict[str, set[str]] = {}  # Use sets to prevent duplicates
        knowledge_applied: dict[str, list[str]] = {}
        goal_associations: dict[str, str] = {}

        for task_item in tasks_rich:
            if not task_item:
                continue

            task_data = task_item.get("task", {})
            graph_ctx = task_item.get("graph_context", {})
            task_uid = task_data.get("uid")

            if not task_uid:
                continue

            # Extract dependencies (deduplicated)
            dep_uids = self._uids(graph_ctx.get("dependencies"))
            if dep_uids:
                dependencies[task_uid] = dep_uids
                # Build inverse mapping: if task A depends on B, then B blocks A
                for dep_uid in dep_uids:
                    blockers_sets.setdefault(dep_uid, set()).add(task_uid)

            # Extract applied knowledge (deduplicated)
            ku_uids = self._uids(graph_ctx.get("applied_knowledge"))
            if ku_uids:
                knowledge_applied[task_uid] = ku_uids

            # Extract goal association
            goal_ctx = graph_ctx.get("goal_context")
            if goal_ctx and goal_ctx.get("uid"):
                goal_associations[task_uid] = goal_ctx["uid"]

        # Convert blocker sets to sorted lists for stable output
        blockers = {k: sorted(v) for k, v in blockers_sets.items()}

        return TaskRelationshipData(
            dependencies=dependencies,
            blockers=blockers,
            knowledge_applied=knowledge_applied,
            goal_associations=goal_associations,
        )

    def extract_goal_relationships(
        self, goals_rich: list[dict[str, Any]], mastered_uids: set[str]
    ) -> GoalRelationshipData:
        """
        Extract goal relationship data from goals_rich[].graph_context.

        Extracts:
        - Required knowledge (REQUIRES_KNOWLEDGE relationships)
        - Mastered knowledge (subset of required that user has mastered)
        - Completion percentage (computed from graph state)
        - Supporting tasks (FULFILLS_GOAL relationships)

        Args:
            goals_rich: List of goal items with graph_context
                       Shape: [{"goal": {...}, "graph_context": {...}}, ...]
            mastered_uids: Set of UIDs the user has mastered

        Returns:
            GoalRelationshipData with all goal relationships

        Note:
            completion_from_graph is only set for goals with required knowledge.
            Goals with no requirements have no entry (not 1.0 or 0.0).
            Downstream consumers should treat missing keys as "no knowledge requirements".
        """
        knowledge_required: dict[str, list[str]] = {}
        knowledge_mastered: dict[str, list[str]] = {}
        completion_from_graph: dict[str, float] = {}
        supporting_tasks: dict[str, list[str]] = {}

        for goal_item in goals_rich:
            if not goal_item:
                continue

            goal_data = goal_item.get("goal", {})
            graph_ctx = goal_item.get("graph_context", {})
            goal_uid = goal_data.get("uid")

            if not goal_uid:
                continue

            # Extract required knowledge (deduplicated)
            req_uids = self._uids(graph_ctx.get("required_knowledge"))
            if req_uids:
                knowledge_required[goal_uid] = req_uids
                # Compute which required knowledge is already mastered
                mastered_for_goal = [uid for uid in req_uids if uid in mastered_uids]
                if mastered_for_goal:
                    knowledge_mastered[goal_uid] = mastered_for_goal
                # Compute completion percentage from graph state
                completion_from_graph[goal_uid] = len(mastered_for_goal) / len(req_uids)

            # Extract supporting tasks (deduplicated)
            task_uids = self._uids(graph_ctx.get("contributing_tasks"))
            if task_uids:
                supporting_tasks[goal_uid] = task_uids

        return GoalRelationshipData(
            knowledge_required=knowledge_required,
            knowledge_mastered=knowledge_mastered,
            completion_from_graph=completion_from_graph,
            supporting_tasks=supporting_tasks,
        )

    def extract_habit_relationships(
        self, habits_rich: list[dict[str, Any]]
    ) -> HabitRelationshipData:
        """
        Extract habit relationship data from habits_rich[].graph_context.

        Extracts:
        - Applied knowledge (APPLIES_KNOWLEDGE/REINFORCES_KNOWLEDGE relationships)
        - Prerequisite habits (ENABLES_HABIT/PREREQUISITE_FOR relationships)

        Args:
            habits_rich: List of habit items with graph_context
                        Shape: [{"habit": {...}, "graph_context": {...}}, ...]

        Returns:
            HabitRelationshipData with all habit relationships
        """
        knowledge_applied: dict[str, list[str]] = {}
        prerequisites: dict[str, list[str]] = {}

        for habit_item in habits_rich:
            if not habit_item:
                continue

            habit_data = habit_item.get("habit", {})
            graph_ctx = habit_item.get("graph_context", {})
            habit_uid = habit_data.get("uid")

            if not habit_uid:
                continue

            # Extract applied knowledge (deduplicated)
            ku_uids = self._uids(graph_ctx.get("applied_knowledge"))
            if ku_uids:
                knowledge_applied[habit_uid] = ku_uids

            # Extract prerequisite habits (deduplicated)
            prereq_uids = self._uids(graph_ctx.get("prerequisites"))
            if prereq_uids:
                prerequisites[habit_uid] = prereq_uids

        return HabitRelationshipData(
            knowledge_applied=knowledge_applied,
            prerequisites=prerequisites,
        )

    def extract_knowledge_relationships(
        self, knowledge_rich: list[dict[str, Any]], mastered_uids: set[str]
    ) -> KnowledgeRelationshipData:
        """
        Extract knowledge relationship data from knowledge_rich[].graph_context.

        Extracts:
        - Prerequisite counts (number of prerequisites per KU)
        - Ready-to-learn UIDs (KUs where all prerequisites are mastered)

        Args:
            knowledge_rich: List of knowledge items with graph_context
                           Shape: [{"uid": "...", "graph_context": {...}}, ...]
                           NOTE: Knowledge items use direct UID (not nested like tasks/goals/habits)
            mastered_uids: Set of UIDs the user has mastered

        Returns:
            KnowledgeRelationshipData with prerequisite counts and ready-to-learn

        Note:
            Ready-to-learn computation distinguishes between:
            - "no prerequisites" (true leaf node - ready if not mastered)
            - "missing graph_context" (data issue - excluded with warning)
        """
        prerequisite_counts: dict[str, int] = {}
        ready_to_learn_uids: set[str] = set()

        # Build prerequisite map for ready-to-learn computation
        # Track KUs with valid graph_context vs those missing it
        ku_prerequisites: dict[str, set[str]] = {}
        kus_with_valid_context: set[str] = set()
        missing_context_logged = False

        for ku_item in knowledge_rich:
            if not ku_item:
                continue

            ku_uid = ku_item.get("uid")
            if not ku_uid:
                continue

            graph_ctx = ku_item.get("graph_context")

            # Guard: distinguish "no graph_context" (data issue) from "no prerequisites" (valid)
            if graph_ctx is None:
                if not missing_context_logged:
                    logger.warning(
                        "Knowledge item missing graph_context - excluding from ready-to-learn. "
                        "Check MEGA-QUERY shape for knowledge domain."
                    )
                    missing_context_logged = True
                continue

            kus_with_valid_context.add(ku_uid)

            # Count prerequisites (deduplicated)
            prereq_uids = set(self._uids(graph_ctx.get("prerequisites")))
            prerequisite_counts[ku_uid] = len(prereq_uids)
            ku_prerequisites[ku_uid] = prereq_uids

        # Compute ready-to-learn UIDs:
        # KUs not yet mastered where all prerequisites ARE mastered
        # Only consider KUs with valid graph_context
        for ku_uid in kus_with_valid_context:
            if ku_uid in mastered_uids:
                continue  # Already mastered, not "ready to learn"
            prereqs = ku_prerequisites.get(ku_uid, set())
            # Ready if: no prereqs (true leaf) OR all prereqs mastered
            if not prereqs or prereqs.issubset(mastered_uids):
                ready_to_learn_uids.add(ku_uid)

        return KnowledgeRelationshipData(
            prerequisite_counts=prerequisite_counts,
            ready_to_learn_uids=ready_to_learn_uids,
        )
