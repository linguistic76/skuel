"""Choices API routes.

Provides HTMX-compatible endpoints for choice status/priority updates and hierarchy queries.

Hierarchy (ownership-verified, via create_activity_hierarchy_api_routes):
    GET  /api/choices/children       — Direct subchoices of a parent choice (JSON)
    GET  /api/choices/{uid}/children — Subchoices as a TreeNodeList fragment (HTMX)
    GET  /api/choices/parent         — Immediate parent of a subchoice
    GET  /api/choices/hierarchy      — Full hierarchy context (ancestors, siblings, children)
    POST /api/choices/remove-child   — Remove a subchoice relationship
    POST /api/choices/add-child      — Add a subchoice relationship

Cross-domain links (link-* via create_activity_link_api_routes):
    POST /api/choices/link-goal              — Link choice to a goal it affects/advances
    POST /api/choices/link-principle         — Link choice to the principle that informs it
    GET  /api/choices/aligned-with-principle — Choices semantically aligned with a principle

Knowledge intelligence:
    GET  /api/choices/knowledge-patterns — Detected learning patterns across user choices
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories import (
    PRIORITY_VALUES,
    ActivityFieldApiConfig,
    ActivityHierarchyApiConfig,
    CrossDomainLinkSpec,
    FieldUpdateSpec,
    LinkTargetSpec,
    create_activity_field_api_routes,
    create_activity_hierarchy_api_routes,
    create_activity_link_api_routes,
    create_knowledge_patterns_api_route,
    verify_entity_ownership,
)
from core.models.choice.choice import Choice
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.entity_requests import (
    AddHierarchyChildRequest,
    LinkChoiceToGoalRequest,
    LinkChoiceToPrincipleRequest,
)
from core.utils.result_simplified import Errors, Result
from ui.activities.choices_views import ChoiceCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.choices_service import ChoicesService
    from core.services.goals_service import GoalsService
    from core.services.principles_service import PrinciplesService


def create_choices_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    choices_service: ChoicesService,
    goals_service: GoalsService,
    principles_service: PrinciplesService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Choices API routes."""

    async def update_status(uid: str, new_status: str) -> Result[Choice]:
        # Mirror tasks_api: go through the facade contract with a typed intent (ADR-066),
        # not past it into .core with a raw dict. The facade funnels through the core's
        # validated, ChoiceUpdated-firing update path.
        return await choices_service.update_choice(uid, ChoiceUpdateIntent(status=new_status))

    async def update_priority(uid: str, new_priority: str) -> Result[Choice]:
        return await choices_service.update_choice(uid, ChoiceUpdateIntent(priority=new_priority))

    field_routes = create_activity_field_api_routes(
        rt,
        ActivityFieldApiConfig(
            domain_name="choices",
            singular="choice",
            service=choices_service,
            card_fn=ChoiceCard,
            fields=(
                FieldUpdateSpec(field="status", apply=update_status),
                FieldUpdateSpec(
                    field="priority", apply=update_priority, allowed_values=PRIORITY_VALUES
                ),
            ),
        ),
    )

    # ================================================================
    # HIERARCHY — shared Activity Domain hierarchy route block
    # ================================================================

    async def add_subchoice_relationship(req: AddHierarchyChildRequest) -> Result[bool]:
        # Choices carry no progress_weight — the request field is ignored.
        return await choices_service.create_subchoice_relationship(req.parent_uid, req.child_uid)

    hierarchy_routes = create_activity_hierarchy_api_routes(
        rt,
        ActivityHierarchyApiConfig(
            domain_name="choices",
            singular="choice",
            service=choices_service,
            get_children=choices_service.get_subchoices,
            get_parent=choices_service.get_parent_choice,
            get_hierarchy=choices_service.get_choice_hierarchy,
            add_child_relationship=add_subchoice_relationship,
            remove_child_relationship=choices_service.remove_subchoice_relationship,
        ),
    )

    # ================================================================
    # CROSS-DOMAIN LINKS
    # ================================================================

    async def apply_link_goal(req: LinkChoiceToGoalRequest) -> Result[bool]:
        return await choices_service.link_choice_to_goal(
            req.choice_uid, req.goal_uid, req.contribution_score
        )

    async def apply_link_principle(req: LinkChoiceToPrincipleRequest) -> Result[bool]:
        return await choices_service.link_choice_to_principle(
            req.choice_uid, req.principle_uid, req.alignment_score
        )

    link_routes = create_activity_link_api_routes(
        rt,
        domain_name="choices",
        singular="choice",
        service=choices_service,
        specs=(
            CrossDomainLinkSpec(
                action="link-goal",
                request_model=LinkChoiceToGoalRequest,
                owner_uid_field="choice_uid",
                apply=apply_link_goal,
                doc="Link choice to a goal it affects/advances (AFFECTS_GOAL).",
                target=LinkTargetSpec(service=goals_service, uid_field="goal_uid", singular="goal"),
            ),
            CrossDomainLinkSpec(
                action="link-principle",
                request_model=LinkChoiceToPrincipleRequest,
                owner_uid_field="choice_uid",
                apply=apply_link_principle,
                doc="Link choice to the principle that informs it (INFORMED_BY_PRINCIPLE).",
                target=LinkTargetSpec(
                    service=principles_service, uid_field="principle_uid", singular="principle"
                ),
            ),
        ),
    )

    @rt("/api/choices/aligned-with-principle", methods=["GET"])
    @boundary_handler()
    async def choices_aligned_with_principle(request: Request) -> Result[list[Choice]]:
        """Choices semantically aligned with a given principle (min_confidence threshold)."""
        user_uid = require_authenticated_user(request)
        principle_uid = request.query_params.get("principle_uid", "").strip()
        if not principle_uid:
            return Result.fail(
                Errors.validation(message="principle_uid is required", field="principle_uid")
            )
        principle_ownership_error = await verify_entity_ownership(
            principles_service, principle_uid, user_uid, "principle"
        )
        if principle_ownership_error:
            return principle_ownership_error
        raw_confidence = request.query_params.get("min_confidence", "0.8")
        try:
            min_confidence = float(raw_confidence)
        except ValueError:
            return Result.fail(
                Errors.validation(message="min_confidence must be a number", field="min_confidence")
            )
        result = await choices_service.find_choices_aligned_with_principle(
            principle_uid, min_confidence
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([c for c in result.value if c.user_uid == user_uid])

    # ================================================================
    # KNOWLEDGE INTELLIGENCE — learning patterns
    # ================================================================

    knowledge_patterns_route = create_knowledge_patterns_api_route(
        rt, "choices", choices_service.analyze_learning_patterns
    )

    return [
        *field_routes,
        *hierarchy_routes,
        *link_routes,
        choices_aligned_with_principle,
        knowledge_patterns_route,
    ]
