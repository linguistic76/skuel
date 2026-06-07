"""Self Check-In routes — dual-track perception-gap surface (ADR-030).

Surfaces the (previously dormant) dual-track assessment engine for the three
user-level dimensions: Productivity (Tasks), Engagement (Events), Decision
Quality (Choices).

Routes:
- GET /self-checkin          — the self-rating page (form + empty results slot)
- GET /self-checkin/results  — HTMX fragment: computes + renders the gap cards

Both are GET (non-mutating compute-and-display) — no persistence in v1.
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.models.enums import DecisionQualityLevel, EngagementLevel, ProductivityLevel
from core.models.shared.dual_track import DualTrackResult
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.page_header import PageHeader
from ui.self_checkin import render_checkin_form, render_checkin_results

logger = get_logger("skuel.routes.self_checkin")


def _parse_level(enum_cls: type, raw: str) -> Any:
    """Parse a raw form value into an enum member, or None when blank/invalid."""
    if not raw:
        return None
    try:
        return enum_cls(raw)
    except ValueError:
        logger.debug("Self check-in: ignoring invalid %s value %r", enum_cls.__name__, raw)
        return None


def _collect(
    label: str,
    result: Result[DualTrackResult[Any]],
    results: list[tuple[str, DualTrackResult[Any]]],
    errors: list[str],
) -> None:
    """Append a successful assessment to results, or its error to errors."""
    if result.is_error:
        errors.append(f"{label}: {result.expect_error().message}")
    else:
        results.append((label, result.value))


def create_self_checkin_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Any,
    _sync_service: Any = None,
) -> None:
    """Wire the self check-in page + results fragment."""
    if not services or not services.tasks or not services.events or not services.choices:
        logger.warning("Self check-in routes skipped: activity services unavailable")
        return

    @rt("/self-checkin")
    async def self_checkin_page(request: Request) -> Any:
        """Render the self-rating page."""
        require_authenticated_user(request)
        content = Div(
            PageHeader(
                "Self Check-In",
                subtitle="Compare how you feel with what your tracked actions show",
            ),
            render_checkin_form(),
            Div(id="checkin-results", cls="mt-6"),
            cls="space-y-6",
        )
        return await BasePage(
            content,
            title="Self Check-In",
            page_type=PageType.STANDARD,
            request=request,
            active_page="self-checkin",
        )

    @rt("/self-checkin/results")
    async def self_checkin_results(
        request: Request,
        productivity: str = "",
        engagement: str = "",
        decision_quality: str = "",
        reflection: str = "",
    ) -> Any:
        """HTMX fragment: run the selected dual-track assessments and render gap cards."""
        user_uid = require_authenticated_user(request)
        results: list[tuple[str, DualTrackResult[Any]]] = []
        errors: list[str] = []

        prod = _parse_level(ProductivityLevel, productivity)
        if prod is not None:
            _collect(
                "Productivity",
                await services.tasks.intelligence.assess_productivity_dual_track(
                    user_uid, prod, user_evidence=reflection
                ),
                results,
                errors,
            )

        eng = _parse_level(EngagementLevel, engagement)
        if eng is not None:
            _collect(
                "Engagement",
                await services.events.intelligence.assess_engagement_dual_track(
                    user_uid, eng, user_evidence=reflection
                ),
                results,
                errors,
            )

        dq = _parse_level(DecisionQualityLevel, decision_quality)
        if dq is not None:
            _collect(
                "Decision Quality",
                await services.choices.intelligence.assess_decision_quality_dual_track(
                    user_uid, dq, user_evidence=reflection
                ),
                results,
                errors,
            )

        return render_checkin_results(results, errors)


__all__ = ["create_self_checkin_routes"]
