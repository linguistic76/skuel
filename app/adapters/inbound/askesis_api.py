"""Askesis API routes — the question-answer endpoint.

The historical surface (CRUD instance management, guidance, insights,
domain-integration, analytics, suggestions, intelligence update, daily-plan,
path-steps, critical-path, unblocking-order, synergies, life-path-alignment,
schedule-recommendations) was removed in the ADR-059 follow-up: 16 of 17
routes had zero callers in ``ui/``, ``static/js/``, or other services and
no functional test coverage. Per "One Path Forward" — no aspirational
endpoints.

What remains:
- ``GET /api/askesis/ask`` — the JSON-shaped RAG entry point, the only route
  with any test coverage (auth-gate in tests/integration/test_askesis_ask_endpoint.py).

The production UI uses ``POST /askesis/api/submit`` (in askesis_ui.py),
which calls ``askesis_service.answer_user_question`` directly and renders
HTMX bubbles. New API surface should be added back here only when a real
caller exists.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.rate_limit import llm_quota_allowed, llm_quota_exceeded_error
from adapters.inbound.result_helpers import require_found
from core.config.intelligence_tier import IntelligenceTier
from core.ports import AskesisOperations
from core.services.intelligence_tier_service import get_user_intelligence_tier
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.user_service import UserService

logger = get_logger("skuel.routes.askesis.api")


def create_askesis_api_routes(
    app: Any,
    rt: Any,
    askesis_service: AskesisOperations,
    intelligence_tier: IntelligenceTier | None = None,
    user_service: "UserService | None" = None,
) -> list[Any]:
    """Register the Askesis API routes.

    Args:
        app: FastHTML application instance (unused — kept for factory signature parity).
        rt: Route decorator.
        askesis_service: AskesisService instance (RAG pipeline).
        intelligence_tier: System intelligence tier for per-user gate (ADR-043).
        user_service: User service for role lookup in the per-user tier gate.
    """

    @rt("/api/askesis/ask")
    @boundary_handler()
    async def ask_question_route(request: Request) -> Result[dict[str, Any]]:
        """Ask Askesis a question using the RAG pipeline.

        Query Parameters:
            question (str): Natural language question (required).
            session_id (str): Optional conversation session identifier.

        Returns:
            Result[dict]: Response containing answer, context_used,
            suggested_actions, confidence, mode, has_citations.

        Example:
            GET /api/askesis/ask?question=What%20should%20I%20learn%20next?
        """
        user_uid = require_authenticated_user(request)

        # Per-user tier gate (ADR-043): fail-secure — missing dependencies
        # mean the gate cannot be evaluated, so deny rather than allow.
        if intelligence_tier is None:
            return Result.fail(
                Errors.forbidden(
                    action="use Askesis AI",
                    reason="AI features require a paid subscription",
                    required_role="MEMBER",
                )
            )
        if user_service is None:
            return Result.fail(
                Errors.system("UserService not configured", operation="ask_question_route")
            )
        user = require_found(await user_service.get_user(user_uid), "User", user_uid)
        if user.is_error:
            return Result.fail(Errors.database("get_user", "Could not verify user access tier"))
        effective_tier = get_user_intelligence_tier(intelligence_tier, user.value.role)
        if not effective_tier.ai_enabled:
            return Result.fail(
                Errors.forbidden(
                    action="use Askesis AI",
                    reason="AI features require a paid subscription",
                    required_role="MEMBER",
                )
            )

        question = request.query_params.get("question")
        session_id = request.query_params.get("session_id")
        # Per-conversation model choice (switcher), gated OpenAI-safe downstream.
        model = request.query_params.get("model")

        if not question:
            return Result.fail(
                Errors.validation(
                    message="question is required",
                    field="question",
                    value=None,
                )
            )

        # Daily LLM quota — after every validation, immediately before the
        # paid RAG pipeline, so a rejected request never burns a unit.
        if not llm_quota_allowed(user_uid):
            return Result.fail(llm_quota_exceeded_error())

        logger.info(f"RAG question from {user_uid}: {question}")
        result = await askesis_service.answer_user_question(
            user_uid, question, session_id=session_id, model=model or None
        )
        if result.is_ok:
            logger.info(f"RAG answer generated for {user_uid}")
        else:
            logger.error(f"RAG pipeline failed for {user_uid}: {result.error}")

        return result

    logger.info("Askesis API routes registered (/api/askesis/ask)")
    return []


__all__ = ["create_askesis_api_routes"]
