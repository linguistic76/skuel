"""
Askesis UI Routes
=================

UI routes for Askesis AI assistant — three-column chat surface.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import P
from starlette.responses import RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import safe_form_string
from adapters.inbound.rate_limit import LLM_QUOTA_MESSAGE, llm_quota_allowed
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import GuidanceMode
from core.models.search_request import SearchRequest
from core.services.intelligence_tier_service import get_user_intelligence_tier
from core.utils.logging import get_logger
from ui.askesis import render_askesis_page, render_assistant_message, render_user_message

if TYPE_CHECKING:
    from core.orchestrator.search_router import SearchRouter
    from core.services.user_service import UserService

logger = get_logger("skuel.ui.askesis")


def create_askesis_ui_routes(
    _app: Any,
    rt: Any,
    _askesis_service: Any,
    intelligence_tier: IntelligenceTier | None = None,
    user_service: "UserService | None" = None,
    ku_service: Any = None,
    search_router: "SearchRouter | None" = None,
) -> list[Any]:
    """Create UI routes for Askesis AI assistant."""

    routes = []

    async def _load_nous_topics() -> list[str]:
        """Fetch the NOUS topic vocabulary for the composer scope control.

        Fails soft — a missing ku_service or a query error yields an empty list,
        so the composer renders without the scope selector rather than 500ing.
        """
        if ku_service is None:
            return []
        result = await ku_service.list_nous_topics()
        if result.is_error:
            logger.warning(f"Could not load NOUS topics for Askesis composer: {result.error}")
            return []
        return sorted(result.value)

    async def _load_nous_subtopic_map() -> dict[str, list[str]]:
        """Fetch the nous→sub-topics dependency map for the composer scope.

        Spans BOTH :Ku and :PathStep via SearchRouter (which merges each
        curriculum domain's own-label co-occurrence pairs — cross-domain
        aggregation in the service layer, not a backend). The composer inlines
        it into Alpine state so the sub-topic selector offers only the chosen
        topic's sub-topics. Fails soft the same way as topics. Empty until the
        vault carries `nous_subtopic:` data, so the sub-topic selector renders
        nothing (mechanism ships ahead of content).

        **Askesis is NOT a search result set, so it takes the WIDEST honest
        vocabulary — ruled 2026-08-26.** `/search` narrowed its own to the
        curriculum domains it returns (Ku alone); that is a fact about a page
        that lists things, and it does not travel here. Askesis reaches
        everything about the user, bounded by scopes the user opens and closes
        themselves — this selector is one of those boundaries, which is why it
        renders as a visible, clearable chip rather than an implicit filter.
        Code must never narrow it on the user's behalf, and never to match what
        some other surface happens to show.

        Concretely, narrowing here would also be wrong on its own terms: the
        scope selects the `:ContentChunk` passages an answer is grounded in,
        and lesson bodies live on PathSteps (`_retrieve_scoped_chunks` cites
        the PathStep a passage came from), so a Ku-only vocabulary would hide
        the sub-topics whose passages Askesis actually reads.

        See: docs/roadmap/done/search-facet-redesign.md (ruling 7).
        """
        if search_router is None:
            return {}
        result = await search_router.nous_subtopic_map()
        if result.is_error:
            logger.warning(f"Could not load NOUS sub-topics for Askesis composer: {result.error}")
            return {}
        return result.value or {}

    @rt("/askesis")
    async def askesis_home(request: Request) -> Any:
        """Full Askesis chat surface.

        Optional ``?question=`` / ``?nous=`` carry the /search "Ask" handoff:
        the composer is prefilled + scope-seeded (chip shown) and the user clicks
        Send. It never auto-submits — a crafted GET must not run a prompt in a
        logged-in victim's session (Kody #545).
        """
        question = request.query_params.get("question", "")
        nous_topics = await _load_nous_topics()
        nous_subtopic_map = await _load_nous_subtopic_map()
        # Only honor a seeded scope when the live vocabulary actually contains it.
        # In the no-data fail-soft path the sub-topic selector + chip don't render,
        # so a crafted ?nous_subtopic= would be an INVISIBLE scope silently
        # constraining every answer with no way to see or clear it (Codex #546).
        # Validation is DEPENDENT, mirroring the selector: the sub-topic must
        # co-occur with the seeded nous on ≥1 entity (a pair no content carries
        # is dropped). A valid /search handoff always passes — its dropdown now
        # offers a Ku-only SUBSET of these merged pairs, so anything it can send
        # is in this map; only crafted or stale values are dropped.
        nous = request.query_params.get("nous", "")
        if nous not in nous_topics:
            nous = ""
        nous_subtopic = request.query_params.get("nous_subtopic", "")
        if nous_subtopic not in nous_subtopic_map.get(nous, []):
            nous_subtopic = ""
        # Model-switcher options come from the wired caller (dev with no Anthropic
        # adapter offers only OpenAI models); empty → no picker rendered.
        model_options = (
            _askesis_service.available_chat_models() if _askesis_service is not None else []
        )
        return render_askesis_page(
            request,
            nous_topics=nous_topics,
            nous_subtopic_map=nous_subtopic_map,
            initial_question=question,
            initial_nous=nous,
            initial_nous_subtopic=nous_subtopic,
            model_options=model_options,
        )

    routes.append(askesis_home)

    @rt("/askesis/new-chat")
    def askesis_new_chat(
        request: Request,
    ) -> Any:
        return RedirectResponse("/askesis", status_code=302)

    routes.append(askesis_new_chat)

    @rt("/askesis/history")
    def askesis_history(
        request: Request,
    ) -> Any:
        return RedirectResponse("/askesis", status_code=302)

    routes.append(askesis_history)

    @rt("/askesis/analytics")
    def askesis_analytics(
        request: Request,
    ) -> Any:
        return RedirectResponse("/askesis", status_code=302)

    routes.append(askesis_analytics)

    @rt("/askesis/settings")
    def askesis_settings(
        request: Request,
    ) -> Any:
        return RedirectResponse("/askesis", status_code=302)

    routes.append(askesis_settings)

    @rt("/askesis/api/submit")
    @csrf_protected
    async def submit_message(request: Request) -> Any:
        """Handle message submission (HTMX endpoint) — returns styled user + AI bubbles."""
        user_uid = require_authenticated_user(request)

        # Per-user tier gate (ADR-043): fail-secure — missing dependencies
        # mean the gate cannot be evaluated, so deny rather than allow.
        if intelligence_tier is None:
            return P(
                "AI features require a paid subscription. Upgrade to MEMBER to unlock Askesis.",
                cls="text-error text-sm px-7 py-2",
            )
        if user_service is None:
            return P(
                "Could not verify your access level. Please try again.",
                cls="text-error text-sm px-7 py-2",
            )
        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return P(
                "Could not verify your access level. Please try again.",
                cls="text-error text-sm px-7 py-2",
            )
        effective_tier = get_user_intelligence_tier(intelligence_tier, user_result.value.role)
        if not effective_tier.ai_enabled:
            return P(
                "AI features require a paid subscription. Upgrade to MEMBER to unlock Askesis.",
                cls="text-error text-sm px-7 py-2",
            )

        form_data = await request.form()
        message = safe_form_string(form_data.get("message"))

        if not message:
            return P("Please enter a message.", cls="text-error text-sm px-7 py-2")

        mode_str = safe_form_string(form_data.get("mode", ""))
        preferred_mode: GuidanceMode | None = (
            GuidanceMode(mode_str) if mode_str in GuidanceMode._value2member_map_ else None
        )

        # Optional NOUS topic + sub-topic scope from the composer — narrows the
        # answer's retrieved passages to that topic/sub-topic (Scoped Ask). Both
        # empty = no scope; either present builds the scope. The sub-topic facet
        # reaches retrieval for free via SearchRequest.to_property_filters().
        nous = safe_form_string(form_data.get("nous", ""))
        nous_subtopic = safe_form_string(form_data.get("nous_subtopic", ""))
        scope: SearchRequest | None = (
            SearchRequest(nous=nous or None, nous_subtopic=nous_subtopic or None)
            if (nous or nous_subtopic)
            else None
        )

        # Per-conversation model choice from the composer's switcher (composer-state
        # only — Askesis has no durable session). Gated OpenAI-safe downstream, so a
        # forged/unavailable model degrades to the app default rather than erroring.
        model = safe_form_string(form_data.get("model", ""))

        # Daily LLM quota — after every validation, immediately before the
        # paid RAG pipeline, so a rejected request never burns a unit.
        if not llm_quota_allowed(user_uid):
            return P(LLM_QUOTA_MESSAGE, cls="text-error text-sm px-7 py-2")

        ai_response: str
        canon_sources: tuple[Any, ...] = ()
        try:
            result = await _askesis_service.answer_user_question(
                user_uid, message, preferred_mode=preferred_mode, scope=scope, model=model or None
            )
            if result.is_error:
                logger.error(f"Askesis service error: {result.error}")
                ai_response = (
                    result.error.message
                    if result.error.message
                    else "I'm having trouble right now. Please try again."
                )
            else:
                ai_response = result.value.get("answer", "No response generated.")
                # Canon readings the guided prompt drew on (ADR-077) — CanonSource
                # is a core dataclass, fine to carry across to the renderer.
                canon_sources = tuple(result.value.get("canon_sources") or ())
        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Unexpected AI service error: {e}", exc_info=True)
            ai_response = "I'm having trouble right now. Please try again."

        return render_user_message(message), render_assistant_message(
            ai_response, canon_sources=canon_sources
        )

    routes.append(submit_message)

    logger.info(f"Askesis UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_askesis_ui_routes"]
