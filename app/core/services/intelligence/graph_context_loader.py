"""
GraphContextLoader — fetch an entity and its graph context in one call.

Used by domain intelligence services to load `(entity, GraphContext)` tuples.
The intelligence service binds a backend get-method and a domain-model
converter at construction time; the loader runs a fetch + a single
intent-driven graph query against `GraphIntelligenceService`.

Replaces the former `GraphContextOrchestrator` — same behavior, typed
collaborators, no reflective `getattr` on the backend, no back-reference to
the owning service.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.enums import Domain
    from core.models.graph_context import GraphContext
    from core.models.query_types import QueryIntent
    from core.services.infrastructure.graph_intelligence_service import (
        GraphIntelligenceService,
    )


class SuggestsQueryIntent(Protocol):
    """Structural type for entities that can suggest a graph query intent."""

    def get_suggested_query_intent(self) -> QueryIntent: ...


type GetEntity[R] = Callable[[str], Awaitable[Result[R]]]
type ToDomain[R, T] = Callable[[R], T]


class GraphContextLoader[T: SuggestsQueryIntent]:
    """
    Loads `(entity, GraphContext)` for a single domain.

    Two collaborators, fixed two-step shape:
    1. Call the bound backend get-method.
    2. Convert the raw payload to a domain model.
    3. Call `graph_intel.query_with_intent` using either the caller-supplied
       intent or the model's `get_suggested_query_intent()`.

    The owning intelligence service binds `get_entity` and `to_domain` at
    construction time, so the loader holds no reference to the service.
    """

    def __init__(
        self,
        *,
        get_entity: GetEntity[Any],
        to_domain: ToDomain[Any, T],
        graph_intel: GraphIntelligenceService,
        domain: Domain,
        model_name: str,
    ) -> None:
        self.get_entity = get_entity
        self.to_domain = to_domain
        self.graph_intel = graph_intel
        self.domain = domain
        self.model_name = model_name
        self.logger = get_logger(f"skuel.services.intelligence.loader.{domain.value}")

    async def get_with_context(
        self,
        uid: str,
        depth: int = 2,
        intent: QueryIntent | None = None,
    ) -> Result[tuple[T, GraphContext]]:
        """
        Load the entity and its graph context.

        If `intent` is omitted, uses the entity's `get_suggested_query_intent()`.
        """
        loaded = await self._load(uid)
        if loaded.is_error:
            return Result.fail(loaded)
        entity = loaded.value

        chosen_intent = intent if intent is not None else entity.get_suggested_query_intent()

        self.logger.debug(
            f"Loading context for {self.model_name} {uid} "
            f"with intent {chosen_intent.value} at depth {depth}"
        )

        ctx_result = await self.graph_intel.query_with_intent(
            domain=self.domain, node_uid=uid, intent=chosen_intent, depth=depth
        )
        if ctx_result.is_error:
            return Result.fail(ctx_result)

        ctx = ctx_result.value
        elapsed = ctx.neo4j_query_time_ms or 0.0
        self.logger.debug(
            f"Context loaded for {self.model_name} {uid}: {ctx.total_nodes} nodes, {elapsed:.1f}ms"
        )
        return Result.ok((entity, ctx))

    async def _load(self, uid: str) -> Result[T]:
        entity_result = await self.get_entity(uid)
        if entity_result.is_error:
            return Result.fail(entity_result)
        if not entity_result.value:
            return Result.fail(Errors.not_found(resource=self.model_name, identifier=uid))
        return Result.ok(self.to_domain(entity_result.value))
