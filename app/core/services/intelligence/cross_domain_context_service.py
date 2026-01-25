"""
CrossDomainContextService
=========================

Unified service for cross-domain context retrieval and analysis.

Eliminates the duplicated pattern across 8 intelligence services:
    Fetch entity → Validate → Fetch context → Extract → Calculate → Build response

This single-call pattern replaces ~30-40 lines of boilerplate per method.

Usage:
    result = await context_service.analyze_with_context(
        entity_uid="task:123",
        backend=self.backend,
        relationships=self.relationships,
        context_method="get_task_cross_domain_context",
        context_type=TaskCrossContext,
        metrics_fn=calculate_task_metrics,
    )

Philosophy: "Fetch once, analyze completely"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Self


@runtime_checkable
class DictConvertible(Protocol):
    """Protocol for types that can be created from a dictionary.

    Used to constrain the context type (C) in CrossDomainContextService,
    ensuring type-safety when calling from_dict() on context types.
    """

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create instance from dictionary."""
        ...


T = TypeVar("T")  # Entity type
C = TypeVar("C", bound="DictConvertible")  # Context type with from_dict support


@dataclass
class ContextAnalysisResult[T, C: "DictConvertible"]:
    """
    Result of cross-domain context analysis.

    Contains:
    - entity: The domain entity being analyzed
    - context: Typed cross-domain context data
    - metrics: Calculated metrics about the entity in context
    - recommendations: Optional list of recommendations

    Usage:
        result = await context_service.analyze_with_context(...)
        if result.is_ok:
            analysis = result.value
            print(f"Entity: {analysis.entity.title}")
            print(f"Goal support: {analysis.context.supporting_goal_uids}")
            print(f"Metrics: {analysis.metrics}")
    """

    entity: T
    context: C
    metrics: dict[str, Any]
    recommendations: list[str]


