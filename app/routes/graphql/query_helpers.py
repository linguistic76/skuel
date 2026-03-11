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

from __future__ import annotations

from typing import TYPE_CHECKING

from core.utils.logging import get_logger
from routes.graphql.context import GraphQLContext

if TYPE_CHECKING:
    from core.utils.result_simplified import Result
    from routes.graphql.types import KnowledgeNode

from routes.graphql.mappers import knowledge_node_from_dto

logger = get_logger("skuel.graphql.query_helpers")


def unwrap_result[T](result: Result[T], fallback: T) -> T:
    """Return result value, or fallback on error/None."""
    if result.is_error or not result.value:
        return fallback
    return result.value


def unwrap_list[T](result: Result[list[T]]) -> list[T]:
    """Unwrap a Result containing a list. Returns [] on error or None."""
    if result.is_error or not result.value:
        return []
    return result.value


def unwrap_optional[T](result: Result[T]) -> T | None:
    """Unwrap a Result to its value or None."""
    if result.is_error:
        return None
    return result.value


class GraphQLQueryHelpers:
    """
    Query helpers optimized for GraphQL patterns.

    All methods delegate to service layer methods — no direct Cypher.
    """

    # ========================================================================
    # KNOWLEDGE RELATIONSHIP QUERIES
    # ========================================================================

    @staticmethod
    async def get_prerequisites(context: GraphQLContext, ku_uid: str) -> list[KnowledgeNode]:
        """
        Get prerequisite knowledge units for GraphQL resolver.

        Delegates to ArticleService.get_prerequisites() which returns
        Result[list[CurriculumDTO]].
        """
        if not context.services.article:
            return []

        result = await context.services.article.get_prerequisites(ku_uid)
        dtos = unwrap_result(result, [])
        prereqs = [knowledge_node_from_dto(dto) for dto in dtos]
        logger.debug(f"Loaded {len(prereqs)} prerequisites for {ku_uid}")
        return prereqs

    @staticmethod
    async def get_enables(context: GraphQLContext, ku_uid: str) -> list[KnowledgeNode]:
        """
        Get knowledge units enabled by this one (reverse prerequisites).

        Delegates to ArticleService.get_enables() which returns
        Result[list[CurriculumDTO]].
        """
        if not context.services.article:
            return []

        result = await context.services.article.get_enables(ku_uid)
        dtos = unwrap_result(result, [])
        enabled = [knowledge_node_from_dto(dto) for dto in dtos]
        logger.debug(f"Loaded {len(enabled)} enabled knowledge units for {ku_uid}")
        return enabled

    # ========================================================================
    # TASK KNOWLEDGE RELATIONSHIPS
    # ========================================================================

    @staticmethod
    async def get_task_knowledge(context: GraphQLContext, task_uid: str) -> KnowledgeNode | None:
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


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "GraphQLQueryHelpers",
    "unwrap_list",
    "unwrap_optional",
    "unwrap_result",
]
