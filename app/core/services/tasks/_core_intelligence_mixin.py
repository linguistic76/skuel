"""
Core Intelligence Mixin — TasksIntelligenceService
===================================================

Context retrieval and cross-domain categorization.

Part of tasks_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.services.intelligence._core_intelligence_mixin import (
    _CoreIntelligenceMixin as _SharedCoreMixin,
)
from core.utils.decorators import requires_graph_intelligence, with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext
    from core.models.task.task import Task


class _CoreIntelligenceMixin(_SharedCoreMixin):
    """
    Graph context and cross-domain categorization for TasksIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by TasksIntelligenceService.__init__
    context_loader: Any
    logger: Any

    @requires_graph_intelligence("get_task_with_context")
    async def get_task_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Task, GraphContext]]:
        """
        Domain-named alias for get_with_context().

        Calls the context loader directly to avoid recursive MRO resolution
        with the protocol-level get_with_context() method.
        """
        if not self.context_loader:
            return Result.fail(
                Errors.system(
                    message="GraphContextLoader not initialized",
                    operation="get_task_with_context",
                )
            )
        return await self.context_loader.get_with_context(uid=uid, depth=depth)  # type: ignore[return-value]

    @with_error_handling(
        "categorize_cross_domain_context", error_type="system", uid_param="task_uid"
    )
    async def categorize_cross_domain_context(
        self, task_uid: str, raw_context: list[dict[str, Any]]
    ) -> Result[dict[str, Any]]:
        """
        Categorize raw graph context into task-specific groups.

        Architecture:
        - Backend provides raw graph data via get_domain_context_raw()
        - Intelligence service performs domain-specific categorization
        - This achieves true separation: Backend = primitives, Intelligence = domain logic

        Args:
            task_uid: Task UID
            raw_context: Raw graph context from backend (list of entities with metadata)

        Returns:
            Result containing TaskCrossContext grouped by relationship semantic:
            - prerequisites: Tasks that must be completed first (DEPENDS_ON - outgoing)
            - dependents: Tasks that depend on this one (DEPENDS_ON - incoming)
            - required_knowledge: Knowledge needed to complete task (REQUIRES_KNOWLEDGE)
            - applied_knowledge: Knowledge this task applies (APPLIES_KNOWLEDGE)
            - contributing_goals: Goals this task fulfills (CONTRIBUTES_TO_GOAL, FULFILLS_GOAL)
        """
        from core.models.graph.path_aware_types import (
            PathAwareGoal,
            PathAwareKnowledge,
            PathAwareTask,
            TaskCrossContext,
        )

        # Group by entity type and relationship
        prerequisites = []
        dependents = []
        required_knowledge = []
        applied_knowledge = []
        contributing_goals = []

        for entity in raw_context:
            labels = entity["labels"]
            via_rels = entity["via_relationships"]

            # Task dependencies (bidirectional DEPENDS_ON)
            # Use directional markers (->DEPENDS_ON / <-DEPENDS_ON) to distinguish
            depends_on = RelationshipName.DEPENDS_ON.value
            if NeoLabel.ENTITY.value in labels and (
                f"->{depends_on}" in via_rels
                or depends_on in via_rels
                or f"<-{depends_on}" in via_rels
            ):
                task_entity = PathAwareTask(
                    uid=entity["uid"],
                    title=entity["title"],
                    distance=entity["distance"],
                    path_strength=entity["path_strength"],
                    via_relationships=via_rels,
                )

                # Check for directional relationship markers
                if f"->{depends_on}" in via_rels or depends_on in via_rels:
                    # Outgoing DEPENDS_ON = this task depends on the related task (prerequisite)
                    prerequisites.append(task_entity)
                elif f"<-{depends_on}" in via_rels:
                    # Incoming DEPENDS_ON = related task depends on this one (dependent)
                    dependents.append(task_entity)

            # Knowledge requirements (REQUIRES_KNOWLEDGE, APPLIES_KNOWLEDGE)
            elif NeoLabel.ENTITY.value in labels and (
                RelationshipName.REQUIRES_KNOWLEDGE.value in via_rels
                or RelationshipName.APPLIES_KNOWLEDGE.value in via_rels
            ):
                knowledge_entity = PathAwareKnowledge(
                    uid=entity["uid"],
                    title=entity["title"],
                    distance=entity["distance"],
                    path_strength=entity["path_strength"],
                    via_relationships=via_rels,
                )
                if RelationshipName.REQUIRES_KNOWLEDGE.value in via_rels:
                    required_knowledge.append(knowledge_entity)
                elif RelationshipName.APPLIES_KNOWLEDGE.value in via_rels:
                    applied_knowledge.append(knowledge_entity)

            # Goals this task contributes to/fulfills
            elif NeoLabel.ENTITY.value in labels and (
                RelationshipName.CONTRIBUTES_TO_GOAL.value in via_rels
                or RelationshipName.FULFILLS_GOAL.value in via_rels
            ):
                contributing_goals.append(
                    PathAwareGoal(
                        uid=entity["uid"],
                        title=entity["title"],
                        distance=entity["distance"],
                        path_strength=entity["path_strength"],
                        via_relationships=via_rels,
                    )
                )

        context = TaskCrossContext(
            task_uid=task_uid,
            prerequisites=prerequisites,
            dependents=dependents,
            required_knowledge=required_knowledge,
            applied_knowledge=applied_knowledge,
            contributing_goals=contributing_goals,
        )

        return Result.ok(
            {
                "task_uid": context.task_uid,
                "prerequisites": [
                    {
                        "uid": t.uid,
                        "title": t.title,
                        "distance": t.distance,
                        "path_strength": t.path_strength,
                        "via_relationships": t.via_relationships,
                    }
                    for t in context.prerequisites
                ],
                "dependents": [
                    {
                        "uid": t.uid,
                        "title": t.title,
                        "distance": t.distance,
                        "path_strength": t.path_strength,
                        "via_relationships": t.via_relationships,
                    }
                    for t in context.dependents
                ],
                "required_knowledge": [
                    {
                        "uid": k.uid,
                        "title": k.title,
                        "distance": k.distance,
                        "path_strength": k.path_strength,
                        "via_relationships": k.via_relationships,
                    }
                    for k in context.required_knowledge
                ],
                "applied_knowledge": [
                    {
                        "uid": k.uid,
                        "title": k.title,
                        "distance": k.distance,
                        "path_strength": k.path_strength,
                        "via_relationships": k.via_relationships,
                    }
                    for k in context.applied_knowledge
                ],
                "contributing_goals": [
                    {
                        "uid": g.uid,
                        "title": g.title,
                        "distance": g.distance,
                        "path_strength": g.path_strength,
                        "via_relationships": g.via_relationships,
                    }
                    for g in context.contributing_goals
                ],
            }
        )
