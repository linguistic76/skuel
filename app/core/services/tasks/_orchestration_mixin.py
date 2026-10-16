"""Orchestration methods extracted from TasksService facade."""

from __future__ import annotations

from typing import Any

from core.utils.result_simplified import Result


class _OrchestrationMixin:
    """Orchestration methods for TasksService."""

    relationships: Any
    get_task: Any  # Provided by TasksService facade

    async def analyze_task_knowledge_impact(self, task_uid: str) -> Result[dict[str, Any]]:
        """
        Analyze the knowledge impact of a specific task.

        The scores come from the Task's own fields; the knowledge it links comes from
        its graph edges.
        """
        from core.services.tasks.task_relationships import TaskRelationships

        task_result = await self.get_task(task_uid)
        if task_result.is_error:
            return Result.fail(task_result)

        task = task_result.value

        # GRAPH-NATIVE: Fetch relationship data from graph
        rels = await TaskRelationships.fetch(task.uid, self.relationships)

        impact_analysis = {
            "task_uid": task.uid,
            "title": task.title,
            "knowledge_complexity_score": task.calculate_knowledge_complexity(),
            "learning_impact_score": task.calculate_learning_impact(),
            "is_knowledge_bridge": task.is_knowledge_bridge(),
            "validates_mastery": task.validates_knowledge_mastery(),
            "combined_knowledge_uids": rels.get_combined_knowledge_uids(),
        }

        return Result.ok(impact_analysis)
