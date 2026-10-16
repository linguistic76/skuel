"""
LateralRouteFactory - Unified API Routes for Lateral Relationships
===================================================================

Provides HTMX-friendly endpoints for lateral relationships across all domains.

Read endpoints for all 9 domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP):
- GET /api/{domain}/{uid}/lateral/blocking - Get relationships that block this entity
- GET /api/{domain}/{uid}/lateral/blocked - Get relationships blocked by this entity
- GET /api/{domain}/{uid}/lateral/prerequisites - Get prerequisite relationships
- GET /api/{domain}/{uid}/lateral/alternatives - Get alternative relationships
- GET /api/{domain}/{uid}/lateral/complementary - Get complementary relationships
- GET /api/{domain}/{uid}/lateral/siblings - Get sibling relationships (derived from hierarchy)
- GET /api/{domain}/{uid}/lateral/chain - Blocking chain (HTML fragment)
- GET /api/{domain}/{uid}/lateral/alternatives/compare - Alternatives grid (HTML fragment)
- GET /api/{domain}/{uid}/lateral/graph - Relationship graph (Vis.js format)

Write endpoints for the 6 Activity Domains only (each endpoint ownership-verified):
- POST /api/{domain}/{uid}/lateral/blocks - Create blocking relationship
- POST /api/{domain}/{uid}/lateral/prerequisites - Create prerequisite relationship
- POST /api/{domain}/{uid}/lateral/alternatives - Create alternative relationship
- POST /api/{domain}/{uid}/lateral/complementary - Create complementary relationship
- DELETE /api/{domain}/{uid}/lateral/{type}/{target_uid} - Delete relationship
- GET /api/{domain}/{uid}/lateral/manage - Deletable edge list (HTML fragment)

Domain-specific routes can be added separately for unique relationship types:
- Habits: POST /api/habits/{uid}/lateral/stacks - Create habit stacking
- Habits: GET /api/habits/{uid}/lateral/stack - Get habit stack
- etc.

Usage:
    factory = LateralRouteFactory(
        domain="goals",
        lateral_service=lateral_service, # Core LateralRelationshipService
        entity_name="Goal",
        domain_service=goals_service, # For ownership verification
    )
    factory.register_routes(app, rt)

A curriculum domain (ku / ps / lp) passes ``domain_service=None`` and gets the
reads only, on an anchor the service holds to curriculum. Its edges are authored
in the content vault (ADR-091 S8).

See: /docs/architecture/RELATIONSHIPS_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any, TypedDict, cast

from fasthtml.common import FT

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories.route_helpers import (
    parse_float_param_strict,
    parse_int_param_strict,
)
from core.constants import GraphDepth
from core.models.enums.activity_enums import Priority
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, Neo4jProperties
from core.ports.query_types import (
    DerivedSiblingItem,
    LateralRelationshipItem,
    RelationshipGraphData,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.patterns.entity_links import entity_detail_href
from ui.patterns.relationships.alternatives_grid import render_alternatives_fragment
from ui.patterns.relationships.blocking_chain import render_chain_fragment
from ui.patterns.relationships.manage_list import (
    MANAGEABLE_TYPES,
    render_lateral_manage_fragment,
)

if TYPE_CHECKING:
    from core.ports.service_protocols import (
        LateralRelationshipOperations,
        OwnershipVerifier,
    )

logger = get_logger(__name__)

# Emitted by every lateral write (create/delete) so the shared readers and the
# relationship graph refresh off one DOM event. See LATERAL_RELATIONSHIPS_VISUALIZATION.md.
_RELATIONSHIPS_CHANGED_HEADERS: dict[str, str] = {"HX-Trigger": "relationships-changed"}


class _ChangedHeaders(TypedDict):
    """The ``_headers`` every lateral write answers with — popped into response headers."""

    _headers: dict[str, str]


class BlockingCreatedPayload(_ChangedHeaders):
    """``POST …/lateral/blocks`` — the BLOCKS edge written."""

    message: str
    blocker_uid: str
    blocked_uid: str


class PrerequisiteCreatedPayload(_ChangedHeaders):
    """``POST …/lateral/prerequisites`` — the PREREQUISITE_FOR edge written."""

    message: str
    prerequisite_uid: str
    dependent_uid: str


class PairCreatedPayload(_ChangedHeaders):
    """``POST …/lateral/alternatives`` and ``…/complementary`` — the symmetric edge written."""

    message: str
    entity_a_uid: str
    entity_b_uid: str


class LateralDeletedPayload(_ChangedHeaders):
    """``DELETE …/lateral/{type}/{target_uid}`` — the edge removed."""

    message: str
    source_uid: str
    target_uid: str


class BlockingPayload(TypedDict):
    """``GET …/lateral/blocking`` — the entities that block this one."""

    blocking: list[LateralRelationshipItem]
    count: int


class BlockedPayload(TypedDict):
    """``GET …/lateral/blocked`` — the entities this one blocks."""

    blocked: list[LateralRelationshipItem]
    count: int


class PrerequisitesPayload(TypedDict):
    """``GET …/lateral/prerequisites`` — prerequisite edges in either direction."""

    prerequisites: list[LateralRelationshipItem]
    count: int


class AlternativesPayload(TypedDict):
    """``GET …/lateral/alternatives`` — the entity's alternatives."""

    alternatives: list[LateralRelationshipItem]
    count: int


