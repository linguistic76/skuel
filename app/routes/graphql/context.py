"""
GraphQL Context and DataLoader
===============================

Provides context management and DataLoader for N+1 query prevention.
"""

from dataclasses import dataclass
from typing import Any

from strawberry.dataloader import DataLoader

from core.utils.logging import get_logger
from core.utils.services_bootstrap import Services

logger = get_logger(__name__)


@dataclass
class GraphQLContext:
    """
    GraphQL execution context with service dependencies and DataLoaders.

    This context is created per request and includes:
    - All SKUEL services for resolvers to use
    - DataLoaders for batching and caching to prevent N+1 queries
    - SearchRouter for search functionality (One Path Forward, January 2026)
    """

    # Services (injected from bootstrap)
    services: Services

    # Search router (One Path Forward, January 2026)
    search_router: Any  # SearchRouter - THE search orchestrator

    # Neo4j driver (for query helpers that need direct graph access)
    driver: Any  # Neo4j driver instance

    # Knowledge backend (for flexible GraphQL queries - bypasses protocol layer)
    knowledge_backend: Any  # KnowledgeUniversalBackend

    # DataLoaders (created per request for batching)
    knowledge_loader: DataLoader[str, Any]
    task_loader: DataLoader[str, Any]
    learning_path_loader: DataLoader[str, Any]
    learning_step_loader: DataLoader[str, Any]  # NEW: Phase 4

    # Request metadata
    user_uid: str | None = None


async def batch_load_knowledge_units(keys: list[str], context: GraphQLContext) -> list[Any]:
    """
    Batch load knowledge units by UIDs with metrics logging.
    """
    logger.info(f"📊 DataLoader batching {len(keys)} knowledge units")

    if not context.services.ku:
        logger.warning("⚠️ Knowledge service not available for batch load")
        return [None] * len(keys)

    result = await context.services.ku.get_knowledge_units_batch(list(keys))  # type: ignore[attr-defined]

    if result.is_error:
        logger.error(f"❌ Batch load failed: {result.error}")
        return [None] * len(keys)

    logger.info(f"✅ Batch loaded {len(result.value)} knowledge units in 1 query")
    return result.value


async def batch_load_tasks(keys: list[str], context: GraphQLContext) -> list[Any]:
    """
    Batch load tasks by UIDs with metrics logging.
    """
    logger.info(f"📊 DataLoader batching {len(keys)} tasks")

    if not context.services.tasks:
        logger.warning("⚠️ Tasks service not available for batch load")
        return [None] * len(keys)

    result = await context.services.tasks.get_tasks_batch(list(keys))

    if result.is_error:
        logger.error(f"❌ Batch load failed: {result.error}")
        return [None] * len(keys)

    logger.info(f"✅ Batch loaded {len(result.value)} tasks in 1 query")
    return result.value


async def batch_load_learning_paths(keys: list[str], context: GraphQLContext) -> list[Any]:
    """
    Batch load learning paths by UIDs with metrics logging.
    """
    logger.info(f"📊 DataLoader batching {len(keys)} learning paths")

    if not context.services.learning_paths:
        logger.warning("⚠️ Learning paths service not available for batch load")
        return [None] * len(keys)

    result = await context.services.learning_paths.get_learning_paths_batch(list(keys))

    if result.is_error:
        logger.error(f"❌ Batch load failed: {result.error}")
        return [None] * len(keys)

    logger.info(f"✅ Batch loaded {len(result.value)} learning paths in 1 query")
    return result.value


async def batch_load_learning_steps(keys: list[str], context: GraphQLContext) -> list[Any]:
    """
    Batch load learning steps by UIDs with metrics logging.

    Phase 4: Prevents N+1 queries when loading steps for multiple paths.

    Args:
        keys: List of learning step UIDs to batch load
        context: GraphQL context with services

    Returns:
        List of LearningStep objects or None for missing steps
    """
    logger.info(f"📊 DataLoader batching {len(keys)} learning steps")

    if not context.services.learning_steps:
        logger.warning("⚠️ Learning steps service not available for batch load")
        return [None] * len(keys)

    # Try to batch load if service supports it
    # If not, fall back to individual loads
    try:
        result = await context.services.learning_steps.get_learning_steps_batch(list(keys))

        if result.is_error:
            logger.error(f"❌ Batch load failed: {result.error}")
            return [None] * len(keys)

        logger.info(f"✅ Batch loaded {len(result.value)} learning steps in 1 query")
        return result.value

    except AttributeError:
        # Fallback: Load individually (batch method not available)
        logger.warning("⚠️ Batch method not available, loading steps individually")
        steps = []
        for key in keys:
            result = await context.services.learning_steps.get(key)
            # Type-safe value extraction
            if result.is_ok:
                steps.append(result.value)
            else:
                steps.append(None)

        logger.info(f"✅ Loaded {len([s for s in steps if s])} learning steps individually")
        return steps

    except Exception as e:
        logger.error(f"❌ Error loading learning steps: {e}")
        return [None] * len(keys)


def create_graphql_context(
    services: Services,
    search_router: Any,
    driver: Any,
    knowledge_backend: Any,
    user_uid: str | None = None,
) -> GraphQLContext:
    """
    Create GraphQL context with DataLoaders for a request.

    Args:
        services: Bootstrapped SKUEL services
        search_router: SearchRouter for search functionality (One Path Forward)
        driver: Neo4j driver instance (for query helpers)
        knowledge_backend: KnowledgeUniversalBackend for flexible queries
        user_uid: Optional user ID for personalized queries

    Returns:
        GraphQLContext with DataLoaders configured
    """
    # Create context first (with placeholder loaders)
    context = GraphQLContext(
        services=services,
        search_router=search_router,
        driver=driver,
        knowledge_backend=knowledge_backend,
        knowledge_loader=None,  # type: ignore[arg-type]  # Set below
        task_loader=None,  # type: ignore[arg-type]  # Set below
        learning_path_loader=None,  # type: ignore[arg-type]  # Set below
        learning_step_loader=None,  # type: ignore[arg-type]  # Set below
        user_uid=user_uid,
    )

    # Helper functions to bind context to batch loaders
    # This pattern avoids lambda expressions while preserving functionality
    async def load_knowledge_units(keys: list[str]) -> list[Any]:
        return await batch_load_knowledge_units(keys, context)

    async def load_tasks(keys: list[str]) -> list[Any]:
        return await batch_load_tasks(keys, context)

    async def load_learning_paths(keys: list[str]) -> list[Any]:
        return await batch_load_learning_paths(keys, context)

    async def load_learning_steps(keys: list[str]) -> list[Any]:
        return await batch_load_learning_steps(keys, context)

    # Create DataLoaders with named functions instead of lambdas
    context.knowledge_loader = DataLoader(load_fn=load_knowledge_units)
    context.task_loader = DataLoader(load_fn=load_tasks)
    context.learning_path_loader = DataLoader(load_fn=load_learning_paths)
    context.learning_step_loader = DataLoader(load_fn=load_learning_steps)

    return context
