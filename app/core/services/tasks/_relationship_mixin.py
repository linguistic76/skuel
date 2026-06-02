"""Relationship and context methods extracted from TasksService facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.events import TaskUpdated, publish_event
from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.graph_context import GraphContext
    from core.models.task.task import Task
    from core.models.type_hints import Neo4jProperties, UserUID
    from core.ports.domain_protocols import TasksOperations
    from core.ports.infrastructure_protocols import EventBusOperations


class _RelationshipMixin:
    """Relationship and context retrieval methods for TasksService."""

    relationships: Any
    backend: TasksOperations
    event_bus: EventBusOperations | None
    logger: Any

    async def get_task_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Task, GraphContext]]:
        """Get task with full graph context using pure Cypher graph intelligence."""
        return await self.relationships.get_with_context(uid, depth)

    async def get_task_with_dependencies(self, uid: str, depth: int = 2) -> Result[dict[str, Any]]:
        """Get task with complete dependency graph."""
        result = await self.relationships.get_with_context(uid, depth, intent="dependencies")
        if result.is_error:
            return result
        task, context = result.value
        return Result.ok({"task": task, "graph_context": context})

    async def get_task_practice_opportunities(
        self, uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """Find practice opportunities related to this task."""
        result = await self.relationships.get_with_context(uid, depth, intent="practice")
        if result.is_error:
            return result
        task, context = result.value
        return Result.ok({"task": task, "practice_context": context})

    async def link_task_to_knowledge(
        self,
        task_uid: str,
        knowledge_uid: str,
        knowledge_score_required: float = 0.8,
        is_learning_opportunity: bool = False,
    ) -> Result[bool]:
        """Link task to required knowledge unit."""
        return await self.relationships.link_to_knowledge(
            task_uid,
            knowledge_uid,
            knowledge_score_required=knowledge_score_required,
            is_learning_opportunity=is_learning_opportunity,
        )

    async def link_task_to_goal(
        self,
        task_uid: str,
        goal_uid: str,
        contribution_percentage: float = 0.1,
        milestone_uid: str | None = None,
    ) -> Result[bool]:
        """Link task to goal it contributes to."""
        return await self.relationships.link_to_goal(
            task_uid,
            goal_uid,
            contribution_percentage=contribution_percentage,
            milestone_uid=milestone_uid,
        )

    async def create_task_dependency(
        self,
        dependent_task_uid: str,
        blocks_task_uid: str,
        is_hard_dependency: bool = True,
        dependency_type: str = "blocks",
    ) -> Result[bool]:
        """Create a ``(dependent)-[:DEPENDS_ON]->(blocks)`` dependency edge between tasks.

        Backend: UniversalNeo4jBackend.create_relationships_batch — the same proven
        path the create/update flows use. NOT UnifiedRelationshipService.create_relationship,
        whose dynamic ``link_task_to_<key>`` backend method does not exist for tasks
        (it getattrs a missing method and fails at runtime — the bug this method had).
        """
        properties: Neo4jProperties = {
            "is_hard_dependency": is_hard_dependency,
            "dependency_type": dependency_type,
        }
        edges: list[tuple[str, str, str, Neo4jProperties | None]] = [
            (dependent_task_uid, blocks_task_uid, RelationshipName.DEPENDS_ON.value, properties)
        ]
        result = await self.backend.create_relationships_batch(edges)
        if result.is_error:
            return Result.fail(result)
        await self._publish_dependency_update(dependent_task_uid, blocks_task_uid)
        return Result.ok(True)

    async def _publish_dependency_update(
        self, dependent_task_uid: str, blocks_task_uid: str
    ) -> None:
        """Publish TaskUpdated for the affected owners after a DEPENDS_ON edge change.

        The dependency graph feeds ``UnifiedUserContext.task_dependencies`` and the
        inverse blockers view, so a successful edge-only mutation must invalidate the
        owners' rich-context caches — otherwise dependency context stays stale until
        the TTL expires (same reason ``_publish_edge_only_update`` exists for the
        habit/knowledge edges). Best-effort: with no event bus wired, or a task that
        no longer resolves, this is a no-op — the edge is already written.
        """
        if self.event_bus is None:
            return
        seen: set[str] = set()
        for uid in (dependent_task_uid, blocks_task_uid):
            fetched = await self.backend.get(uid)
            if fetched.is_error or fetched.value is None:
                continue
            user_uid = fetched.value.user_uid
            if not user_uid or user_uid in seen:
                continue
            seen.add(user_uid)
            event = TaskUpdated(task_uid=uid, user_uid=user_uid, updated_fields=["dependencies"])
            await publish_event(self.event_bus, event, self.logger)

    async def get_tasks_requiring_knowledge(
        self, knowledge_uid: str, _user_uid: UserUID | None = None, _limit: int = 100
    ) -> Result[list[Task]]:
        """Get tasks that require specific knowledge (returns Task objects, not dicts)."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=knowledge_uid,
            min_confidence=0.0,
            direction="incoming",
        )

    async def create_semantic_knowledge_relationship(
        self,
        task_uid: str,
        knowledge_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create a semantic relationship between task and knowledge."""
        return await self.relationships.create_semantic_relationship(
            task_uid, knowledge_uid, semantic_type, confidence, notes
        )