class CrossDomainContextService:
    """
    Unified service for cross-domain context retrieval and analysis.

    This service consolidates the repeated pattern found in 23+ methods
    across 8 intelligence services, providing:

    1. fetch_typed_context() - Fetch context and convert to typed dataclass
    2. analyze_with_context() - Complete analysis: entity + context + metrics
    3. batch_analyze_with_context() - Batch analysis for multiple entities

    Benefits:
    - ~30-40 lines of boilerplate → 1 method call
    - Type-safe context dataclasses (IDE autocomplete, compile-time checks)
    - Consistent error handling across all domains
    - Pluggable metrics calculators per domain

    Architecture:
        Intelligence Services (TasksIntelligence, GoalsIntelligence, etc.)
            ↓
        CrossDomainContextService (this service)
            ↓
        Typed Context Dataclasses (TaskCrossContext, GoalCrossContext, etc.)
            ↓
        Relationship Services (get_*_cross_domain_context())


    Source Tag: "cross_domain_context_inferred"
    - Format: "cross_domain_context_inferred" for system-aggregated relationships
    - This service does not create relationships, only queries and aggregates them

    Confidence Scoring:
    - Inherits confidence from underlying relationship services
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from domain metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries (via delegation)
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    def __init__(self) -> None:
        """Initialize the service."""
        self.logger = get_logger("skuel.intelligence.cross_domain_context")

    async def fetch_typed_context(
        self,
        entity_uid: str,
        relationships: Any,
        context_method: str,
        context_type: type[C],
        **kwargs: Any,
    ) -> Result[C]:
        """
        Fetch cross-domain context and convert to typed dataclass.

        This method handles:
        1. Validation that relationships service exists
        2. Dynamic method lookup on relationships service
        3. Execution of context query
        4. Conversion from untyped dict to typed dataclass

        Args:
            entity_uid: UID of entity to fetch context for
            relationships: Relationship service instance
            context_method: Name of method on relationships service
                           (e.g., "get_task_cross_domain_context")
            context_type: Dataclass type to construct (must have from_dict classmethod)
            **kwargs: Additional args passed to context method (depth, min_confidence, etc.)

        Returns:
            Result containing typed context dataclass

        Example:
            context_result = await service.fetch_typed_context(
                entity_uid="task:123",
                relationships=self.relationships,
                context_method="get_task_cross_domain_context",
                context_type=TaskCrossContext,
                depth=2,
                min_confidence=0.8,
            )
            if context_result.is_ok:
                context = context_result.value
                print(f"Task has {len(context.prerequisite_task_uids)} prerequisites")
        """
        # Validate relationships service exists
        if relationships is None:
            return Result.fail(
                Errors.system(
                    message="Relationships service required for cross-domain context",
                    operation="fetch_typed_context",
                )
            )

        # Get the context method dynamically
        method = getattr(relationships, context_method, None)
        if method is None:
            return Result.fail(
                Errors.system(
                    message=f"Method {context_method} not found on relationships service",
                    operation="fetch_typed_context",
                )
            )

        # Fetch untyped context
        try:
            context_result = await method(entity_uid, **kwargs)
        except TypeError as e:
            # Handle case where method signature doesn't match kwargs
            self.logger.warning(f"Context method signature mismatch: {e}. Retrying without kwargs.")
            context_result = await method(entity_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        # Convert to typed dataclass using from_dict classmethod
        typed_context = context_type.from_dict(context_result.value)
        return Result.ok(typed_context)

    async def analyze_with_context(
        self,
        entity_uid: str,
        backend: Any,
        relationships: Any,
        context_method: str,
        context_type: type[C],
        metrics_fn: Callable[[Any, C], dict[str, Any]],
        recommendations_fn: Callable[[Any, C, dict[str, Any]], list[str]] | None = None,
        **context_kwargs: Any,
    ) -> Result[ContextAnalysisResult[Any, C]]:
        """
        Complete analysis pattern: fetch entity + context + calculate metrics.

        This single method replaces the 23 duplicated patterns across intelligence services.

        The pattern it replaces:
            1. Fetch entity from backend (5 lines)
            2. Validate relationships service (3 lines)
            3. Fetch cross-domain context (5 lines)
            4. Extract from untyped dict (8-15 lines)
            5. Calculate metrics (10-20 lines)
            6. Build response (15-25 lines)

        Total: ~30-40 lines → 1 method call

        Args:
            entity_uid: UID of entity to analyze
            backend: Domain backend for fetching entity (must have get() method)
            relationships: Relationship service for context
            context_method: Method name on relationships service
            context_type: Typed context dataclass with from_dict()
            metrics_fn: Function to calculate metrics: (entity, context) -> dict
            recommendations_fn: Optional function to generate recommendations:
                              (entity, context, metrics) -> list[str]
            **context_kwargs: Additional args for context method (depth, min_confidence)

        Returns:
            Result containing ContextAnalysisResult with entity, context, metrics,
            and recommendations

        Example:
            result = await context_service.analyze_with_context(
                entity_uid="goal:123",
                backend=self.backend,
                relationships=self.relationships,
                context_method="get_goal_cross_domain_context",
                context_type=GoalCrossContext,
                metrics_fn=calculate_goal_metrics,
                recommendations_fn=self._generate_goal_recommendations,
            )

            if result.is_ok:
                analysis = result.value
                return Result.ok({
                    "goal": analysis.entity,
                    "metrics": analysis.metrics,
                    "recommendations": analysis.recommendations,
                    "graph_context": analysis.context,
                })
        """
        # Step 1: Fetch entity
        entity_result = await backend.get(entity_uid)
        if entity_result.is_error:
            return Result.fail(entity_result.expect_error())
        entity = entity_result.value

        if entity is None:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))

        # Step 2: Fetch typed context
        context_result = await self.fetch_typed_context(
            entity_uid=entity_uid,
            relationships=relationships,
            context_method=context_method,
            context_type=context_type,
            **context_kwargs,
        )
        if context_result.is_error:
            return Result.fail(context_result.expect_error())
        context = context_result.value

        # Step 3: Calculate metrics
        metrics = metrics_fn(entity, context)

        # Step 4: Generate recommendations (optional)
        recommendations: list[str] = []
        if recommendations_fn:
            recommendations = recommendations_fn(entity, context, metrics)

        return Result.ok(
            ContextAnalysisResult(
                entity=entity,
                context=context,
                metrics=metrics,
                recommendations=recommendations,
            )
        )

    async def batch_analyze_with_context(
        self,
        entity_uids: list[str],
        backend: Any,
        relationships: Any,
        batch_context_method: str,
        context_type: type[C],
        metrics_fn: Callable[[Any, C], dict[str, Any]],
    ) -> Result[dict[str, ContextAnalysisResult[Any, C]]]:
        """
        Batch analysis for multiple entities (used by Finance, Events).

        Optimizes batch operations by:
        1. Fetching all entities in one query
        2. Fetching all contexts in one batch query
        3. Building results for each entity

        Args:
            entity_uids: List of entity UIDs to analyze
            backend: Domain backend (must have get_many() method)
            relationships: Relationship service (must have batch context method)
            batch_context_method: Batch method name on relationships
                                 (e.g., "batch_get_expense_cross_domain_context")
            context_type: Typed context dataclass with from_dict()
            metrics_fn: Function to calculate metrics for each entity

        Returns:
            Result containing dict mapping UID to ContextAnalysisResult

        Example:
            result = await context_service.batch_analyze_with_context(
                entity_uids=["expense:1", "expense:2", "expense:3"],
                backend=self.backend,
                relationships=self.relationships,
                batch_context_method="batch_get_expense_cross_domain_context",
                context_type=FinanceCrossContext,
                metrics_fn=calculate_finance_metrics,
            )

            if result.is_ok:
                for uid, analysis in result.value.items():
                    print(f"{uid}: {analysis.metrics['goal_impact']}")
        """
        if not entity_uids:
            return Result.ok({})

        # Step 1: Fetch all entities
        entities_result = await backend.get_many(entity_uids)
        if entities_result.is_error:
            return Result.fail(entities_result.expect_error())

        # Build UID -> entity mapping
        entities = {e.uid: e for e in entities_result.value if e is not None}

        # Step 2: Fetch all contexts in batch
        batch_method = getattr(relationships, batch_context_method, None)
        if batch_method is None:
            return Result.fail(
                Errors.system(
                    message=f"Batch method {batch_context_method} not found",
                    operation="batch_analyze_with_context",
                )
            )

        contexts_result = await batch_method(entity_uids)
        if contexts_result.is_error:
            return Result.fail(contexts_result.expect_error())
        contexts_dict = contexts_result.value

        # Step 3: Build results for each entity
        results: dict[str, ContextAnalysisResult[Any, C]] = {}
        for uid in entity_uids:
            entity = entities.get(uid)
            if entity is None:
                continue

            context_data = contexts_dict.get(uid, {})
            typed_context = context_type.from_dict(context_data)
            metrics = metrics_fn(entity, typed_context)

            results[uid] = ContextAnalysisResult(
                entity=entity,
                context=typed_context,
                metrics=metrics,
                recommendations=[],
            )

        return Result.ok(results)


# Singleton instance for easy access
_context_service: CrossDomainContextService | None = None


def get_context_service() -> CrossDomainContextService:
    """
    Get the singleton CrossDomainContextService instance.

    Usage:
        from core.services.intelligence.cross_domain_context_service import get_context_service

        context_service = get_context_service()
        result = await context_service.analyze_with_context(...)
    """
    global _context_service
    if _context_service is None:
        _context_service = CrossDomainContextService()
    return _context_service
