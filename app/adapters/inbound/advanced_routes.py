"""
Advanced Routes - Calendar Optimization
============================================

Wires the calendar optimization API routes using DomainRouteConfig.

Primary service: calendar_optimization_orchestrator (Calendar cognitive-load balancing)

Routes:
- GET /cal/optimize - Optimize calendar with cognitive load balancing
- GET /cal/cognitive-load - Analyze cognitive load for a date
"""

from typing import Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.route_factories import (
    DomainRouteConfig,
    parse_date_param_strict,
    register_domain_routes,
)
from core.models.calendar_optimization import (
    CalendarOptimization,
    CognitiveLoadDay,
    SchedulingStrategy,
)
from core.orchestrator.calendar_optimization_orchestrator import (
    CalendarOptimizationOrchestrator,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

logger = get_logger("skuel.routes.advanced")


# ---------------------------------------------------------------------------
# Calendar Optimization - Cognitive Load Balancing (primary service)
# ---------------------------------------------------------------------------


def create_calendar_optimization_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    calendar_optimization_orchestrator: CalendarOptimizationOrchestrator,
) -> None:
    """Register calendar optimization endpoints."""

    @rt("/cal/optimize")
    @boundary_handler()
    async def optimize(
        request: Request,
        target_date: str | None = None,
        strategy: str = "cognitive_balanced",
    ) -> Result[CalendarOptimization]:
        """
        Optimize the authenticated user's calendar for a date (cognitive load balancing).

        Query params:
            target_date: Date to optimize (YYYY-MM-DD), defaults to today
            strategy: Optimization strategy (default: cognitive_balanced)
                     Options: cognitive_balanced, knowledge_focused, deadline_driven,
                             energy_aligned, spaced_repetition
        """
        user_uid = require_authenticated_user(request)
        if target_date:
            date_result = parse_date_param_strict(target_date, "target_date")
            if date_result.is_error:
                return Result.fail(date_result)
            opt_date = date_result.value
        else:
            opt_date = today_in(current_zone())

        try:
            strat = SchedulingStrategy(strategy)
        except ValueError:
            return Result.fail(
                Errors.validation(f"Invalid strategy: {strategy}", field="strategy", value=strategy)
            )

        return await calendar_optimization_orchestrator.optimize_schedule(
            user_uid=user_uid,
            target_date=opt_date,
            strategy=strat,
        )

    @rt("/cal/cognitive-load")
    @boundary_handler()
    async def cognitive_load(
        request: Request,
        target_date: str | None = None,
    ) -> Result[CognitiveLoadDay]:
        """The caller's cognitive load for a date: one analysis per open task due
        that day, and the analyses that risk overload."""
        user_uid = require_authenticated_user(request)
        if target_date:
            date_result = parse_date_param_strict(target_date, "target_date")
            if date_result.is_error:
                return Result.fail(date_result)
            opt_date = date_result.value
        else:
            opt_date = today_in(current_zone())

        task_list, analyses = await calendar_optimization_orchestrator.get_cognitive_load_analyses(
            user_uid=user_uid, target_date=opt_date
        )
        return Result.ok(
            CognitiveLoadDay(
                date=opt_date.isoformat(),
                task_count=len(task_list),
                cognitive_analyses=analyses,
                overload_risks=[a for a in analyses if a["cognitive_load"]["is_overload_risk"]],
            )
        )


# ---------------------------------------------------------------------------
# DomainRouteConfig wiring
# ---------------------------------------------------------------------------

ADVANCED_CONFIG = DomainRouteConfig(
    domain_name="advanced",
    primary_service_attr="calendar_optimization_orchestrator",
    api_factory=create_calendar_optimization_routes,
)


def create_advanced_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service=None
) -> None:
    """
    Wire the calendar optimization routes using DomainRouteConfig.

    See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
    """
    register_domain_routes(app, rt, services, ADVANCED_CONFIG)


__all__ = ["create_advanced_routes"]
