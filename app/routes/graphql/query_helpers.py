"""
GraphQL Query Helpers
=====================

GraphQL-optimized query helpers that delegate to service layer.

These helpers are specifically designed for GraphQL resolvers:
- Delegate to service methods (never contain Cypher directly)
- Return GraphQL types directly
- Use GraphQLContext infrastructure
- Optimize for nested resolver patterns
"""

from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from routes.graphql.context import GraphQLContext

if TYPE_CHECKING:
    from routes.graphql.types import KnowledgeNode

logger = get_logger("skuel.graphql.query_helpers")


class GraphQLQueryHelpers:
    """
    Query helpers optimized for GraphQL patterns.

    All methods delegate to service layer methods — no direct Cypher.
    """

    # ========================================================================
    # KNOWLEDGE RELATIONSHIP QUERIES
    # ========================================================================

    @staticmethod
    async def get_prerequisites(context: GraphQLContext, ku_uid: str) -> list["KnowledgeNode"]:
        """
        Get prerequisite knowledge units for GraphQL resolver.

        Delegates to ArticleService.get_prerequisites() which returns
        Result[list[CurriculumDTO]].
        """
        from routes.graphql.types import KnowledgeNode

        if not context.services.article:
            return []

        result = await context.services.article.get_prerequisites(ku_uid)
        if result.is_error or not result.value:
            return []

        prereqs = [
            KnowledgeNode(
                uid=dto.uid,
                title=dto.title,
                summary=dto.summary or "",
                domain=dto.domain.value,
                tags=dto.tags or [],
                quality_score=dto.quality_score,
            )
            for dto in result.value
        ]

        logger.debug(f"Loaded {len(prereqs)} prerequisites for {ku_uid}")
        return prereqs

    @staticmethod
    async def get_enables(context: GraphQLContext, ku_uid: str) -> list["KnowledgeNode"]:
        """
        Get knowledge units enabled by this one (reverse prerequisites).

        Delegates to ArticleService.get_enables() which returns
        Result[list[CurriculumDTO]].
        """
        from routes.graphql.types import KnowledgeNode

        if not context.services.article:
            return []

        result = await context.services.article.get_enables(ku_uid)
        if result.is_error or not result.value:
            return []

        enabled = [
            KnowledgeNode(
                uid=dto.uid,
                title=dto.title,
                summary=dto.summary or "",
                domain=dto.domain.value,
                tags=dto.tags or [],
                quality_score=dto.quality_score,
            )
            for dto in result.value
        ]

        logger.debug(f"Loaded {len(enabled)} enabled knowledge units for {ku_uid}")
        return enabled

    # ========================================================================
    # TASK KNOWLEDGE RELATIONSHIPS
    # ========================================================================

    @staticmethod
    async def get_task_knowledge(context: GraphQLContext, task_uid: str) -> "KnowledgeNode | None":
        """
        Get knowledge unit associated with a task.

        Uses DataLoader for batching when loading tasks with knowledge.

        Args:
            context: GraphQL execution context
            task_uid: Task UID

        Returns:
            KnowledgeNode if task has associated knowledge, None otherwise
        """
        # GRAPH-NATIVE: Task knowledge relationships not accessible via GraphQL context.
        # GraphQL context lacks tasks_backend — relationship data lives in Neo4j graph,
        # queried via TasksService, not exposed here.
        return None

    # ========================================================================
    # LEARNING PATH QUERIES
    # ========================================================================

    @staticmethod
    async def get_learning_path_steps(
        context: GraphQLContext, path_uid: str
    ) -> list[dict[str, Any]]:
        """
        Get learning path steps with knowledge units.

        Returns steps with embedded knowledge data for efficient GraphQL resolution.

        Args:
            context: GraphQL execution context
            path_uid: Learning path UID

        Returns:
            List of step dictionaries with knowledge data
        """
        # Get learning path
        path = await context.learning_path_loader.load(path_uid)
        if not path or not path.steps:
            return []

        # DataLoader automatically batches individual load() calls
        steps_data = []
        for i, step in enumerate(path.steps):
            # GRAPH-NATIVE: Use primary_knowledge_uids (plural) instead of knowledge_uid
            primary_ku = step.primary_knowledge_uids[0] if step.primary_knowledge_uids else None
            step_data = {
                "step_number": i + 1,
                "knowledge_uid": primary_ku,
                "mastery_threshold": step.mastery_threshold or 0.7,
                "estimated_time": step.estimated_time or 1.0,
            }

            # Load knowledge via DataLoader
            if primary_ku:
                ku = await context.knowledge_loader.load(primary_ku)
                if ku:
                    step_data["knowledge"] = {
                        "uid": ku.uid,
                        "title": ku.title,
                        "summary": ku.summary or "",
                        "domain": ku.domain.value,
                        "tags": ku.tags or [],
                        "quality_score": ku.quality_score,
                    }

            steps_data.append(step_data)

        logger.debug(f"Loaded {len(steps_data)} steps for learning path {path_uid}")
        return steps_data


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "GraphQLQueryHelpers",
]
