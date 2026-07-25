"""
Path Steps API — Domain-Specific Routes
=========================================

CRUD and Intelligence routes are config-driven via DomainRouteConfig
in path_steps_routes.py. This file contains domain-specific manual routes:
relationships, content, search, organization, analytics, adaptive curriculum,
and ORGANIZES hierarchy operations.
"""

from typing import Any

from fasthtml.common import Div, P, Request

from adapters.inbound.auth import make_service_getter, require_admin, require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.result_helpers import require_found
from adapters.inbound.route_factories import parse_int_query_param
from adapters.inbound.route_factories.analytics_route_factory import AnalyticsRouteFactory
from core.constants import GraphDepth
from core.models.entity_requests import AddTagsRequest, RemoveTagsRequest
from core.models.pathways.learning_progress import LearningJourney
from core.models.pathways.path_step import PathStep
from core.models.pathways.pathways_request import (
    PathStepPathRequest,
    StepContentUpdateRequest,
    StepOrganizeRequest,
    StepRelationshipCreateRequest,
    StepReorderRequest,
)
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
    user_service: Any = None,
) -> list[Any]:
    """
    Create path steps API routes using factory pattern.

    SECURITY: CRUD write operations (create, update, delete) require ADMIN role.
    Read operations (get, list) are public.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        ps_service: PsService instance
        user_progress_service: UserProgressService for per-caller mastery annotation
            on the prerequisite-chain read (REQUIRED — a missing progress service
            would silently mark every prerequisite unmastered; fail-fast instead)
        user_service: User service for admin role verification
    """

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # STEP-PATH RELATIONSHIPS
    # ========================================================================

    @rt("/api/path-steps/attach-to-path", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def attach_step_to_path_route(
        request: Request, step_uid: str, current_user: Any = None
    ) -> Result[bool]:
        """Attach a path step to a learning path. Requires ADMIN role (curriculum write)."""
        result = await parse_json_body(request, PathStepPathRequest)
        if result.is_error:
            return result  # type: ignore[return-value]

        return await ps_service.attach_step_to_path(
            step_uid, result.value.path_uid, result.value.sequence
        )

    @rt("/api/path-steps/detach-from-path", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def detach_step_from_path_route(
        request: Request, step_uid: str, current_user: Any = None
    ) -> Result[bool]:
        """Detach a path step from a learning path. Requires ADMIN role (curriculum write)."""
        result = await parse_json_body(request, PathStepPathRequest)
        if result.is_error:
            return result  # type: ignore[return-value]

        return await ps_service.detach_step_from_path(step_uid, result.value.path_uid)

    # Step Prerequisites
    # ------------------

    @rt("/api/path-steps/prerequisites")
    @boundary_handler()
    async def get_step_prerequisites_route(
        request: Request, step_uid: str, depth: int = GraphDepth.DEFAULT
    ) -> Result[PrerequisiteChainData]:
        """Get the transitive prerequisite chain for a path step.

        One variable-length traversal spanning REQUIRES_STEP (sequential) and
        REQUIRES_KNOWLEDGE (knowledge) prerequisites — the two dimensions this
        read formerly returned as separate 1-hop UID lists, now unified into one
        flat, distance-ranked chain (nearest-first, min-distance deduped). Each
        node is annotated with the requesting user's mastery.

        Args:
            step_uid: Target path step
            depth: Traversal depth (1-10, default 3); depth=1 yields only
                immediate prerequisites.
        """
        user_uid = require_authenticated_user(request)

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
                depth=max(1, min(depth, GraphDepth.MAXIMUM)),
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

    @rt("/api/path-steps/relationships", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def create_step_relationship_route(
        request: Request, uid: str, current_user: Any = None
    ) -> Result[bool]:
        """Create a semantic relationship between path steps. Requires ADMIN role."""
        result = await parse_json_body(request, StepRelationshipCreateRequest)
        if result.is_error:
            return result  # type: ignore[return-value]
        req = result.value

        # Keyword args: req.description maps to `notes`; `confidence` keeps
        # the service default. The prior positional call passed strength as
        # confidence and description as strength — a real bug, latent only
        # because the endpoint was rarely exercised.
        return await ps_service.create_step_relationship(
            source_uid=uid,
            target_uid=req.target_uid,
            relationship_type=req.type,
            strength=req.strength,
            notes=req.description or None,
        )

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
    # CONTENT OPERATIONS
    # ========================================================================

    @rt("/api/path-steps/content", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def update_step_content_route(
        request: Request, uid: str, current_user: Any = None
    ) -> Result[PathStep]:
        """Update path step content. Requires ADMIN role."""
        result = await parse_json_body(request, StepContentUpdateRequest)
        if result.is_error:
            return result  # type: ignore[return-value]

        return await ps_service.update_step_content(uid, result.value.content, result.value.title)

    @rt("/api/path-steps/tags", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def add_step_tags_route(
        request: Request, uid: str, current_user: Any = None
    ) -> Result[PathStep]:
        """Add tags to a path step. Requires ADMIN role."""
        result = await parse_json_body(request, AddTagsRequest)
        if result.is_error:
            return result  # type: ignore[return-value]

        return await ps_service.add_step_tags(uid, result.value.tags)

    @rt("/api/path-steps/tags", methods=["DELETE"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def remove_step_tags_route(
        request: Request, uid: str, current_user: Any = None
    ) -> Result[PathStep]:
        """Remove tags from a path step. Requires ADMIN role."""
        result = await parse_json_body(request, RemoveTagsRequest)
        if result.is_error:
            return result  # type: ignore[return-value]

        return await ps_service.remove_step_tags(uid, result.value.tags)

    # ========================================================================
    # SEARCH & DISCOVERY
    # ========================================================================

    @rt("/api/path-steps/search")
    @boundary_handler()
    async def search_steps_route(request: Request) -> Result[list[Any]]:
        """Search path steps by content, title, or tags."""
        params = dict(request.query_params)
        query = params.get("q", "")
        limit = parse_int_query_param(params, "limit", 50, minimum=1, maximum=100)

        return await ps_service.search_steps(query, limit)

    @rt("/api/path-steps/related")
    @boundary_handler()
    async def find_related_steps_route(request: Request, uid: str) -> Result[list[PathStep]]:
        """Find path steps related to the given one."""
        params = dict(request.query_params)
        similarity_threshold = float(params.get("threshold", 0.7))
        limit = parse_int_query_param(params, "limit", 10, minimum=1, maximum=500)

        return await ps_service.find_related_steps(uid, similarity_threshold, limit)

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
        min_usage = parse_int_query_param(params, "min_usage", 1, minimum=0)

        return await ps_service.list_step_tags(min_usage)

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
        context_result = await ps_service.user_service.get_user_context(user_uid)
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
    async def get_personalized_curriculum(
        request: Request, category: str, limit: int = 10
    ) -> Result[list[Any]]:
        """Get personalized curriculum for an SEL category."""
        from core.models.enums import SELCategory

        user_uid = require_authenticated_user(request)
        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Result.fail(Errors.validation(f"Invalid SEL category: {category}"))
        return await ps_service.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit
        )

    @rt("/api/path-steps/journey-html")
    async def get_step_journey_html(request: Request) -> Any:
        """HTMX: Render SEL journey as HTML fragment."""
        from fasthtml.common import P as FP

        user_uid = require_authenticated_user(request)
        result = await ps_service.get_sel_journey(user_uid)

        if result.is_error:
            return Alert(
                FP("Unable to load your learning journey.", cls="text-center py-8"),
                variant=AlertT.error,
            )

        from ui.patterns.curriculum_adaptive import SELJourneyOverview

        return SELJourneyOverview(result.value)

    @rt("/api/path-steps/curriculum-html/{category}")
    async def get_curriculum_html(request: Request, category: str, limit: int = 10) -> Any:
        """HTMX: Render personalized curriculum grid as HTML fragment."""
        from core.models.enums import SELCategory

        user_uid = require_authenticated_user(request)

        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Alert(P(f"Invalid category: {category}"), variant=AlertT.error)

        result = await ps_service.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit
        )

        if result.is_error:
            return Alert(P("Unable to load curriculum."), variant=AlertT.error)

        curriculum: list[Any] = list(result.value or [])
        if not curriculum:
            from ui.patterns.empty_state import EmptyState

            return EmptyState(
                title="No curriculum available yet",
                description="Complete prerequisite knowledge units to unlock content in this area.",
                icon="📚",
            )

        from ui.patterns.curriculum_adaptive import AdaptiveKUCard

        return Div(
            *[AdaptiveKUCard(ku) for ku in curriculum],
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        )

    # ========================================================================
    # ANALYTICS ROUTES (Factory-Generated)
    # ========================================================================

    async def handle_summary_analytics(
        service: PsService, params: dict[str, str]
    ) -> Result[dict[str, Any]]:
        """Handle summary analytics for all path steps."""
        time_period = params.get("period", "month")
        return await service.get_step_stats(time_period)

    async def handle_graph_structure(
        service: PsService, params: dict[str, str]
    ) -> Result[dict[str, Any]]:
        """Handle path step graph structure and metrics."""
        include_metrics = params.get("metrics", "true").lower() == "true"
        return await service.get_step_stats(str(include_metrics))

    analytics_factory = AnalyticsRouteFactory(
        service=ps_service,
        domain_name="path-steps",
        analytics_config={
            "summary": {
                "path": "/api/path-steps/analytics/summary",
                "handler": handle_summary_analytics,
                "description": "Get summary analytics for all path steps",
                "methods": ["GET"],
            },
            "graph_structure": {
                "path": "/api/path-steps/graph/structure",
                "handler": handle_graph_structure,
                "description": "Get path step graph structure and metrics",
                "methods": ["GET"],
            },
        },
    )
    analytics_factory.register_routes(app, rt)

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

    # Organization Operations (ADMIN ONLY)
    # -------------------------------------

    @rt("/api/path-steps/organize", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler(success_status=201)
    async def organize_route(request: Request, current_user: Any = None) -> Result[dict[str, Any]]:
        """Organize a path step under another (create ORGANIZES relationship)."""
        parsed = await parse_json_body(request, StepOrganizeRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await ps_service.organize(req.parent_uid, req.child_uid, req.order)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            {"success": result.value, "parent_uid": req.parent_uid, "child_uid": req.child_uid}
        )

    @rt("/api/path-steps/unorganize", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def unorganize_route(
        request: Request, current_user: Any = None
    ) -> Result[dict[str, Any]]:
        """Remove organization relationship between path steps."""
        parsed = await parse_json_body(request, StepOrganizeRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await ps_service.unorganize(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"success": result.value})

    @rt("/api/path-steps/reorder", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def reorder_route(request: Request, current_user: Any = None) -> Result[dict[str, Any]]:
        """Change the order of a child path step within its parent."""
        parsed = await parse_json_body(request, StepReorderRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await ps_service.reorder(req.parent_uid, req.child_uid, req.new_order)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"success": result.value})

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
        limit = parse_int_query_param(params, "limit", 50, minimum=1, maximum=500)
        return await ps_service.list_root_organizers(limit)

    @rt("/api/path-steps/{uid}/organized-children")
    @boundary_handler()
    async def get_organized_children_route(
        request: Request, uid: str
    ) -> Result[list[OrganizerResult]]:
        """Get direct children of a path step organized by ORGANIZES relationship."""
        return await ps_service.get_organized_children(uid)

    logger.info(
        "Path Steps domain routes registered "
        "(step-path, semantic, content, search, organization, analytics, ORGANIZES hierarchy)"
    )

    return []


__all__ = ["create_path_steps_api_routes"]
