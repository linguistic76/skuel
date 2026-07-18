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

from core.models.enums import Domain, EntityStatus
from core.models.pathways.lp_position import LpPosition
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_request import TaskCreateRequest
from core.models.type_hints import UserUID
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.infrastructure import LearningAlignmentBridge
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
        super().__init__(backend=backend, service_name="tasks.learning")
        self.event_bus = event_bus
        self.relationships = relationship_service

        self.learning_helper = LearningAlignmentBridge[Task, TaskDTO, TaskCreateRequest](
            service=self,
            backend_get=self.backend.get_task,
            backend_get_user=self.backend.get_user_tasks,
            backend_create=self.backend.create_task,
            domain=Domain.TASKS,
            entity_name="task",
        )

    @with_error_handling("get_learning_relevant_tasks", error_type="database", uid_param="user_uid")
    async def get_learning_relevant_tasks(
        self, user_uid: UserUID, learning_position: LpPosition, limit: int = 10
    ) -> Result[list[Task]]:
        # Stays hand-rolled (not delegated to LearningAlignmentBridge): Task knowledge
        # lives on APPLIES_KNOWLEDGE edges, not on the model, so scoring requires an
        # async fetch per task. The Bridge's sync scorer cannot express that, and
        # LpPosition.assess_task_relevance has current+next-step semantics distinct
        # from the Bridge's default sum-based scorer.
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
    async def get_next_learning_task(
        self, user_context: UserContext
    ) -> Result[
        Task | None
    ]:  # skuel-lint: disable=SKUEL029 -- facade-delegated: TasksService.get_next_learning_task awaits this via delegation
        """Get the next recommended learning task based on context."""
        ready_knowledge = user_context.get_ready_to_learn()
        if not ready_knowledge:
            return Result.ok(None)

        self.logger.debug(
            f"Get next learning task - found {len(ready_knowledge)} ready knowledge areas"
        )
        return Result.ok(None)

    async def suggest_learning_aligned_tasks(
        self, learning_position: LpPosition, _task_domain: str | None = None, limit: int = 10
    ) -> Result[list[dict[str, Any]]]:
        """Suggest new tasks aligned with learning path progression."""
        return await self.learning_helper.suggest_learning_aligned_entities(
            learning_position=learning_position, max_suggestions=limit
        )

    async def create_tasks_from_learning_path(  # skuel-lint: disable=SKUEL029 -- facade-delegated: TasksService awaits this via delegation
        self, learning_path_uid: str, _user_context: UserContext
    ) -> Result[list[Task]]:
        """Create tasks from a learning path (stub — pending implementation)."""
        self.logger.debug(
            f"Create tasks from learning path {learning_path_uid} - not yet implemented"
        )
        return Result.ok([])
