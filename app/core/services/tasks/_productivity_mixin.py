"""
Productivity Mixin — TasksIntelligenceService
=============================================

Analytics engine methods: learning patterns, knowledge-aware priorities,
task insights, mastery progression.

Part of tasks_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.constants import QueryLimit
from core.models.enums import EntityStatus
from core.models.task.task import Task
from core.services.tasks.task_relationships import TaskRelationships
from core.services.tasks_types import KnowledgePatternAnalysis
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.type_hints import UserUID
    from core.ports.domain_protocols import TasksOperations


class _ProductivityMixin:
    """
    Analytics engine methods for TasksIntelligenceService.

    Delegates to TaskKnowledgeAnalyzer for pattern detection, priority calculation,
    insight generation, and mastery tracking.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by TasksIntelligenceService.__init__
    backend: "TasksOperations"
    logger: Any
    _knowledge_analyzer: Any
    relationships: Any

    async def analyze_learning_patterns(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        """
        Analyze learning patterns across user's task activities.

        Args:
            user_uid: User to analyze
            timeframe_days: Analysis timeframe in days

        Returns:
            Result containing detected learning patterns
        """
        tasks_result = await self.backend.find_by(user_uid=user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result)

        return await self._knowledge_analyzer.analyze_learning_patterns(
            tasks_result.value, timeframe_days
        )

    async def calculate_knowledge_aware_priorities(
        self, user_uid: UserUID, task_uids: list[str] | None = None
    ) -> Result[list[Any]]:
        """
        Calculate knowledge-aware priority scores for tasks.

        Args:
            user_uid: User whose tasks to prioritize
            task_uids: Specific task UIDs to prioritize (None for all)

        Returns:
            Result containing knowledge-aware priority scores
        """
        import asyncio
        from operator import attrgetter

        from core.services.tasks.task_relationships import TaskRelationships

        tasks_result = await self.backend.find_by(user_uid=user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result)

        all_tasks = tasks_result.value

        if task_uids:
            tasks_to_prioritize = [t for t in all_tasks if t.uid in task_uids]
        else:
            tasks_to_prioritize = [
                t
                for t in all_tasks
                if t.status in [EntityStatus.DRAFT, EntityStatus.ACTIVE, EntityStatus.SCHEDULED]
            ]

        patterns_result = await self.analyze_learning_patterns(user_uid)
        patterns = patterns_result.value if patterns_result.is_ok else []

        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationships) for task in all_tasks]
        )

        all_knowledge_uids: set[str] = set()
        for task, _rels in zip(all_tasks, rels_list, strict=False):
            all_knowledge_uids.update(task.get_combined_knowledge_uids())

        mastery_result = await self._knowledge_analyzer.track_knowledge_mastery_progression(
            all_tasks, list(all_knowledge_uids)
        )
        mastery_progressions = mastery_result.value if mastery_result.is_ok else {}

        # One sel_category batch for the whole task set — the per-task scorer
        # would otherwise issue one lookup per task (Codex P2 #1054). Union of
        # the same uid tiers the scorer reads (applies + inferred).
        linked_uids: set[str] = set()
        for rels in rels_list:
            linked_uids.update(rels.applies_knowledge_uids)
            linked_uids.update(rels.inferred_knowledge_uids)
        ku_categories = await self._knowledge_analyzer.resolve_ku_categories(list(linked_uids))

        priorities = []
        for task in tasks_to_prioritize:
            priority_result = await self._knowledge_analyzer.calculate_knowledge_aware_priority(
                task, mastery_progressions, patterns, ku_categories=ku_categories
            )
            if priority_result.is_ok:
                priorities.append(priority_result.value)

        priorities.sort(key=attrgetter("final_priority_score"), reverse=True)
        return Result.ok(priorities)

    async def generate_task_insights(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        """
        Generate insights from user's completed tasks.

        Args:
            user_uid: User to analyze
            timeframe_days: Analysis timeframe in days

        Returns:
            Result containing generated task insights
        """
        tasks_result = await self.backend.find_by(user_uid=user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result)

        cutoff_date = date.today() - timedelta(days=timeframe_days)
        completed_tasks = [
            task
            for task in tasks_result.value
            if task.status == EntityStatus.COMPLETED
            and task.completion_date
            and task.completion_date >= cutoff_date
        ]

        patterns_result = await self.analyze_learning_patterns(user_uid, timeframe_days)
        patterns = patterns_result.value if patterns_result.is_ok else []

        return await self._knowledge_analyzer.generate_task_insights(completed_tasks, patterns)

    async def track_knowledge_mastery_progression(
        self, user_uid: UserUID, knowledge_uids: list[str] | None = None
    ) -> Result[dict[str, Any]]:
        """
        Track knowledge mastery progression for user.

        Args:
            user_uid: User to analyze
            knowledge_uids: Specific knowledge UIDs to track (None for all)

        Returns:
            Result containing mastery progressions by knowledge UID
        """
        import asyncio

        from core.services.tasks.task_relationships import TaskRelationships

        tasks_result = await self.backend.find_by(user_uid=user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result)

        all_tasks = tasks_result.value

        if knowledge_uids is None:
            rels_list = await asyncio.gather(
                *[TaskRelationships.fetch(task.uid, self.relationships) for task in all_tasks]
            )
            all_knowledge_uids: set[str] = set()
            for task, _rels in zip(all_tasks, rels_list, strict=False):
                all_knowledge_uids.update(task.get_combined_knowledge_uids())
            knowledge_uids = list(all_knowledge_uids)

        return await self._knowledge_analyzer.track_knowledge_mastery_progression(
            all_tasks, knowledge_uids
        )

    async def analyze_task_learning_metrics(
        self, _filters: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        Analyze learning metrics from tasks using Task model capabilities.

        Scores each task for knowledge complexity, learning impact, bridge-task
        detection, and mastery validation. Different from
        get_learning_opportunities() which uses graph intelligence for discovery;
        this is per-task scoring, sorted by learning impact.

        GRAPH-NATIVE: Fetches relationship data for tasks that have learning
        opportunities before calling Task model methods.
        """
        tasks_result = await self.backend.list(limit=QueryLimit.SMALL)
        if tasks_result.is_error:
            return Result.fail(tasks_result)

        tasks, _ = tasks_result.value
        tasks_with_opportunities = [task for task in tasks if task.learning_opportunities_count > 0]

        if not tasks_with_opportunities:
            return Result.ok([])

        rels_list = await asyncio.gather(
            *[
                TaskRelationships.fetch(task.uid, self.relationships)
                for task in tasks_with_opportunities
            ]
        )

        opportunities: list[dict[str, Any]] = []
        for task, _rels in zip(tasks_with_opportunities, rels_list, strict=False):
            opportunities.append(
                {
                    "task_uid": task.uid,
                    "title": task.title,
                    "opportunities_count": task.learning_opportunities_count,
                    # knowledge_patterns inferred from relationships, not a stored field
                    "knowledge_patterns": [],
                    "complexity_score": task.calculate_knowledge_complexity(),
                    "learning_impact": task.calculate_learning_impact(),
                    "is_bridge_task": task.is_knowledge_bridge(),
                    "validates_mastery": task.validates_knowledge_mastery(),
                }
            )

        opportunities.sort(key=itemgetter("learning_impact"), reverse=True)
        return Result.ok(opportunities)

    async def generate_task_knowledge_insights(
        self, _domain_filter: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Generate knowledge insights summary across all user tasks.

        Aggregates bridge-task count, mastery-validation count, high-complexity
        count, and total learning opportunities; derives ratios and knowledge
        pattern analysis.

        GRAPH-NATIVE: Fetches relationships for all tasks in parallel.
        """
        tasks_result = await self.backend.list(limit=QueryLimit.COMPREHENSIVE)
        if tasks_result.is_error:
            return Result.fail(tasks_result)

        all_tasks, _ = tasks_result.value

        if not all_tasks:
            return Result.ok(
                {
                    "total_tasks_analyzed": 0,
                    "knowledge_bridge_tasks": 0,
                    "mastery_validation_tasks": 0,
                    "high_complexity_tasks": 0,
                    "total_learning_opportunities": 0,
                    "average_learning_opportunities": 0,
                    "bridge_task_ratio": 0,
                    "mastery_validation_ratio": 0,
                    "knowledge_discovery_patterns": {},
                }
            )

        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationships) for task in all_tasks]
        )

        knowledge_bridge_tasks: list[Task] = []
        mastery_validation_tasks: list[Task] = []
        high_complexity_tasks: list[Task] = []
        total_learning_opportunities = 0

        for task, _rels in zip(all_tasks, rels_list, strict=False):
            if task.is_knowledge_bridge():
                knowledge_bridge_tasks.append(task)
            if task.validates_knowledge_mastery():
                mastery_validation_tasks.append(task)
            if task.calculate_knowledge_complexity() > 0.7:
                high_complexity_tasks.append(task)
            total_learning_opportunities += task.learning_opportunities_count

        insights = {
            "total_tasks_analyzed": len(all_tasks),
            "knowledge_bridge_tasks": len(knowledge_bridge_tasks),
            "mastery_validation_tasks": len(mastery_validation_tasks),
            "high_complexity_tasks": len(high_complexity_tasks),
            "total_learning_opportunities": total_learning_opportunities,
            "average_learning_opportunities": total_learning_opportunities / len(all_tasks),
            "bridge_task_ratio": len(knowledge_bridge_tasks) / len(all_tasks),
            "mastery_validation_ratio": len(mastery_validation_tasks) / len(all_tasks),
            "knowledge_discovery_patterns": self._analyze_task_knowledge_patterns(
                all_tasks, rels_list
            ),
        }

        return Result.ok(insights)

    def _analyze_task_knowledge_patterns(
        self, tasks: list[Task], rels_list: list[TaskRelationships]
    ) -> KnowledgePatternAnalysis:
        """Derive knowledge-combination frequencies across tasks."""
        pattern_counts: dict[str, int] = {}
        knowledge_combinations: dict[tuple[str, ...], int] = {}

        for task, _rels in zip(tasks, rels_list, strict=False):
            all_knowledge = task.get_combined_knowledge_uids()
            if len(all_knowledge) > 1:
                combo_key = tuple(sorted(all_knowledge))
                knowledge_combinations[combo_key] = knowledge_combinations.get(combo_key, 0) + 1

        return KnowledgePatternAnalysis(
            common_patterns=dict(
                sorted(pattern_counts.items(), key=itemgetter(1), reverse=True)[:10]
            ),
            frequent_knowledge_combinations=dict(
                sorted(knowledge_combinations.items(), key=itemgetter(1), reverse=True)[:5]
            ),
            total_unique_patterns=len(pattern_counts),
            total_knowledge_combinations=len(knowledge_combinations),
        )
