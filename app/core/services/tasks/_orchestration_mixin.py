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

    backend: Any
    progress: Any
    relationships: Any
    intelligence: Any
    logger: Any
    _ku_generation_service: Any
    get_task: Any  # Provided by TasksService facade

    async def complete_task_with_cascade(
        self,
        task_uid: str,
        user_context: UserContext,
        actual_minutes: int | None = None,
        quality_score: int | None = None,
    ) -> Result[Task]:
        """Complete a task and cascade updates through the system."""
        result = await self.progress.complete_task_with_cascade(
            task_uid, user_context, actual_minutes, quality_score
        )
        if result.is_ok and self._ku_generation_service:
            await self._trigger_knowledge_generation(user_context.user_uid)
        return result

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
            "enhancement_summary": task.get_knowledge_enhancement_summary(),  # type: ignore[attr-defined]
            "all_knowledge_connections": task.get_all_knowledge_connections(),  # type: ignore[attr-defined]
            "combined_knowledge_uids": task.get_combined_knowledge_uids(),
        }

        return Result.ok(impact_analysis)

    async def get_user_assigned_tasks(
        self, user_uid: UserUID, include_completed: bool = False, limit: int = 100
    ) -> Result[list[Task]]:
        """Get tasks assigned to user via graph traversal."""
        filters: dict[str, Any] = {"user_uid": user_uid}
        if not include_completed:
            filters["status__ne"] = "completed"
        result = await self.backend.list(filters=filters, limit=limit)
        if result.is_error:
            return Result.fail(result)
        # list() returns tuple[list[Task], int]
        tasks, _ = result.value
        return Result.ok(tasks)

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
        if not self._ku_generation_service:
            return Result.fail(
                Errors.system(
                    message="Knowledge generation service not available",
                    operation="trigger_manual_knowledge_generation",
                )
            )

        try:
            knowledge_result = (
                await self._ku_generation_service.extract_knowledge_from_completed_tasks(
                    user_uid=user_uid, days_back=days_back, min_tasks=min_tasks
                )
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

            curation_result = await self._ku_generation_service.curate_generated_knowledge(
                generated_knowledge
            )

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

    async def _trigger_knowledge_generation(self, user_uid: UserUID) -> None:
        """Trigger automatic knowledge generation from completed tasks."""
        if not self._ku_generation_service:
            return

        try:
            knowledge_result = (
                await self._ku_generation_service.extract_knowledge_from_completed_tasks(
                    user_uid=user_uid, days_back=30, min_tasks=3
                )
            )

            if knowledge_result.is_ok and knowledge_result.value:
                curation_result = await self._ku_generation_service.curate_generated_knowledge(
                    knowledge_result.value
                )

                if curation_result.is_ok:
                    auto_published = curation_result.value.get("auto_publish", [])
                    for knowledge_dto in auto_published:
                        if self._ku_generation_service.ku_service:
                            await self._ku_generation_service.ku_service.create(
                                title=knowledge_dto.title,
                                body=knowledge_dto.content,
                                summary=knowledge_dto.content[:200] + "..."
                                if len(knowledge_dto.content) > 200
                                else knowledge_dto.content,
                                tags=knowledge_dto.tags,
                                domain=str(knowledge_dto.domain.value),
                                **knowledge_dto.metadata,
                            )
        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.warning(f"Knowledge generation failed for user {user_uid}: {e}")
