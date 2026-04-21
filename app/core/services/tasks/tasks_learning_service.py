"""
Tasks Learning Service
======================

Handles task-learning path integration and knowledge-aware operations.

Responsibilities:
- Suggest learning-aligned tasks
- Identify tasks relevant to user's current learning position
- Surface the next recommended learning task
- Generate tasks from a learning path
"""

from __future__ import annotations

from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus, Priority
from core.models.pathways.lp_position import LpPosition
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.type_hints import UserUID
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations
    from core.services.relationships import UnifiedRelationshipService


class TasksLearningService(BaseService["TasksOperations", Task]):
    """Learning path integration service for tasks."""

    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        entity_label="Entity",
    )

    def __init__(
        self,
        backend: TasksOperations,
        event_bus: Any = None,
        relationship_service: UnifiedRelationshipService | None = None,
    ) -> None:
        """
        Args:
            backend: TasksOperations backend (required)
            event_bus: Event bus (accepted for factory uniformity, not used)
            relationship_service: Relationship service (accepted for factory uniformity, not used)
        """
        super().__init__(backend=backend, service_name="tasks.learning")
        self.event_bus = event_bus
        self.relationships = relationship_service

    @property
    def entity_label(self) -> str:
        return "Entity"

    @with_error_handling("get_learning_relevant_tasks", error_type="database", uid_param="user_uid")
    async def get_learning_relevant_tasks(
        self, user_uid: UserUID, learning_position: LpPosition, limit: int = 10
    ) -> Result[list[Task]]:
        """Get tasks most relevant to the user's current learning path position."""
        tasks_result = await self.backend.get_user_entities(user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result)

        entities, _total = tasks_result.value
        all_tasks = self._to_domain_models(entities, TaskDTO, Task)

        task_scores: list[tuple[Task, float]] = []
        for task in all_tasks:
            if task.status == EntityStatus.COMPLETED:
                continue

            applies_knowledge_result = await self.backend.get_related_uids(
                task.uid, RelationshipName.APPLIES_KNOWLEDGE, direction="outgoing"
            )
            task_knowledge_uids = (
                applies_knowledge_result.value if applies_knowledge_result.is_ok else []
            )
            task_domain = task.priority if task.priority else "general"
            relevance_score = learning_position.assess_task_relevance(
                task_domain, task_knowledge_uids
            )
            task_scores.append((task, relevance_score))

        task_scores.sort(key=itemgetter(1), reverse=True)
        relevant_tasks = [task for task, _ in task_scores[:limit]]

        self.logger.info(
            "Found %d learning-relevant tasks for user %s (from %d total)",
            len(relevant_tasks),
            user_uid,
            len(all_tasks),
        )

        return Result.ok(relevant_tasks)

    @with_error_handling("get_next_learning_task", error_type="database")
    async def get_next_learning_task(self, user_context: UserContext) -> Result[Task | None]:
        """Get the next recommended learning task based on context."""
        ready_knowledge = user_context.get_ready_to_learn()
        if not ready_knowledge:
            return Result.ok(None)

        self.logger.debug(
            f"Get next learning task - found {len(ready_knowledge)} ready knowledge areas"
        )
        return Result.ok(None)

    @with_error_handling("suggest_learning_aligned_tasks", error_type="database")
    async def suggest_learning_aligned_tasks(
        self, learning_position: LpPosition, _task_domain: str | None = None, limit: int = 10
    ) -> Result[list[dict[str, Any]]]:
        """Suggest new tasks aligned with learning path progression."""
        suggestions: list[dict[str, Any]] = []

        for path in learning_position.active_paths:
            current_step = learning_position.current_steps.get(path.uid)
            if not current_step:
                continue

            ku_uid = (
                current_step.knowledge_uids[0]
                if current_step.knowledge_uids
                else current_step.title
            )

            suggestions.append(
                {
                    "title": f"Practice {ku_uid}",
                    "description": f"Apply {ku_uid} knowledge from {path.title}",
                    "learning_path": path.title,
                    "knowledge_uid": ku_uid,
                    "estimated_minutes": int((current_step.estimated_hours or 0) * 60 / 3),
                    "priority": Priority.MEDIUM.value,
                    "learning_relevance_score": 0.9,
                    "suggestion_reason": f"Aligns with current step in {path.title}",
                }
            )

            path_steps = path.metadata.get("steps", []) if path.metadata else []
            try:
                current_index = path_steps.index(current_step)
                if current_index + 1 < len(path_steps):
                    next_step = path_steps[current_index + 1]
                    next_ku_uid = (
                        next_step.knowledge_uids[0] if next_step.knowledge_uids else next_step.title
                    )
                    suggestions.append(
                        {
                            "title": f"Prepare for {next_ku_uid}",
                            "description": f"Research and prepare for upcoming {next_ku_uid} in {path.title}",
                            "learning_path": path.title,
                            "knowledge_uid": next_ku_uid,
                            "estimated_minutes": 30,
                            "priority": Priority.LOW.value,
                            "learning_relevance_score": 0.7,
                            "suggestion_reason": f"Preparation for next step in {path.title}",
                        }
                    )
            except ValueError:
                pass

        suggestions.sort(key=itemgetter("learning_relevance_score"), reverse=True)

        self.logger.info(
            "Generated %d learning-aligned task suggestions from %d active paths",
            len(suggestions),
            len(learning_position.active_paths),
        )

        return Result.ok(suggestions[:limit])

    async def create_tasks_from_learning_path(
        self, learning_path_uid: str, _user_context: UserContext
    ) -> Result[list[Task]]:
        """Create tasks from a learning path (stub — pending implementation)."""
        self.logger.debug(
            f"Create tasks from learning path {learning_path_uid} - not yet implemented"
        )
        return Result.ok([])
