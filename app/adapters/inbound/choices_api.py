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

Options and the decision (ownership-verified; JSON or the choice page's forms; the page
is answered over HTMX with its detail view re-rendered):
    POST /api/choices/{uid}/options                      — Add an option to an undecided choice
    POST /api/choices/{uid}/options/{option_uid}/remove  — Remove an option from it
    POST /api/choices/{uid}/decide                       — Decide it: select one of its options, once
    POST /api/choices/{uid}/outcome                      — Record how a decided choice turned out

Knowledge intelligence:
    GET  /api/choices/knowledge-patterns — Detected learning patterns across user choices
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fasthtml.common import FtResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_body
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
    parse_float_param_strict,
    verify_entity_ownership,
)
from core.models.choice.choice import Choice
from core.models.choice.choice_request import (
    ChoiceDecisionRequest,
    ChoiceEvaluationRequest,
    ChoiceOptionRequest,
)
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.entity_requests import (
    AddHierarchyChildRequest,
    LinkChoiceToGoalRequest,
    LinkChoiceToPrincipleRequest,
)
from core.models.enums.neo_labels import NeoLabel
from core.utils.result_simplified import Errors, Result
from ui.activities.choices_views import ChoiceCard, ChoiceDetailView

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import RouteDecorator
    from core.ports import ConnectionFetchOperations
    from core.services.choices_service import ChoicesService
    from core.services.goals_service import GoalsService
    from core.services.principles_service import PrinciplesService


def create_choices_api_routes(
    rt: RouteDecorator,
    choices_service: ChoicesService,
    goals_service: GoalsService,
    principles_service: PrinciplesService,
    connection_fetch_backend: ConnectionFetchOperations,
) -> None:
    """Register Choices API routes."""

    async def update_status(uid: str, new_status: str) -> Result[Choice]:
        # Mirror tasks_api: go through the facade contract with a typed intent (ADR-066),
        # not past it into .core with a raw dict. The facade funnels through the core's
        # validated, ChoiceUpdated-firing update path.
        return await choices_service.update_choice(uid, ChoiceUpdateIntent(status=new_status))

    async def update_priority(uid: str, new_priority: str) -> Result[Choice]:
        return await choices_service.update_choice(uid, ChoiceUpdateIntent(priority=new_priority))

    create_activity_field_api_routes(
        rt,
        ActivityFieldApiConfig(
            domain_name="choices",
            singular="choice",
            service=choices_service,
            card_fn=ChoiceCard,
            links=connection_fetch_backend,
            link_label=NeoLabel.CHOICE,
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

    create_activity_hierarchy_api_routes(
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
        return await choices_service.link_choice_to_principle(req.choice_uid, req.principle_uid)

    create_activity_link_api_routes(
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
                doc="Link choice to a principle that informs it (INFORMS_CHOICE, principle → choice).",
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
        min_confidence = parse_float_param_strict(
            request.query_params.get("min_confidence"),
            "min_confidence",
            default=0.8,
            min_val=0.0,
            max_val=1.0,
        )
        if min_confidence.is_error:
            return Result.fail(min_confidence)
        return await choices_service.find_choices_aligned_with_principle(
            principle_uid, user_uid, min_confidence.value
        )

    # ================================================================
    # OPTIONS, THE DECISION AND ITS OUTCOME — the choice page's controls
    # ================================================================

    async def answer(request: Request, written: Result[Choice]) -> Result[Choice] | FtResponse:
        """The choice a door wrote: its detail view for the page, the choice for JSON.

        A refusal is the same error either way: HTMX swaps nothing and the page's
        toast reads its message.
        """
        if written.is_error or not request.headers.get("HX-Request"):
            return written
        choice = written.value
        links = await connection_fetch_backend.fetch_entity_connections(
            NeoLabel.CHOICE, [choice.uid]
        )
        return FtResponse(ChoiceDetailView(choice, links.get(choice.uid, [])))

    @rt("/api/choices/{uid}/options", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def add_choice_option(request: Request, uid: str) -> Result[Choice] | FtResponse:
        """Add one option (``ChoiceOptionRequest``) to the caller's undecided choice.

        Not owned or missing → 404. A decided choice, or a binary choice that holds
        two options already, is refused (400) and keeps its options.
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(choices_service, uid, user_uid, "choice")
        if ownership_error:
            return ownership_error
        parsed = await parse_body(request, ChoiceOptionRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        return await answer(request, await choices_service.add_option(uid, parsed.value))

    @rt("/api/choices/{uid}/options/{option_uid}/remove", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def remove_choice_option(
        request: Request, uid: str, option_uid: str
    ) -> Result[Choice] | FtResponse:
        """Remove one option from the caller's undecided choice.

        Not owned or missing, or an option the choice does not hold → 404. A decided
        choice, or one the removal would leave with fewer than two options, is
        refused (400).
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(choices_service, uid, user_uid, "choice")
        if ownership_error:
            return ownership_error
        return await answer(request, await choices_service.remove_option(uid, option_uid))

    @rt("/api/choices/{uid}/decide", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def decide_choice(request: Request, uid: str) -> Result[Choice] | FtResponse:
        """Decide the caller's choice (``ChoiceDecisionRequest``): one of its own options, once.

        Not owned or missing → 404. An option the choice does not hold, a choice with
        fewer than two options, and a choice already decided are refused (400) with
        the choice unchanged. Publishes ``ChoiceMade``.
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(choices_service, uid, user_uid, "choice")
        if ownership_error:
            return ownership_error
        parsed = await parse_body(request, ChoiceDecisionRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        decision = parsed.value
        return await answer(
            request,
            await choices_service.make_decision(
                uid,
                decision.selected_option_uid,
                decision_rationale=decision.decision_rationale,
                confidence=decision.confidence,
            ),
        )

    @rt("/api/choices/{uid}/outcome", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def record_choice_outcome(request: Request, uid: str) -> Result[Choice] | FtResponse:
        """Record how the caller's decided choice turned out (``ChoiceEvaluationRequest``).

        Open or closed, a decided choice takes an outcome, and a later one replaces it.
        Not owned or missing → 404. A choice not yet decided is refused (400) and keeps
        what it had. Publishes ``ChoiceOutcomeRecorded``.
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(choices_service, uid, user_uid, "choice")
        if ownership_error:
            return ownership_error
        parsed = await parse_body(request, ChoiceEvaluationRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        return await answer(
            request, await choices_service.evaluate_choice_outcome(uid, parsed.value)
        )

    # ================================================================
    # KNOWLEDGE INTELLIGENCE — learning patterns
    # ================================================================

    create_knowledge_patterns_api_route(rt, "choices", choices_service.analyze_learning_patterns)
