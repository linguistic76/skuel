"""Orchestration methods extracted from TasksService facade."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.task.task import Task
    from core.models.type_hints import UserUID
    from core.services.user import UserContext


class _OrchestrationMixin:
    """Orchestration methods for TasksService."""

    progress: Any
    relationships: Any
    intelligence: Any
    logger: Any
    event_handler: Any
    get_task: Any  # Provided by TasksService facade

    async def complete_task_with_cascade(
        self,
        task_uid: str,
        user_context: UserContext,
        actual_minutes: int | None = None,
        quality_score: int | None = None,
    ) -> Result[Task]:
        """Complete a task and cascade updates through the system.

        Knowledge generation runs as a TaskCompleted event subscriber in
        TaskEventHandlerService — not as an inline side effect here.
        """
        return await self.progress.complete_task_with_cascade(
            task_uid, user_context, actual_minutes, quality_score
        )

    async def analyze_task_knowledge_impact(self, task_uid: str) -> Result[dict[str, Any]]:
        """
        Analyze the knowledge impact of a specific task using unified Task model.

        GRAPH-NATIVE: Fetches relationship data from graph to pass to Task methods.
        """
        from core.services.tasks.task_relationships import TaskRelationships

        task_result = await self.get_task(task_uid)
        if task_result.is_error:
            return Result.fail(task_result)

        task = task_result.value

        # GRAPH-NATIVE: Fetch relationship data from graph
        _rels = await TaskRelationships.fetch(task.uid, self.relationships)

        # Use unified Task model knowledge capabilities
        impact_analysis = {
            "task_uid": task.uid,
            "title": task.title,
            "knowledge_complexity_score": task.calculate_knowledge_complexity(),
            "learning_impact_score": task.calculate_learning_impact(),
            "is_knowledge_bridge": task.is_knowledge_bridge(),
            "validates_mastery": task.validates_knowledge_mastery(),
            "enhancement_summary": task.get_knowledge_enhancement_summary(),
            "all_knowledge_connections": task.get_all_knowledge_connections(),
            "combined_knowledge_uids": task.get_combined_knowledge_uids(),
        }

        return Result.ok(impact_analysis)

    async def trigger_manual_knowledge_generation(
        self, user_uid: UserUID, days_back: int = 30, min_tasks: int = 3
    ) -> Result[dict[str, Any]]:
        """
        Manually trigger knowledge generation and return results for review.

        Args:
            user_uid: User whose tasks to analyze
            days_back: Days of history to analyze
            min_tasks: Minimum completed tasks needed

        Returns:
            Result containing generation summary and knowledge units
        """
        ku_generation_service = self.event_handler.ku_generation_service
        if not ku_generation_service:
            return Result.fail(
                Errors.system(
                    message="Knowledge generation service not available",
                    operation="trigger_manual_knowledge_generation",
                )
            )

        try:
            knowledge_result = await ku_generation_service.extract_knowledge_from_completed_tasks(
                user_uid=user_uid, days_back=days_back, min_tasks=min_tasks
            )

            if knowledge_result.is_error:
                return Result.fail(knowledge_result)

            generated_knowledge = knowledge_result.value

            if not generated_knowledge:
                return Result.ok(
                    {
                        "message": "No knowledge could be generated from completed tasks",
                        "generated_count": 0,
                        "curated_knowledge": {},
                    }
                )

            curation_result = ku_generation_service.curate_generated_knowledge(generated_knowledge)

            if curation_result.is_error:
                return curation_result

            curated_knowledge = curation_result.value

            return Result.ok(
                {
                    "user_uid": user_uid,
                    "analysis_period_days": days_back,
                    "generated_knowledge_count": len(generated_knowledge),
                    "curated_knowledge": curated_knowledge,
                    "statistics": {
                        "auto_publish_ready": len(curated_knowledge.get("auto_publish", [])),
                        "review_recommended": len(curated_knowledge.get("review_recommended", [])),
                        "needs_improvement": len(curated_knowledge.get("needs_improvement", [])),
                        "low_quality": len(curated_knowledge.get("low_quality", [])),
                    },
                    "generation_timestamp": datetime.now().isoformat(),
                }
            )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(f"Manual knowledge generation failed for user {user_uid}: {e}")
            return Result.fail(
                Errors.system(
                    message=f"Knowledge generation failed: {e!s}",
                    operation="trigger_manual_knowledge_generation",
                )
            )
