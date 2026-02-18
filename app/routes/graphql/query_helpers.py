"""
GraphQL Query Helpers
=====================

GraphQL-optimized query helpers using QueryPatterns.

These helpers are specifically designed for GraphQL resolvers:
- Leverage DataLoaders for batching (prevent N+1 queries)
- Return GraphQL types directly
- Use GraphQLContext infrastructure
- Optimize for nested resolver patterns
- Standardized via QueryPatterns

Created: October 21, 2025
"""

from typing import TYPE_CHECKING, Any

from core.constants import GraphDepth
from core.models.query import QueryPatterns
from core.utils.logging import get_logger
from routes.graphql.context import GraphQLContext

if TYPE_CHECKING:
    from routes.graphql.types import KnowledgeNode

logger = get_logger("skuel.graphql.query_helpers")


class GraphQLQueryHelpers:
    """
    Query helpers optimized for GraphQL patterns.

    All methods use QueryPatterns for standardized query building
    and integrate with DataLoaders for N+1 prevention.
    """

    # ========================================================================
    # KNOWLEDGE RELATIONSHIP QUERIES
    # ========================================================================

    @staticmethod
    async def get_prerequisites(context: GraphQLContext, ku_uid: str) -> list["KnowledgeNode"]:
        """
        Get prerequisite knowledge units for GraphQL resolver.

        Optimized for GraphQL:
        - Uses QueryPatterns for standardized prerequisite chain query
        - Integrates with DataLoader for batching
        - Returns GraphQL types directly
        - Gets only direct prerequisites (GraphQL handles deeper nesting)

        Args:
            context: GraphQL execution context (with DataLoaders)
            ku_uid: Knowledge unit UID

        Returns:
            List of KnowledgeNode objects for prerequisites

        Example GraphQL query:
            query {
              knowledge_unit(uid: "ku.123") {
                prerequisites {
                  uid
                  title
                  prerequisites {  # GraphQL handles nesting
                    uid
                    title
                  }
                }
              }
            }
        """
        # Step 1: Get prerequisite UIDs using QueryPatterns
        # Only direct prerequisites (GraphDepth.DIRECT) - GraphQL nesting handles deeper levels
        query, params = QueryPatterns.get_prerequisite_chain(
            entity_label="Ku",
            entity_uid=ku_uid,
            relationship_type="REQUIRES",
            max_depth=GraphDepth.DIRECT,  # Direct prerequisites only
            user_uid=context.user_uid,  # Include mastery status
        )

        # Execute query (using driver from context, not service internals)
        async with context.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

        # Step 2: Use DataLoader to batch load full entities
        # This prevents N+1 queries when loading multiple knowledge units
        from routes.graphql.types import KnowledgeNode

        prereqs = []
        for record in records:
            prereq_uid = record.get("entity_uid")
            if prereq_uid and prereq_uid != ku_uid:  # Skip self-reference
                # DataLoader batches this automatically!
                ku = await context.knowledge_loader.load(prereq_uid)
                if ku:
                    prereqs.append(
                        KnowledgeNode(
                            uid=ku.uid,
                            title=ku.title,
                            summary=ku.summary or "",
                            domain=ku.domain.value,
                            tags=ku.tags or [],
                            quality_score=ku.quality_score,
                        )
                    )

        logger.debug(f"Loaded {len(prereqs)} prerequisites for {ku_uid}")
        return prereqs

    @staticmethod
    async def get_enables(context: GraphQLContext, ku_uid: str) -> list["KnowledgeNode"]:
        """
        Get knowledge units enabled by this one (reverse prerequisites).

        Optimized for GraphQL with DataLoader batching.

        Args:
            context: GraphQL execution context
            ku_uid: Knowledge unit UID

        Returns:
            List of KnowledgeNode objects that this knowledge enables

        Example GraphQL query:
            query {
              knowledge_unit(uid: "ku.123") {
                enables {
                  uid
                  title
                }
              }
            }
        """
        # Get entities that require this knowledge (reverse relationship)
        query, params = QueryPatterns.get_entity_with_relationships(
            entity_label="Ku",
            entity_uid=ku_uid,
            rel_types=["REQUIRES"],
            rel_direction="incoming",  # Entities that point TO this one
        )

        async with context.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()

        if not record or not record.get("relationships"):
            return []

        # Extract UIDs of enabled knowledge units
        relationships = record["relationships"]
        enabled_uids = [
            rel.get("related_uid")
            for rel in relationships
            if rel.get("relationship_type") == "REQUIRES"
        ]

        # Use DataLoader to batch load entities
        from routes.graphql.types import KnowledgeNode

        enabled = []
        for uid in enabled_uids:
            if uid:
                ku = await context.knowledge_loader.load(uid)
                if ku:
                    enabled.append(
                        KnowledgeNode(
                            uid=ku.uid,
                            title=ku.title,
                            summary=ku.summary or "",
                            domain=ku.domain.value,
                            tags=ku.tags or [],
                            quality_score=ku.quality_score,
                        )
                    )

        logger.debug(f"Loaded {len(enabled)} enabled knowledge units for {ku_uid}")
        return enabled

    # ========================================================================
    # USER KNOWLEDGE QUERIES
    # ========================================================================

    @staticmethod
    async def get_user_mastered_knowledge(
        context: GraphQLContext, limit: int = 100
    ) -> list["KnowledgeNode"]:
        """
        Get user's mastered knowledge (GraphQL-optimized).

        Uses QueryPatterns for standardized user-entity relationship query.

        Args:
            context: GraphQL execution context
            limit: Maximum results to return

        Returns:
            List of KnowledgeNode objects user has mastered

        Example GraphQL query:
            query {
              user {
                mastered_knowledge(limit: 20) {
                  uid
                  title
                  domain
                }
              }
            }
        """
        if not context.user_uid:
            logger.warning("Attempted to get mastered knowledge without user_uid")
            return []

        # Get mastered knowledge via relationship
        query, params = QueryPatterns.get_user_entities(
            entity_label="Ku",
            user_uid=context.user_uid,
            relationship="MASTERED",
            order_by="r.achieved_at DESC",
            limit=limit,
        )

        async with context.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

        # Map to GraphQL types
        from routes.graphql.types import KnowledgeNode

        knowledge_nodes = []
        for record in records:
            node = record["e"]  # Entity from QueryPatterns
            knowledge_nodes.append(
                KnowledgeNode(
                    uid=node["uid"],
                    title=node["title"],
                    summary=node.get("summary", ""),
                    domain=node.get("domain", "knowledge"),
                    tags=node.get("tags", []),
                    quality_score=node.get("quality_score", 0.5),
                )
            )

        logger.debug(
            f"Loaded {len(knowledge_nodes)} mastered knowledge units for user {context.user_uid}"
        )
        return knowledge_nodes

    @staticmethod
    async def get_user_in_progress_knowledge(
        context: GraphQLContext, limit: int = 100
    ) -> list["KnowledgeNode"]:
        """
        Get user's in-progress knowledge (GraphQL-optimized).

        Args:
            context: GraphQL execution context
            limit: Maximum results to return

        Returns:
            List of KnowledgeNode objects user is currently learning
        """
        if not context.user_uid:
            return []

        query, params = QueryPatterns.get_user_entities(
            entity_label="Ku",
            user_uid=context.user_uid,
            relationship="IN_PROGRESS",
            order_by="r.last_accessed DESC",
            limit=limit,
        )

        async with context.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

        from routes.graphql.types import KnowledgeNode

        knowledge_nodes = []
        for record in records:
            node = record["e"]
            knowledge_nodes.append(
                KnowledgeNode(
                    uid=node["uid"],
                    title=node["title"],
                    summary=node.get("summary", ""),
                    domain=node.get("domain", "knowledge"),
                    tags=node.get("tags", []),
                    quality_score=node.get("quality_score", 0.5),
                )
            )

        logger.debug(
            f"Loaded {len(knowledge_nodes)} in-progress knowledge units for user {context.user_uid}"
        )
        return knowledge_nodes

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

        Example GraphQL query:
            query {
              task(uid: "task.123") {
                knowledge {
                  uid
                  title
                  prerequisites { uid title }
                }
              }
            }
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
