"""
GraphQL Context and DataLoader
===============================

Provides context management and DataLoader for N+1 query prevention.
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from strawberry.dataloader import DataLoader

from core.utils.logging import get_logger
from services_bootstrap import Services

logger = get_logger(__name__)

# Type alias for batch load functions: (list[str]) -> Result[list[T | None]]
type BatchLoadFn = Callable[[list[str]], Coroutine[Any, Any, Any]]


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

    # DataLoaders (created per request for batching)
    knowledge_loader: DataLoader[str, Any]
    task_loader: DataLoader[str, Any]
    learning_path_loader: DataLoader[str, Any]
    learning_step_loader: DataLoader[str, Any]

    # Request metadata (always set — auth enforced at HTTP layer)
    user_uid: str = ""


async def _batch_load(
    keys: list[str],
    batch_fn: BatchLoadFn,
    domain: str,
) -> list[Any]:
    """
    Shared batch loading logic for all DataLoaders.

    Handles Result unwrapping and error logging so individual loaders
    don't repeat this boilerplate.

    Args:
        keys: UIDs to batch load
        batch_fn: Bound batch method on the domain service
        domain: Domain name for log messages
    """
    logger.info(f"DataLoader batching {len(keys)} {domain}")

    result = await batch_fn(list(keys))

    if result.is_error:
        logger.error(f"Batch load {domain} failed: {result.error}")
        return [None] * len(keys)

    logger.info(f"Batch loaded {len(result.value)} {domain} in 1 query")
    return result.value


def create_graphql_context(
    services: Services,
    search_router: Any,
    user_uid: str = "",
) -> GraphQLContext:
    """
    Create GraphQL context with DataLoaders for a request.

    Args:
        services: Bootstrapped SKUEL services
        search_router: SearchRouter for search functionality (One Path Forward)
        user_uid: Authenticated user UID (required — auth enforced at HTTP layer)

    Returns:
        GraphQLContext with DataLoaders configured
    """
    # Create context first (with placeholder loaders)
    context = GraphQLContext(
        services=services,
        search_router=search_router,
        knowledge_loader=None,  # type: ignore[arg-type]  # Set below
        task_loader=None,  # type: ignore[arg-type]  # Set below
        learning_path_loader=None,  # type: ignore[arg-type]  # Set below
        learning_step_loader=None,  # type: ignore[arg-type]  # Set below
        user_uid=user_uid,
    )

    # Helper functions to bind context to batch loaders (SKUEL012: no lambdas)
    async def load_knowledge_units(keys: list[str]) -> list[Any]:
        return await _batch_load(
            keys, context.services.article.get_articles_batch, "knowledge units"
        )

    async def load_tasks(keys: list[str]) -> list[Any]:
        return await _batch_load(keys, context.services.tasks.get_tasks_batch, "tasks")

    async def load_learning_paths(keys: list[str]) -> list[Any]:
        return await _batch_load(
            keys, context.services.lp.get_learning_paths_batch, "learning paths"
        )

    async def load_learning_steps(keys: list[str]) -> list[Any]:
        return await _batch_load(
            keys, context.services.ls.get_learning_steps_batch, "learning steps"
        )

    # Create DataLoaders with named functions instead of lambdas
    context.knowledge_loader = DataLoader(load_fn=load_knowledge_units)
    context.task_loader = DataLoader(load_fn=load_tasks)
    context.learning_path_loader = DataLoader(load_fn=load_learning_paths)
    context.learning_step_loader = DataLoader(load_fn=load_learning_steps)

    return context
