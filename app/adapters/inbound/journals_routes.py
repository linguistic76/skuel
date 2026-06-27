"""Journals domain routes — DNWF three-stage workflow (FOUNDER) and continuous (STANDARD).

Routes:
    GET  /journals          — tier-aware landing page (Tasks+ sidebar)
    POST /journals/respond  — STANDARD tier single-response workflow (FULL tier)
    POST /journals/stage1   — Stage 1 Scribe (FOUNDER only, FULL tier)
    POST /journals/stage2   — Stage 2 Thought Partner (FOUNDER only, FULL tier)
    POST /journals/stage3   — Stage 3 What Is Related (FOUNDER only, FULL tier)
    POST /journals/save     — persist journal entry as UserEntry(pipeline=JOURNAL)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services


logger = get_logger("skuel.routes.journals")


def create_journals_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> None:
    """Register Journal domain routes."""

    assert services.user is not None, "UserService must be wired before journals routes"
    user_service = services.user
    journal_service = services.journal  # None when INTELLIGENCE_TIER=core

    # ------------------------------------------------------------------
    # GET /journals — landing page
    # ------------------------------------------------------------------

    @rt("/journals", methods=["GET"])
    async def journals_page(request: Request) -> Any:
        user_uid = require_authenticated_user(request)

        from ui.activities.nav import render_activity_sidebar_page
        from ui.journals import JournalsPage

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return Response("Could not load user", status_code=500)

        workspace = JournalsPage(user_result.value)

        # HTMX fragment swap (e.g. "Write another" / "Start over" buttons target
        # #journal-workspace with outerHTML) — return the workspace div only.
        if request.headers.get("HX-Request"):
            return workspace

        return await render_activity_sidebar_page(
            content=workspace,
            active="journals",
            request=request,
            title="Journal",
        )

    # ------------------------------------------------------------------
    # POST /journals/respond — STANDARD tier single-response workflow
    # ------------------------------------------------------------------

    @rt("/journals/respond", methods=["POST"])
    @csrf_protected
    async def journals_respond(
        request: Request,
        raw_entry: str,
        title: str = "",
    ) -> Any:
        from ui.journals import ErrorFragment, StandardResponseFragment

        user_uid = require_authenticated_user(request)

        if not raw_entry or not raw_entry.strip():
            return ErrorFragment("Please write something before getting a response.")

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        result = await journal_service.run_standard(raw_entry.strip(), user_uid)
        if result.is_error:
            logger.error("Journal respond failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Could not generate a response. Please try again.")

        return StandardResponseFragment(
            raw_entry=raw_entry.strip(),
            title=title.strip(),
            response_output=result.value,
        )

    # ------------------------------------------------------------------
    # POST /journals/stage1 — Scribe
    # ------------------------------------------------------------------

    @rt("/journals/stage1", methods=["POST"])
    @csrf_protected
    async def journals_stage1(
        request: Request,
        raw_entry: str,
        title: str = "",
    ) -> Any:
        from ui.journals import ErrorFragment, Stage1Fragment

        user_uid = require_authenticated_user(request)

        if not raw_entry or not raw_entry.strip():
            return ErrorFragment("Please write something before proceeding.")

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return ErrorFragment("Could not load your profile.")
        if not user_result.value.journal_tier.is_founder():
            return ErrorFragment("Founder workflow is not available for your account.")

        result = await journal_service.run_stage1(raw_entry.strip(), user_uid)
        if result.is_error:
            logger.error("Stage 1 failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Stage 1 failed. Please try again.")

        return Stage1Fragment(
            raw_entry=raw_entry.strip(),
            title=title.strip(),
            scribe_output=result.value,
        )

    # ------------------------------------------------------------------
    # POST /journals/stage2 — Thought Partner
    # ------------------------------------------------------------------

    @rt("/journals/stage2", methods=["POST"])
    @csrf_protected
    async def journals_stage2(
        request: Request,
        raw_entry: str,
        title: str = "",
        scribe_output: str = "",
        review_notes: str = "",
    ) -> Any:
        from ui.journals import ErrorFragment, Stage2Fragment

        user_uid = require_authenticated_user(request)

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return ErrorFragment("Could not load your profile.")
        if not user_result.value.journal_tier.is_founder():
            return ErrorFragment("Founder workflow is not available for your account.")

        result = await journal_service.run_stage2(
            raw_entry=raw_entry,
            scribe_output=scribe_output,
            review_notes=review_notes,
            user_uid=user_uid,
        )
        if result.is_error:
            logger.error("Stage 2 failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Stage 2 failed. Please try again.")

        return Stage2Fragment(
            raw_entry=raw_entry,
            title=title,
            scribe_output=scribe_output,
            thought_partner_output=result.value,
        )

    # ------------------------------------------------------------------
    # POST /journals/stage3 — What Is Related
    # ------------------------------------------------------------------

    @rt("/journals/stage3", methods=["POST"])
    @csrf_protected
    async def journals_stage3(
        request: Request,
        raw_entry: str,
        title: str = "",
        scribe_output: str = "",
        thought_partner_output: str = "",
        review_notes: str = "",
    ) -> Any:
        from ui.journals import ErrorFragment, Stage3Fragment

        user_uid = require_authenticated_user(request)

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return ErrorFragment("Could not load your profile.")
        if not user_result.value.journal_tier.is_founder():
            return ErrorFragment("Founder workflow is not available for your account.")

        result = await journal_service.run_stage3(
            raw_entry=raw_entry,
            thought_partner_output=thought_partner_output,
            review_notes=review_notes,
            user_uid=user_uid,
        )
        if result.is_error:
            logger.error("Stage 3 failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Stage 3 failed. Please try again.")

        return Stage3Fragment(
            raw_entry=raw_entry,
            title=title,
            related_output=result.value,
        )

    # ------------------------------------------------------------------
    # POST /journals/save — persist entry
    # ------------------------------------------------------------------

    @rt("/journals/save", methods=["POST"])
    @csrf_protected
    async def journals_save(
        request: Request,
        raw_entry: str,
        title: str = "",
    ) -> Any:
        from ui.journals import ErrorFragment, SavedFragment

        user_uid = require_authenticated_user(request)

        if not raw_entry or not raw_entry.strip():
            return ErrorFragment("Cannot save an empty entry.")

        if journal_service is None:
            return ErrorFragment("Journal save is not available (CORE tier).")

        result = await journal_service.save_entry(
            title=title.strip(),
            raw_entry=raw_entry.strip(),
            user_uid=user_uid,
        )
        if result.is_error:
            logger.error("Journal save failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Could not save your journal entry.")

        return SavedFragment(entry_uid=result.value)