class ComplementaryPayload(TypedDict):
    """``GET …/lateral/complementary`` — the entities that complement this one."""

    complementary: list[LateralRelationshipItem]
    count: int


class SiblingsPayload(TypedDict):
    """``GET …/lateral/siblings`` — the entity's siblings (derived from the hierarchy by default)."""

    siblings: list[DerivedSiblingItem] | list[LateralRelationshipItem]
    count: int


def parse_edge_score(value: object, field: str, default: float) -> Result[float]:
    """A 0.0-1.0 score a lateral edge stores (``confidence``, ``strength``,
    ``synergy_score``): missing is ``default``; anything that is not a finite
    number in range is refused before the edge is written."""
    return parse_float_param_strict(value, field, default=default, min_val=0.0, max_val=1.0)


def _lateral_priority(raw: str) -> Result[str]:
    """The relationship's priority as a ``Priority`` member value.

    Lateral edges persist ``priority`` verbatim and the graph reads it back for
    edge width, so the vocabulary is enforced here, at the write: a value
    outside low / medium / high is a validation error, never a stored string.
    """
    try:
        return Result.ok(Priority(raw.strip().lower()).value)
    except ValueError:
        return Result.fail(
            Errors.validation("priority must be low, medium or high", field="priority")
        )


class LateralRouteFactory:
    """Factory for creating lateral relationship API routes."""

    def __init__(
        self,
        domain: str,  # "goals", "tasks", "habits", etc.
        lateral_service: LateralRelationshipOperations,
        entity_name: str,  # "Goal", "Task", "Habit", etc.
        domain_service: OwnershipVerifier | None = None,  # None = curriculum, reads only
    ) -> None:
        self.domain = domain
        self.lateral_service = lateral_service
        self.entity_name = entity_name
        self.domain_service = domain_service

    def register_routes(self, _app, rt) -> None:
        """Register this domain's lateral routes.

        Every domain gets the reads. Only a domain with an ownership verifier
        gets the writes and the manage list: a write joins two entities the
        caller owns, and curriculum has no owner (its edges are authored in the
        content vault, ADR-091 S8).
        """
        self._create_blocking_routes(rt)
        self._create_prerequisite_routes(rt)
        self._create_alternative_routes(rt)
        self._create_complementary_routes(rt)
        self._create_sibling_route(rt)
        # Enhanced UX routes
        self._create_chain_route(rt)
        self._create_comparison_route(rt)
        self._create_graph_route(rt)

        verifier = self.domain_service
        if verifier is None:
            return
        self._create_blocking_write_route(rt, verifier)
        self._create_prerequisite_write_route(rt, verifier)
        self._create_alternative_write_route(rt, verifier)
        self._create_complementary_write_route(rt, verifier)
        self._create_delete_route(rt, verifier)
        # Authoring: flat, deletable edit list
        self._create_manage_route(rt, verifier)

    def _create_blocking_routes(self, rt) -> None:
        """Create BLOCKS relationship routes."""

        # GET /api/{domain}/{uid}/lateral/blocking - Get entities that block this one
        @rt(f"/api/{self.domain}/{{uid}}/lateral/blocking", methods=["GET"])
        @boundary_handler()
        async def get_blocking(request: Request, uid: str) -> Result[BlockingPayload]:
            """Get entities that block this entity."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=EntityUID(uid),
                relationship_types=[RelationshipName.BLOCKS],
                direction="incoming",
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "blocking": result.value,
                    "count": len(result.value),
                }
            )

        # GET /api/{domain}/{uid}/lateral/blocked - Get entities blocked by this one
        @rt(f"/api/{self.domain}/{{uid}}/lateral/blocked", methods=["GET"])
        @boundary_handler()
        async def get_blocked(request: Request, uid: str) -> Result[BlockedPayload]:
            """Get entities blocked by this entity."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=EntityUID(uid),
                relationship_types=[RelationshipName.BLOCKS],
                direction="outgoing",
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "blocked": result.value,
                    "count": len(result.value),
                }
            )

    def _create_prerequisite_routes(self, rt) -> None:
        """Create PREREQUISITE_FOR relationship routes."""

        # GET /api/{domain}/{uid}/lateral/prerequisites - Get prerequisite entities
        @rt(f"/api/{self.domain}/{{uid}}/lateral/prerequisites", methods=["GET"])
        @boundary_handler()
        async def get_prerequisites(request: Request, uid: str) -> Result[PrerequisitesPayload]:
            """Get entities that are prerequisites for this entity."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=EntityUID(uid),
                relationship_types=[
                    RelationshipName.PREREQUISITE_FOR,
                    RelationshipName.REQUIRES_PREREQUISITE,
                ],
                direction="both",
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "prerequisites": result.value,
                    "count": len(result.value),
                }
            )

    def _create_alternative_routes(self, rt) -> None:
        """Create ALTERNATIVE_TO relationship routes."""

        # GET /api/{domain}/{uid}/lateral/alternatives - Get alternative entities
        @rt(f"/api/{self.domain}/{{uid}}/lateral/alternatives", methods=["GET"])
        @boundary_handler()
        async def get_alternatives(request: Request, uid: str) -> Result[AlternativesPayload]:
            """Get alternative entities."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=EntityUID(uid),
                relationship_types=[RelationshipName.ALTERNATIVE_TO],
                direction="both",
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "alternatives": result.value,
                    "count": len(result.value),
                }
            )

    def _create_complementary_routes(self, rt) -> None:
        """Create COMPLEMENTARY_TO relationship routes."""

        # GET /api/{domain}/{uid}/lateral/complementary - Get complementary entities
        @rt(f"/api/{self.domain}/{{uid}}/lateral/complementary", methods=["GET"])
        @boundary_handler()
        async def get_complementary(request: Request, uid: str) -> Result[ComplementaryPayload]:
            """Get complementary entities."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=EntityUID(uid),
                relationship_types=[RelationshipName.COMPLEMENTARY_TO],
                direction="both",
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "complementary": result.value,
                    "count": len(result.value),
                }
            )

    def _create_sibling_route(self, rt) -> None:
        """Create sibling relationship route (derived from hierarchy)."""

        # GET /api/{domain}/{uid}/lateral/siblings - Get sibling entities
        @rt(f"/api/{self.domain}/{{uid}}/lateral/siblings", methods=["GET"])
        @boundary_handler()
        async def get_siblings(request: Request, uid: str) -> Result[SiblingsPayload]:
            """Get sibling entities (same parent in hierarchy)."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_siblings(
                entity_uid=EntityUID(uid),
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "siblings": result.value,
                    "count": len(result.value),
                }
            )

    def _create_blocking_write_route(self, rt, verifier: OwnershipVerifier) -> None:
        """Create the blocking write route (an owned domain only)."""

        # POST /api/{domain}/{uid}/lateral/blocks - Create blocking relationship
        @rt(f"/api/{self.domain}/{{uid}}/lateral/blocks", methods=["POST"])
        @csrf_protected
        @boundary_handler(success_status=201)
        async def create_blocking(
            request: Request,
            uid: str,
            target_uid: str,
            reason: str,
            severity: str = "required",
            confidence: str | float | None = None,
            priority: str = "medium",
        ) -> Result[BlockingCreatedPayload]:
            """
            Create BLOCKS relationship.

            Args:
                uid: Blocker entity UID
                target_uid: Blocked entity UID
                reason: Why blocker must complete first
                severity: "required", "recommended", or "suggested"
                confidence: Certainty of this constraint (0.0-1.0; default 1.0 — hard constraints are explicit; anything else is refused)
                priority: Relative importance of this relationship (low/medium/high)
            """
            user_uid = require_authenticated_user(request)
            edge_priority = _lateral_priority(priority)
            if edge_priority.is_error:
                return Result.fail(edge_priority)
            confidence_score = parse_edge_score(confidence, "confidence", 1.0)
            if confidence_score.is_error:
                return Result.fail(confidence_score)

            result = await self.lateral_service.create_lateral_relationship(
                source_uid=uid,
                target_uid=target_uid,
                relationship_type=RelationshipName.BLOCKS,
                metadata={
                    "reason": reason,
                    "severity": severity,
                    "confidence": confidence_score.value,
                    "priority": edge_priority.value,
                    "domain": self.domain,
                    "created_by": user_uid,
                },
                user_uid=user_uid,
                domain_service=verifier,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "message": f"{self.entity_name} blocking relationship created",
                    "blocker_uid": uid,
                    "blocked_uid": target_uid,
                    "_headers": _RELATIONSHIPS_CHANGED_HEADERS,
                }
            )

    def _create_prerequisite_write_route(self, rt, verifier: OwnershipVerifier) -> None:
        """Create the prerequisite write route (an owned domain only)."""

        # POST /api/{domain}/{uid}/lateral/prerequisites - Create prerequisite relationship
        @rt(f"/api/{self.domain}/{{uid}}/lateral/prerequisites", methods=["POST"])
        @csrf_protected
        @boundary_handler(success_status=201)
        async def create_prerequisite(
            request: Request,
            uid: str,
            target_uid: str,
            strength: str | float | None = None,
            reasoning: str | None = None,
            confidence: str | float | None = None,
            priority: str = "medium",
        ) -> Result[PrerequisiteCreatedPayload]:
            """
            Create PREREQUISITE_FOR relationship.

            Args:
                uid: Prerequisite entity UID
                target_uid: Dependent entity UID
                strength: How essential prerequisite is (0.0-1.0; default 0.8)
                reasoning: Optional explanation
                confidence: Certainty of this prerequisite (0.0-1.0; default 1.0 — asserting a hard requirement)

            A score that is not a number in 0.0-1.0 is refused (400), nothing written.
                priority: Relative importance of this relationship (low/medium/high)
            """
            user_uid = require_authenticated_user(request)
            edge_priority = _lateral_priority(priority)
            if edge_priority.is_error:
                return Result.fail(edge_priority)
            strength_score = parse_edge_score(strength, "strength", 0.8)
            if strength_score.is_error:
                return Result.fail(strength_score)
            confidence_score = parse_edge_score(confidence, "confidence", 1.0)
            if confidence_score.is_error:
                return Result.fail(confidence_score)

            result = await self.lateral_service.create_lateral_relationship(
                source_uid=uid,
                target_uid=target_uid,
                relationship_type=RelationshipName.PREREQUISITE_FOR,
                metadata={
                    "strength": strength_score.value,
                    "reasoning": reasoning,
                    "confidence": confidence_score.value,
                    "priority": edge_priority.value,
                    "domain": self.domain,
                    "created_by": user_uid,
                },
                user_uid=user_uid,
                domain_service=verifier,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "message": f"{self.entity_name} prerequisite relationship created",
                    "prerequisite_uid": uid,
                    "dependent_uid": target_uid,
                    "_headers": _RELATIONSHIPS_CHANGED_HEADERS,
                }
            )

    def _create_alternative_write_route(self, rt, verifier: OwnershipVerifier) -> None:
        """Create the alternative write route (an owned domain only)."""

        # POST /api/{domain}/{uid}/lateral/alternatives - Create alternative relationship
        @rt(f"/api/{self.domain}/{{uid}}/lateral/alternatives", methods=["POST"])
        @csrf_protected
        @boundary_handler(success_status=201)
        async def create_alternative(
            request: Request,
            uid: str,
            target_uid: str,
            comparison_criteria: str,
            tradeoffs: list[str] | None = None,
            confidence: str | float | None = None,
            priority: str = "medium",
            timeframe: str = "",
            difficulty: str = "",
            resources: str = "",
        ) -> Result[PairCreatedPayload]:
            """
            Create ALTERNATIVE_TO relationship.

            ``timeframe`` / ``difficulty`` / ``resources`` are the comparison
            axis the alternatives grid renders as criteria rows — free text,
            compared side by side rather than parsed. They describe
            ``target_uid``, the alternative being added.

            A blank criterion is sent as ``None`` rather than omitted. The
            backend upserts with ``MERGE`` + ``SET r += $metadata``, so an
            omitted key would leave a previously authored value in place when
            the same pair is submitted again; a null removes the property, and
            the grid returns to "N/A".

            Args:
                uid: First entity UID
                target_uid: Alternative entity UID
                comparison_criteria: How to compare alternatives
                tradeoffs: Optional list of tradeoffs
                confidence: Certainty that these are genuine alternatives (0.0-1.0; default 0.8 — softer assertion; anything else is refused)
                priority: Relative importance of this relationship (low/medium/high)
                timeframe: How long this alternative takes (e.g. "about 18 months")
                difficulty: How hard it is (e.g. "steep at first")
                resources: What it costs to pursue (e.g. "one mentor plus a rowing machine")
            """
            user_uid = require_authenticated_user(request)
            edge_priority = _lateral_priority(priority)
            if edge_priority.is_error:
                return Result.fail(edge_priority)
            confidence_score = parse_edge_score(confidence, "confidence", 0.8)
            if confidence_score.is_error:
                return Result.fail(confidence_score)

            tradeoffs_widened: list[str | int | float] = list(tradeoffs) if tradeoffs else []
            metadata: Neo4jProperties = {
                "comparison_criteria": comparison_criteria,
                "tradeoffs": tradeoffs_widened,
                "confidence": confidence_score.value,
                "priority": edge_priority.value,
                "domain": self.domain,
                "created_by": user_uid,
            }
            for criterion, value in (
                ("timeframe", timeframe),
                ("difficulty", difficulty),
                ("resources", resources),
            ):
                metadata[criterion] = value or None
            result = await self.lateral_service.create_lateral_relationship(
                source_uid=uid,
                target_uid=target_uid,
                relationship_type=RelationshipName.ALTERNATIVE_TO,
                metadata=metadata,
                user_uid=user_uid,
                domain_service=verifier,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "message": f"{self.entity_name} alternative relationship created",
                    "entity_a_uid": uid,
                    "entity_b_uid": target_uid,
                    "_headers": _RELATIONSHIPS_CHANGED_HEADERS,
                }
            )

    def _create_complementary_write_route(self, rt, verifier: OwnershipVerifier) -> None:
        """Create the complementary write route (an owned domain only)."""

        # POST /api/{domain}/{uid}/lateral/complementary - Create complementary relationship
        @rt(f"/api/{self.domain}/{{uid}}/lateral/complementary", methods=["POST"])
        @csrf_protected
        @boundary_handler(success_status=201)
        async def create_complementary(
            request: Request,
            uid: str,
            target_uid: str,
            synergy_description: str,
            synergy_score: str | float | None = None,
            confidence: str | float | None = None,
            priority: str = "medium",
        ) -> Result[PairCreatedPayload]:
            """
            Create COMPLEMENTARY_TO relationship.

            Args:
                uid: First entity UID
                target_uid: Complementary entity UID
                synergy_description: How entities complement each other
                synergy_score: Strength of synergy (0.0-1.0; default 0.7)
                confidence: Certainty of this synergy (0.0-1.0; default 0.8 — softer assertion)

            A score that is not a number in 0.0-1.0 is refused (400), nothing written.
                priority: Relative importance of this relationship (low/medium/high)
            """
            user_uid = require_authenticated_user(request)
            edge_priority = _lateral_priority(priority)
            if edge_priority.is_error:
                return Result.fail(edge_priority)
            synergy = parse_edge_score(synergy_score, "synergy_score", 0.7)
            if synergy.is_error:
                return Result.fail(synergy)
            confidence_score = parse_edge_score(confidence, "confidence", 0.8)
            if confidence_score.is_error:
                return Result.fail(confidence_score)

            result = await self.lateral_service.create_lateral_relationship(
                source_uid=uid,
                target_uid=target_uid,
                relationship_type=RelationshipName.COMPLEMENTARY_TO,
                metadata={
                    "synergy_description": synergy_description,
                    "synergy_score": synergy.value,
                    "confidence": confidence_score.value,
                    "priority": edge_priority.value,
                    "domain": self.domain,
                    "created_by": user_uid,
                },
                user_uid=user_uid,
                domain_service=verifier,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "message": f"{self.entity_name} complementary relationship created",
                    "entity_a_uid": uid,
                    "entity_b_uid": target_uid,
                    "_headers": _RELATIONSHIPS_CHANGED_HEADERS,
                }
            )

    def _create_delete_route(self, rt, verifier: OwnershipVerifier) -> None:
        """Create route to delete lateral relationships."""

        # DELETE /api/{domain}/{uid}/lateral/{type}/{target_uid} - Delete relationship
        @rt(
            f"/api/{self.domain}/{{uid}}/lateral/{{relationship_type}}/{{target_uid}}",
            methods=["DELETE"],
        )
        @csrf_protected
        @boundary_handler()
        async def delete_lateral_relationship(
            request: Request,
            uid: str,
            relationship_type: str,
            target_uid: str,
        ) -> Result[LateralDeletedPayload]:
            """
            Delete lateral relationship.

            Args:
                uid: Source entity UID
                relationship_type: Type (blocks, prerequisites, alternatives, complementary)
                target_uid: Target entity UID
            """
            user_uid = require_authenticated_user(request)

            # Map route type to RelationshipName
            type_map = {
                "blocks": RelationshipName.BLOCKS,
                "prerequisites": RelationshipName.PREREQUISITE_FOR,
                "alternatives": RelationshipName.ALTERNATIVE_TO,
                "complementary": RelationshipName.COMPLEMENTARY_TO,
            }

            rel_name = type_map.get(relationship_type)
            if not rel_name:
                return Result.fail(
                    Errors.validation(f"Unsupported relationship type: {relationship_type}")
                )

            result = await self.lateral_service.delete_lateral_relationship(
                source_uid=uid,
                target_uid=target_uid,
                relationship_type=rel_name,
                user_uid=user_uid,
                domain_service=verifier,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                {
                    "message": f"{self.entity_name} {relationship_type} relationship deleted",
                    "source_uid": uid,
                    "target_uid": target_uid,
                    "_headers": _RELATIONSHIPS_CHANGED_HEADERS,
                }
            )

    # ========================================================================
    # Enhanced UX Routes
    # ========================================================================

    def _create_chain_route(self, rt) -> None:
        """Create route to get blocking chain with depth levels."""

        # GET /api/{domain}/{uid}/lateral/chain - Get transitive blocking chain
        @rt(f"/api/{self.domain}/{{uid}}/lateral/chain", methods=["GET"])
        @boundary_handler()
        async def get_chain(request: Request, uid: str) -> Result[FT]:
            """
            Get the transitive blocking chain, rendered as an HTML fragment.

            The BlockingChainView container HTMX-loads this and swaps it inline, so
            the route returns rendered HTML (Result[FT] → HTMLResponse), not JSON.

            Args:
                uid: Entity UID
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_blocking_chain(
                EntityUID(uid),
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(render_chain_fragment(cast("dict[str, Any]", result.value)))

    def _create_comparison_route(self, rt) -> None:
        """Create route to get alternatives with comparison data."""

        # GET /api/{domain}/{uid}/lateral/alternatives/compare - Get alternatives with comparison
        @rt(
            f"/api/{self.domain}/{{uid}}/lateral/alternatives/compare",
            methods=["GET"],
        )
        @boundary_handler()
        async def get_comparison(
            request: Request,
            uid: str,
        ) -> Result[FT]:
            """
            Get alternatives rendered as a side-by-side comparison HTML fragment.

            The AlternativesComparisonGrid container HTMX-loads this and swaps it
            inline, so the route returns rendered HTML (Result[FT] → HTMLResponse).

            The comparison criteria are fixed (see ``render_alternatives_fragment``)
            — there is no per-request field selection.

            Args:
                uid: Entity UID
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_alternatives_with_comparison(
                EntityUID(uid),
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(
                render_alternatives_fragment(cast("list[dict[str, Any]]", result.value))
            )

    def _create_graph_route(self, rt) -> None:
        """Create route to get relationship graph in Vis.js format."""

        # GET /api/{domain}/{uid}/lateral/graph - Get relationship graph
        @rt(f"/api/{self.domain}/{{uid}}/lateral/graph", methods=["GET"])
        @boundary_handler()
        async def get_graph(
            request: Request,
            uid: str,
            types: str | None = None,
        ) -> Result[RelationshipGraphData]:
            """
            Get relationship graph in Vis.js Network format.

            The knowledge-dependency view (formerly the GraphQL
            ``knowledge_dependencies`` query) is this route with
            ``?types=REQUIRES_KNOWLEDGE,ENABLES_KNOWLEDGE`` — the traversal is
            undirected, so it returns both prerequisites and dependents around
            the center, with node detail-page URLs.

            Args:
                uid: Center entity UID
                depth: Graph traversal depth (query; 1-3 recommended, default 2;
                    one that does not read, or is below 1, is a 400; one above
                    10 is 10)
                types: Comma-separated relationship types to include (optional;
                    any RelationshipName value, not just the 6 lateral types)

            Returns:
                Vis.js Network format (nodes and edges)
            """
            user_uid = require_authenticated_user(request)
            depth_read = parse_int_param_strict(
                request.query_params.get("depth"),
                "depth",
                GraphDepth.DIRECT,
                default=GraphDepth.NEIGHBORHOOD,
                cap=GraphDepth.MAXIMUM,
            )
            if depth_read.is_error:
                return Result.fail(depth_read)
            depth = depth_read.value

            # Parse relationship types if provided
            relationship_types = None
            if types:
                try:
                    relationship_types = [RelationshipName(t.strip()) for t in types.split(",")]
                except ValueError as e:
                    return Result.fail(Errors.validation(f"Invalid relationship type: {e!s}"))

            result = await self.lateral_service.get_relationship_graph(
                EntityUID(uid),
                depth,
                relationship_types,
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            # Enrich each node with its real detail-page URL (click-to-navigate).
            # URL knowledge is a UI/route concern — resolved here, not in core, from the
            # canonical entity_type property (never the Neo4j label, which isn't a route).
            # Types with no detail page get url=None; the graph's click handler no-ops on it.
            for node in result.value["nodes"]:
                node["url"] = entity_detail_href(node.get("entity_type"), node["id"])

            # Return Vis.js format directly (includes nodes and edges)
            return Result.ok(result.value)

    def _create_manage_route(self, rt, verifier: OwnershipVerifier) -> None:
        """Create the flat, deletable relationship-management list route (authoring)."""

        # GET /api/{domain}/{uid}/lateral/manage - Flat list of direct lateral edges
        @rt(f"/api/{self.domain}/{{uid}}/lateral/manage", methods=["GET"])
        @boundary_handler()
        async def get_manage_list(request: Request, uid: str) -> Result[FT]:
            """Owner-scoped flat list of an entity's direct lateral edges, with delete buttons.

            Drives the existing DELETE route for removals; refreshes on the shared
            ``relationships-changed`` event. Queries only the four primary (non-inverse)
            lateral types, both directions, so each authored edge appears once.
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=EntityUID(uid),
                relationship_types=list(MANAGEABLE_TYPES),
                direction="both",
                user_uid=user_uid,
                domain_service=verifier,
            )

            if result.is_error:
                return Result.fail(result)

            return Result.ok(render_lateral_manage_fragment(uid, self.domain, result.value))


__all__ = ["LateralRouteFactory", "parse_edge_score"]
