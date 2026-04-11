"""
Productivity Mixin — TasksIntelligenceService
=============================================

Analytics engine methods: learning patterns, knowledge-aware priorities,
task insights, mastery progression.

Part of tasks_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.type_hints import UserUID


class _ProductivityMixin:
    """
    Analytics engine methods for TasksIntelligenceService.

    Delegates to AnalyticsEngine for pattern detection, priority calculation,
    insight generation, and mastery tracking.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by TasksIntelligenceService.__init__
    backend: Any
    logger: Any
    _analytics_engine: Any
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

        return await self._analytics_engine.analyze_learning_patterns(
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

        mastery_result = await self._analytics_engine.track_knowledge_mastery_progression(
            all_tasks, list(all_knowledge_uids)
        )
        mastery_progressions = mastery_result.value if mastery_result.is_ok else {}

        priorities = []
        for task in tasks_to_prioritize:
            priority_result = await self._analytics_engine.calculate_knowledge_aware_priority(
                task, mastery_progressions, patterns
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

        return await self._analytics_engine.generate_task_insights(completed_tasks, patterns)

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

        return await self._analytics_engine.track_knowledge_mastery_progression(
            all_tasks, knowledge_uids
        )
