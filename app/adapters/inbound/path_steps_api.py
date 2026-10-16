"""
Path Steps API — Domain-Specific Routes
=========================================

Intelligence routes are config-driven via DomainRouteConfig in
path_steps_routes.py. This file contains the domain-specific reads:
prerequisites, relationships, search, analytics, adaptive curriculum and the
ORGANIZES hierarchy. Every route here reads; a path step is authored only in
the content vault (ADR-091).
"""

from typing import Any

from fasthtml.common import FT, Div, P
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.result_helpers import require_found
from adapters.inbound.route_factories import (
    parse_float_param_strict,
    parse_int_param_strict,
    refuse_malformed,
)
from core.constants import GraphDepth
from core.models.pathways.learning_progress import LearningJourney
from core.models.pathways.path_step import PathStep
from core.models.type_hints import UserUID
from core.ports.query_types import (
    OrganizerResult,
    PrerequisiteChainData,
    PrerequisiteChainNode,
    RootOrganizerResult,
)
from core.services.ps_service import PsService
from core.services.user_progress_service import UserProgressService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.feedback import Alert, AlertT

logger = get_logger("skuel.routes.path_steps.api")


def create_path_steps_api_routes(
    app: Any,
    rt: Any,
    ps_service: PsService,
    user_progress_service: UserProgressService,
) -> None:
    """
    Create path steps API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        ps_service: PsService instance
        user_progress_service: UserProgressService for per-caller mastery annotation
            on the prerequisite-chain read (REQUIRED — a missing progress service
            would silently mark every prerequisite unmastered; fail-fast instead)
    """

    # Step Prerequisites
    # ------------------

    @rt("/api/path-steps/prerequisites")
    @boundary_handler()
    async def get_step_prerequisites_route(
        request: Request, step_uid: str
    ) -> Result[PrerequisiteChainData]:
        """Get the transitive prerequisite chain for a path step.

        One variable-length traversal spanning REQUIRES_STEP (sequential) and
        REQUIRES_KNOWLEDGE (knowledge) prerequisites — the two dimensions this
        read formerly returned as separate 1-hop UID lists, now unified into one
        flat, distance-ranked chain (nearest-first, min-distance deduped). Each
        node is annotated with the requesting user's mastery.

        Args:
            step_uid: Target path step
            depth: Traversal depth (query, default 3; one that does not read or
                is below 1 is a 400, one above 10 is 10); depth=1 yields only
                immediate prerequisites.
        """
        user_uid = require_authenticated_user(request)
        depth_read = parse_int_param_strict(
            request.query_params.get("depth"),
            "depth",
            GraphDepth.DIRECT,
            default=GraphDepth.DEFAULT,
            cap=GraphDepth.MAXIMUM,
        )
        if depth_read.is_error:
            return Result.fail(depth_read)
        depth = depth_read.value

        # Existence gate: a missing/deleted step is 404, not a valid step with an
        # empty chain (the bare traversal can't tell those apart).
        found = require_found(await ps_service.get_step(step_uid), "PathStep", step_uid)
        if found.is_error:
            return Result.fail(found)

        chain_result = await ps_service.get_prerequisite_chain(step_uid, max_depth=depth)
        if chain_result.is_error:
            return Result.fail(chain_result)
        chain = chain_result.value

        # Mastery is the caller's only — one read, set-membership per node.
        # get_mastered_uids preserves the read's Result (unlike the resilient
        # build_user_knowledge_profile, which swallows sub-query errors), so a
        # failed mastery read fails the request instead of silently reporting
        # every node as unmastered.
        mastered_result = await user_progress_service.get_mastered_uids(user_uid)
        if mastered_result.is_error:
            return Result.fail(mastered_result)
        mastered_uids: set[str] = mastered_result.value

        nodes: list[PrerequisiteChainNode] = []
        mastered_count = 0
        for row in chain:
            is_mastered = row["uid"] in mastered_uids
            if is_mastered:
                mastered_count += 1
            nodes.append(
                PrerequisiteChainNode(
                    uid=row["uid"],
                    title=row["title"],
                    domain=row["domain"],
                    entity_type=row["entity_type"],
                    distance=row["distance"],
                    is_mastered=is_mastered,
                )
            )

        total = len(nodes)
        return Result.ok(
            PrerequisiteChainData(
                step_uid=step_uid,
                depth=depth,
                prerequisites=nodes,
                total_prerequisites=total,
                prerequisites_mastered=mastered_count,
                unmet_count=total - mastered_count,
                has_prerequisites=total > 0,
            )
        )

    # ========================================================================
    # SEMANTIC RELATIONSHIPS
    # ========================================================================

    @rt("/api/path-steps/relationships", methods=["GET"])
    @boundary_handler()
    async def get_step_relationships_route(
        request: Request, uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get relationships for a path step."""
        params = dict(request.query_params)
        relationship_type = params.get("type")

        return await ps_service.get_step_relationships(uid, relationship_type)

    @rt("/api/path-steps/dependencies")
    @boundary_handler()
    async def get_step_dependencies_route(request: Request, uid: str) -> Result[list[PathStep]]:
        """Get what depends on this path step."""
        return await ps_service.get_step_dependencies(uid)

    # ========================================================================
    # SEARCH & DISCOVERY
    # ========================================================================

    @rt("/api/path-steps/search")
    @boundary_handler()
    async def search_steps_route(request: Request) -> Result[list[Any]]:
        """Search path steps by content, title, or tags."""
        params = dict(request.query_params)
        query = params.get("q", "")
        limit = parse_int_param_strict(params.get("limit"), "limit", 1, default=50, cap=100)
        if limit.is_error:
            return Result.fail(limit)

        return await ps_service.search_steps(query, limit.value)

    @rt("/api/path-steps/related")
    @boundary_handler()
    async def find_related_steps_route(request: Request, uid: str) -> Result[list[PathStep]]:
        """Find path steps related to the given one."""
        params = dict(request.query_params)
        similarity_threshold = parse_float_param_strict(
            params.get("threshold"), "threshold", default=0.7, min_val=0.0, max_val=1.0
        )
        if similarity_threshold.is_error:
            return Result.fail(similarity_threshold)
        limit = parse_int_param_strict(params.get("limit"), "limit", 1, default=10, cap=500)
        if limit.is_error:
            return Result.fail(limit)

        return await ps_service.find_related_steps(uid, similarity_threshold.value, limit.value)

    @rt("/api/path-steps/recommendations")
    @boundary_handler()
    async def get_step_recommendations_route(request: Request, uid: str) -> Result[list[PathStep]]:
        """Get personalized path step recommendations."""
        params = dict(request.query_params)
        raw_user_uid = params.get("user_uid")
        user_uid = UserUID(raw_user_uid) if raw_user_uid else None
        recommendation_type = params.get("type", "learning")

        return await ps_service.get_step_recommendations(uid, user_uid, recommendation_type)

    # ========================================================================
    # ORGANIZATION — DOMAINS, CATEGORIES, TAGS
    # ========================================================================

    @rt("/api/path-steps/domains")
    @boundary_handler()
    async def list_step_domains_route(  # skuel-lint: disable=SKUEL029 -- FastHTML route handler: async is the router contract
        _request: Request,
    ) -> Result[list[str]]:
        """List all path step domains."""
        return ps_service.list_step_domains()

    @rt("/api/path-steps/categories")
    @boundary_handler()
    async def list_step_categories_route(_request: Request) -> Result[list[str]]:
        """List all path step categories."""
        return await ps_service.list_step_categories()

    @rt("/api/path-steps/all-tags")
    @boundary_handler()
    async def list_step_tags_route(request: Request) -> Result[list[dict[str, Any]]]:
        """List all path step tags with usage counts."""
        params = dict(request.query_params)
        min_usage = parse_int_param_strict(params.get("min_usage"), "min_usage", 0, default=1)
        if min_usage.is_error:
            return Result.fail(min_usage)

        return await ps_service.list_step_tags(min_usage.value)

    # ========================================================================
    # ANALYTICS
    # ========================================================================

    @rt("/api/path-steps/stats")
    @boundary_handler()
    async def get_step_stats_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get statistics for a path step."""
        return await ps_service.get_step_stats(uid)

    # ========================================================================
    # USER CONTEXT — Per-user substance & activity
    # ========================================================================

    @rt("/api/path-steps/my-context")
    @boundary_handler()
    async def get_step_user_context_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get personalized context for how the current user applies this path step."""
        user_uid = require_authenticated_user(request)

        # Fail-fast: PsService is always composed with user_service
        # (services_bootstrap/_learning_services.py) — no per-request guard.
        assert ps_service.user_service is not None, "PsService.user_service must be wired"
        # RICH, not standard. The six activity→knowledge maps the substance
        # score reads are populated only by build_rich; the standard build
        # leaves them empty, so this endpoint answered a confident all-zero
        # breakdown for every step and every learner.
        context_result = await ps_service.user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result)

        user_context = context_result.value
        return await ps_service.get_user_step_context(uid, user_context)

    # ========================================================================
    # ADAPTIVE CURRICULUM / SEL
    # ========================================================================

    @rt("/api/path-steps/journey")
    @boundary_handler()
    async def get_step_journey(request: Request) -> Result[LearningJourney]:
        """Get user's SEL learning journey — progress across all 5 categories."""
        user_uid = require_authenticated_user(request)
        return await ps_service.get_sel_journey(user_uid)

    @rt("/api/path-steps/curriculum/{category}")
    @boundary_handler()
    async def get_personalized_curriculum(request: Request, category: str) -> Result[list[Any]]:
        """Get personalized curriculum for an SEL category.

        ``limit`` is read from the query string (default 10; one that does not read
        or is below 1 is a 400).
        """
        from core.models.enums import SELCategory

        user_uid = require_authenticated_user(request)
        limit = parse_int_param_strict(request.query_params.get("limit"), "limit", 1, default=10)
        if limit.is_error:
            return Result.fail(limit)
        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Result.fail(Errors.validation(f"Invalid SEL category: {category}"))
        return await ps_service.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit.value
        )

    @rt("/api/path-steps/journey-html")
    async def get_step_journey_html(request: Request) -> FT:
        """HTMX: Render SEL journey as HTML fragment."""
        user_uid = require_authenticated_user(request)
        result = await ps_service.get_sel_journey(user_uid)

        if result.is_error:
            return Alert(
                P("Unable to load your learning journey.", cls="text-center py-8"),
                variant=AlertT.error,
            )

        from ui.patterns.curriculum_adaptive import SELJourneyOverview

        return SELJourneyOverview(result.value)

    @rt("/api/path-steps/curriculum-html/{category}")
    async def get_curriculum_html(request: Request, category: str) -> FT | Response:
        """HTMX: Render personalized curriculum grid as HTML fragment.

        ``limit`` is read from the query string (default 10; one that does not read
        or is below 1 is a bare 400).
        """
        from core.models.enums import SELCategory

        user_uid = require_authenticated_user(request)
        limit = parse_int_param_strict(request.query_params.get("limit"), "limit", 1, default=10)
        if limit.is_error:
            return refuse_malformed(limit.expect_error())

        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Alert(P(f"Invalid category: {category}"), variant=AlertT.error)

        result = await ps_service.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit.value
        )

        if result.is_error:
            return Alert(P("Unable to load curriculum."), variant=AlertT.error)

        curriculum: list[PathStep] = list(result.value or [])
        if not curriculum:
            from ui.patterns.empty_state import EmptyState

            return EmptyState(
                title="No curriculum available yet",
                description="Complete prerequisite knowledge units to unlock content in this area.",
                icon="📚",
            )

        from ui.patterns.curriculum_adaptive import AdaptiveKUCard

        return Div(
            *[AdaptiveKUCard(step) for step in curriculum],
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        )

    # ========================================================================
    # ORGANIZES HIERARCHY
    # ========================================================================

    # Identity Operations
    # -------------------

    @rt("/api/path-steps/{uid}/is-organizer")
    @boundary_handler()
    async def is_organizer_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Check if a path step has organized children."""
        result = await ps_service.is_organizer(uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"step_uid": uid, "is_organizer": result.value})

    @rt("/api/path-steps/{uid}/organization")
    @boundary_handler()
    async def get_organization_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get a path step with its organized children hierarchy."""
        result = await ps_service.get_organization_view(uid)
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=uid))
        return Result.ok(result.value.to_dict())

    # Discovery Operations
    # --------------------

    @rt("/api/path-steps/{uid}/organizers")
    @boundary_handler()
    async def find_organizers_route(request: Request, uid: str) -> Result[list[OrganizerResult]]:
        """Find all parent path steps that organize the given path step."""
        return await ps_service.find_organizers(uid)

    @rt("/api/path-steps/root-organizers")
    @boundary_handler()
    async def list_root_organizers_route(request: Request) -> Result[list[RootOrganizerResult]]:
        """List path steps that organize others but are not themselves organized."""
        params = dict(request.query_params)
        limit = parse_int_param_strict(params.get("limit"), "limit", 1, default=50, cap=500)
        if limit.is_error:
            return Result.fail(limit)
        return await ps_service.list_root_organizers(limit.value)

    @rt("/api/path-steps/{uid}/organized-children")
    @boundary_handler()
    async def get_organized_children_route(
        request: Request, uid: str
    ) -> Result[list[OrganizerResult]]:
        """Get direct children of a path step organized by ORGANIZES relationship."""
        return await ps_service.get_organized_children(uid)

    logger.info(
        "Path Steps domain routes registered "
        "(prerequisites, semantic, search, analytics, ORGANIZES hierarchy)"
    )


__all__ = ["create_path_steps_api_routes"]
