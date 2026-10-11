"""
Generic Relationships Fetcher - DRY Pattern for Domain Relationships
=====================================================================

Provides a reusable utility for fetching relationship data in parallel
across all activity domains (Tasks, Goals, Events, Habits, Choices, Principles).

This eliminates the repeated asyncio.gather() + Result unpacking pattern
found in each domain's *Relationships.fetch() classmethod.

Usage Pattern:
--------------
    # Define query specs as (field_name, service_method) tuples
    QUERY_SPECS = [
        ("subtask_uids", "get_task_subtasks"),
        ("applies_knowledge_uids", "get_task_knowledge"),
        # ... more fields
    ]

    @classmethod
    async def fetch(cls, uid: str, service: SomeRelationshipService) -> Self:
        return await fetch_relationships_parallel(
            uid=uid,
            service=service,
            query_specs=QUERY_SPECS,
            dataclass_type=cls,
        )

Benefits:
---------
- Single implementation of asyncio.gather() pattern
- Consistent Result[T] unpacking with empty list fallback
- Type-safe dataclass construction
- ~25-35 lines saved per domain (6 domains = ~150-210 lines total)

Philosophy: "Relationships ARE the data structure, not serialized lists"
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import fields
from typing import Any, Protocol, TypeVar

from core.utils.result_simplified import Result

T = TypeVar("T")


class KeyedBatchReader(Protocol):
    """The keyed batch read ``fetch_relationships_batch`` runs once per key."""

    async def batch_get_related_uids(
        self, relationship_key: str, entity_uids: list[str]
    ) -> Result[dict[str, list[str]]]: ...


async def fetch_relationships_parallel[T](
    uid: str,
    service: Any,
    query_specs: list[tuple[str, str]],
    dataclass_type: type[T],
) -> T:
    """
    Fetch all relationship data from graph in parallel and construct dataclass.

    Executes N graph queries concurrently using asyncio.gather() for optimal
    performance, then unpacks Result[T] objects into dataclass fields.

    Args:
        uid: Entity UID to fetch relationships for
        service: Relationship service instance (provides query methods)
        query_specs: List of (field_name, method_name) tuples defining queries
        dataclass_type: The dataclass type to construct with results

    Returns:
        Instance of dataclass_type with all relationship data populated

    Example:
        QUERY_SPECS = [
            ("subtask_uids", "get_task_subtasks"),
            ("applies_knowledge_uids", "get_task_knowledge"),
        ]

        result = await fetch_relationships_parallel(
            uid="task_123",
            service=tasks_relationship_service,
            query_specs=QUERY_SPECS,
            dataclass_type=TaskRelationships,
        )

    Performance:
        - N parallel queries vs N sequential = ~60-70% faster
        - Single fetch vs per-method queries = 40-60% improvement

    Error Handling:
        - Each query that fails returns empty list (graceful degradation)
        - Errors are logged but don't fail the entire fetch
    """
    # Build list of coroutines from query specs
    # Support both old method-based and new key-based patterns
    coroutines = []
    for _field_name, method_name_or_key in query_specs:
        # Check if service has the method directly (old pattern)
        method = getattr(service, method_name_or_key, None)
        if method is not None:
            coroutines.append(method(uid))
        # Otherwise use get_related_uids with the key (new UnifiedRelationshipService pattern)
        else:
            get_related_uids = getattr(service, "get_related_uids", None)
            if get_related_uids is not None:
                coroutines.append(get_related_uids(method_name_or_key, uid))
            else:
                # Fallback: return empty result
                async def empty_result() -> (
                    Result
                ):  # skuel-lint: disable=SKUEL029 -- appended to coroutines list passed to asyncio.gather
                    return Result.ok([])

                coroutines.append(empty_result())

    # Execute all queries in parallel
    results: list[Result[Any]] = await asyncio.gather(*coroutines)

    # Extract values from Result[T], defaulting to empty list on error
    kwargs: dict[str, Any] = {}
    for (field_name, _method_name), result in zip(query_specs, results, strict=False):
        kwargs[field_name] = result.value if result.is_ok else []

    # Construct and return the dataclass
    return dataclass_type(**kwargs)


async def fetch_relationships_batch[T](
    uids: Sequence[str],
    service: KeyedBatchReader,
    query_specs: list[tuple[str, str]],
    dataclass_type: type[T],
) -> Result[dict[str, T]]:
    """
    Fetch the relationship data of many entities: one query per relationship key.

    The batch form of ``fetch_relationships_parallel`` for a fan-out over many
    uids — the query count is ``len(query_specs)`` whatever the number of uids.
    Each key resolves through the service's keyed batch read, so the edge type,
    direction, tier and far-end kind are the single read's.

    Args:
        uids: Entity UIDs to fetch relationships for (duplicates read once)
        service: Relationship service with ``batch_get_related_uids``
        query_specs: ``(field_name, relationship_key)`` tuples
        dataclass_type: The dataclass type to construct per uid

    Returns:
        Result mapping each uid to its dataclass; a failed read fails the whole batch.
    """
    distinct = list(dict.fromkeys(uids))
    if not distinct:
        return Result.ok({})

    results = await asyncio.gather(
        *[service.batch_get_related_uids(key, distinct) for _field_name, key in query_specs]
    )
    by_field: dict[str, dict[str, list[str]]] = {}
    for (field_name, _key), result in zip(query_specs, results, strict=True):
        if result.is_error:
            return Result.fail(result)
        by_field[field_name] = result.value

    return Result.ok(
        {
            uid: dataclass_type(
                **{field_name: related.get(uid, []) for field_name, related in by_field.items()}
            )
            for uid in distinct
        }
    )


def validate_query_specs(
    query_specs: list[tuple[str, str]],
    dataclass_type: type,
    service_type: type,
) -> list[str]:
    """
    Validate that query specs match dataclass fields and service methods.

    Used for development-time validation to catch mismatches early.

    Args:
        query_specs: List of (field_name, method_name) tuples
        dataclass_type: The dataclass type to validate against
        service_type: The service type to validate against

    Returns:
        List of validation error messages (empty if valid)

    Example:
        errors = validate_query_specs(
            TASK_QUERY_SPECS,
            TaskRelationships,
            UnifiedRelationshipService,
        )
        if errors:
            raise ValueError(f"Invalid query specs: {errors}")
    """
    errors = []
    dataclass_fields = {f.name for f in fields(dataclass_type)}

    for field_name, method_name in query_specs:
        # Check field exists in dataclass
        if field_name not in dataclass_fields:
            errors.append(f"Field '{field_name}' not found in {dataclass_type.__name__}")

        # Check method exists in service (if service_type provided)
        if service_type and getattr(service_type, method_name, None) is None:
            errors.append(f"Method '{method_name}' not found in {service_type.__name__}")

    return errors
