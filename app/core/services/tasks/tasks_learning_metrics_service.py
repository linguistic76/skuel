"""
Tasks Learning Metrics Service
================================

Task-level learning metrics using Task model capabilities + TaskRelationships.

Different from TasksIntelligenceService.get_learning_opportunities() which uses
graph intelligence for discovery. This service analyzes individual tasks for:
- Knowledge complexity score
- Learning impact score
- Knowledge bridge detection
- Mastery validation

Architecture:
- Uses Task model methods (calculate_knowledge_complexity, is_knowledge_bridge, etc.)
- Fetches relationship data via TaskRelationships
- Pure graph queries + Python calculations (NO AI dependencies)
- Moved from TasksAnalyticsService (January 2026)
"""

from __future__ import annotations

import asyncio
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.constants import QueryLimit
from core.models.task.task import Task
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.tasks.task_relationships import TaskRelationships
from core.services.tasks_types import KnowledgePatternAnalysis
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations  # noqa: F401


class TasksLearningMetricsService(BaseAnalyticsService["TasksOperations", Task]):
    """
    Task-level learning metrics using Task model capabilities.

    GRAPH-NATIVE: Fetches relationship data from graph to pass to Task methods.

    Pure calculation — no AI dependencies.
    """

    _service_name = "tasks.learning_metrics"

    async def analyze_task_learning_metrics(
        self, _filters: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        Analyze learning metrics from tasks using Task model capabilities.

        GRAPH-NATIVE: Fetches relationship data from graph to pass to Task methods.

        This method analyzes individual tasks for:
        - Knowledge complexity score
        - Learning impact score
        - Knowledge bridge detection
        - Mastery validation

        Different from get_learning_opportunities() which uses graph intelligence
        to discover what knowledge is needed for tasks.

        Returns:
            Result containing list of task learning metrics sorted by impact
        """
        # Get tasks from backend
        tasks_result = await self.backend.list(limit=QueryLimit.SMALL)
        if tasks_result.is_error:
            return Result.fail(tasks_result)

        tasks, _ = tasks_result.value
        opportunities = []

        # GRAPH-NATIVE: Fetch relationships for tasks with learning opportunities
        tasks_with_opportunities = [task for task in tasks if task.learning_opportunities_count > 0]

        if not tasks_with_opportunities:
            return Result.ok([])

        # Fetch all relationships in parallel
        rels_list = await asyncio.gather(
            *[
                TaskRelationships.fetch(task.uid, self.relationships)
                for task in tasks_with_opportunities
            ]
        )

        for task, _rels in zip(tasks_with_opportunities, rels_list, strict=False):
            opportunity = {
                "task_uid": task.uid,
                "title": task.title,
                "opportunities_count": task.learning_opportunities_count,
                # NOTE: knowledge_patterns inferred from relationships, not stored field
                "knowledge_patterns": [],
                "complexity_score": task.calculate_knowledge_complexity(),
                "learning_impact": task.calculate_learning_impact(),
                "is_bridge_task": task.is_knowledge_bridge(),
                "validates_mastery": task.validates_knowledge_mastery(),
            }
            opportunities.append(opportunity)

        # Sort by learning impact (highest first)
        opportunities.sort(key=itemgetter("learning_impact"), reverse=True)

        return Result.ok(opportunities)

    async def generate_task_knowledge_insights(
        self, _domain_filter: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Generate knowledge insights using Task model capabilities.

        GRAPH-NATIVE: Fetches relationship data from graph to pass to Task methods.

        Returns:
            Result containing knowledge insights summary
        """
        # Get all tasks to analyze knowledge patterns
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

        # GRAPH-NATIVE: Fetch relationships for all tasks in parallel
        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationships) for task in all_tasks]
        )

        knowledge_bridge_tasks = []
        mastery_validation_tasks = []
        high_complexity_tasks = []
        total_learning_opportunities = 0

        for task, _rels in zip(all_tasks, rels_list, strict=False):
            # Analyze using unified Task model capabilities
            if task.is_knowledge_bridge():
                knowledge_bridge_tasks.append(task)

            if task.validates_knowledge_mastery():
                mastery_validation_tasks.append(task)

            if task.calculate_knowledge_complexity() > 0.7:
                high_complexity_tasks.append(task)

            total_learning_opportunities += task.learning_opportunities_count

        # Generate insights
        insights = {
            "total_tasks_analyzed": len(all_tasks),
            "knowledge_bridge_tasks": len(knowledge_bridge_tasks),
            "mastery_validation_tasks": len(mastery_validation_tasks),
            "high_complexity_tasks": len(high_complexity_tasks),
            "total_learning_opportunities": total_learning_opportunities,
            "average_learning_opportunities": total_learning_opportunities / len(all_tasks)
            if all_tasks
            else 0,
            "bridge_task_ratio": len(knowledge_bridge_tasks) / len(all_tasks) if all_tasks else 0,
            "mastery_validation_ratio": len(mastery_validation_tasks) / len(all_tasks)
            if all_tasks
            else 0,
            "knowledge_discovery_patterns": self._analyze_task_knowledge_patterns(
                all_tasks, rels_list
            ),
        }

        return Result.ok(insights)

    def _analyze_task_knowledge_patterns(
        self, tasks: list[Task], rels_list: list[TaskRelationships]
    ) -> KnowledgePatternAnalysis:
        """
        Analyze knowledge patterns across tasks using unified Task model.

        GRAPH-NATIVE: Requires relationship data for knowledge analysis.

        Args:
            tasks: List of tasks to analyze
            rels_list: List of TaskRelationships corresponding to tasks

        Returns:
            Knowledge pattern analysis
        """
        pattern_counts: dict[str, int] = {}
        knowledge_combinations: dict[tuple[str, ...], int] = {}

        for task, _rels in zip(tasks, rels_list, strict=False):
            # NOTE: Pattern counting skipped - knowledge_patterns inferred from relationships
            pass

            # Analyze knowledge combinations
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
