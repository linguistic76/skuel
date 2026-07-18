"""Self Check-In routes — dual-track perception-gap surface (ADR-030).

Surfaces the dual-track assessment engine for the three *user-level* dimensions:
Productivity (Tasks), Engagement (Events), Decision Quality (Choices).

Routes:
- GET  /self-checkin          — the self-rating page (form + results slot + history)
- POST /self-checkin/results  — run + persist the assessments, render gap cards + trends

The results route is POST + ``@csrf_protected`` because it *mutates*: each rated
dimension appends a check-in to the :User node's ``dual_track_checkins`` log
(user-level dims have no :Entity row to attach to). ``skuel.js`` attaches the
X-CSRF-Token header to every HTMX request.
"""

from __future__ import annotations

import functools
from typing import Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.models.enums import (
    DecisionQualityLevel,
    DualTrackDimension,
    EngagementLevel,
    ProductivityLevel,
)
from core.models.shared.dual_track import DualTrackResult
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.page_header import PageHeader
from ui.self_checkin import render_checkin_form, render_checkin_history, render_checkin_results

logger = get_logger("skuel.routes.self_checkin")

# Per-dimension dispatch: which level enum, which container service, and which
# `.intelligence` assess method drives each user-level dimension. The dimension's
# value is the form field name AND the storage key on the :User node.
_DISPATCH: list[tuple[DualTrackDimension, type, str, str]] = [
    (DualTrackDimension.PRODUCTIVITY, ProductivityLevel, "tasks", "assess_productivity_dual_track"),
    (DualTrackDimension.ENGAGEMENT, EngagementLevel, "events", "assess_engagement_dual_track"),
    (
        DualTrackDimension.DECISION_QUALITY,
        DecisionQualityLevel,
        "choices",
        "assess_decision_quality_dual_track",
    ),
]


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
    dim_value: str,
    label: str,
    result: Result[DualTrackResult[Any]],
    results: list[tuple[str, str, DualTrackResult[Any]]],
    errors: list[str],
) -> None:
    """Append a successful assessment to results, or its error to errors."""
    if result.is_error:
        errors.append(f"{label}: {result.expect_error().message}")
    else:
        results.append((dim_value, label, result.value))


async def _load_checkins(services: Any, user_uid: str) -> dict[str, list[dict[str, Any]]]:
    """Read the user's persisted user-level check-ins, keyed by dimension."""
    user_result = await services.user.get_user(user_uid)
    if user_result.is_ok and user_result.value:
        return user_result.value.dual_track_checkins or {}
    return {}


def create_self_checkin_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Any,
    _sync_service: Any = None,
) -> None:
    """Wire the self check-in page + results fragment."""
    if not (services and services.tasks and services.events and services.choices and services.user):
        logger.warning("Self check-in routes skipped: required services unavailable")
        return

    @rt("/self-checkin")
    async def self_checkin_page(request: Request) -> Any:
        """Render the self-rating page (form + empty results slot + check-in history)."""
        user_uid = require_authenticated_user(request)
        checkins = await _load_checkins(services, user_uid)
        content = Div(
            PageHeader(
                "Self Check-In",
                subtitle="Compare how you feel with what your tracked actions show",
            ),
            render_checkin_form(),
            Div(id="checkin-results", cls="mt-6"),
            render_checkin_history(checkins),
            cls="space-y-6",
        )
        return BasePage(
            content,
            title="Self Check-In",
            page_type=PageType.STANDARD,
            request=request,
            active_page="self-checkin",
        )

    @rt("/self-checkin/results", methods=["POST"])
    @csrf_protected
    async def self_checkin_results(request: Request) -> Any:
        """HTMX POST: run + persist the selected dual-track assessments, render gaps.

        POST (not GET) because it mutates — each rated dimension persists a check-in
        to the :User node via ``UserService.append_dual_track_checkin`` (bound as the
        ``store_callback``). CSRF-protected so a check-in can't be written via a plain
        link / prefetch.
        """
        user_uid = require_authenticated_user(request)
        form = await request.form()
        reflection = str(form.get("reflection", ""))

        results: list[tuple[str, str, DualTrackResult[Any]]] = []
        errors: list[str] = []

        for dim, enum_cls, svc_attr, method_name in _DISPATCH:
            level = _parse_level(enum_cls, str(form.get(dim.value, "")))
            if level is None:
                continue
            assess = getattr(getattr(services, svc_attr).intelligence, method_name)
            store_callback = functools.partial(
                services.user.append_dual_track_checkin, dimension=dim
            )
            _collect(
                dim.value,
                dim.label(),
                await assess(
                    user_uid, level, user_evidence=reflection, store_callback=store_callback
                ),
                results,
                errors,
            )

        # Re-read so each trend includes the just-stored check-in.
        checkins = await _load_checkins(services, user_uid)
        return render_checkin_results(results, errors, checkins)


__all__ = ["create_self_checkin_routes"]
