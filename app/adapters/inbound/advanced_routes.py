"""
Advanced Routes - Optional Services
============================================

Wires advanced API routes using DomainRouteConfig (Multi-Factory variant).

Primary service: calendar_optimization_orchestrator (Calendar cognitive-load balancing)
Extension factories:
- create_jupyter_sync_routes: Jupyter-Neo4j-Obsidian workflow (4 endpoints)
- create_performance_routes: Scale & speed optimization (4 endpoints)

Routes:
- GET /cal/optimize - Optimize calendar with cognitive load balancing
- GET /cal/cognitive-load - Analyze cognitive load for a date
- GET /jupyter/fetch - Fetch curriculum content for Jupyter editing
- POST /jupyter/save - Save Jupyter edits back to Neo4j
- POST /jupyter/sync-to-obsidian - Sync changes to Obsidian
- GET /jupyter/detect-conflicts - Detect Neo4j/Obsidian conflicts
- GET /performance/metrics - Current performance metrics
- GET /performance/cache-stats - Cache performance statistics
- POST /performance/optimize - Trigger optimization analysis
- GET /performance/scale-test - Run scale testing simulation
"""

from datetime import date
from typing import Any

from fasthtml.common import JSONResponse, Request

from adapters.inbound.auth import make_service_getter, require_admin, require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import (
    DomainRouteConfig,
    parse_date_param_strict,
    register_domain_routes,
)
from core.orchestrator.calendar_optimization_orchestrator import (
    CalendarOptimizationOrchestrator,
)
from core.services.calendar_optimization_service import CalendarOptimization, SchedulingStrategy
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.advanced")


# ---------------------------------------------------------------------------
# Calendar Optimization - Cognitive Load Balancing (primary service)
# ---------------------------------------------------------------------------


def create_calendar_optimization_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    calendar_optimization_orchestrator: CalendarOptimizationOrchestrator,
) -> list[Any]:
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
            opt_date = date.today()

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
    ) -> Result[dict[str, Any]]:
        """
        Analyze cognitive load for a specific date.
        Returns cognitive load distribution and overload risks.
        """
        user_uid = require_authenticated_user(request)
        if target_date:
            date_result = parse_date_param_strict(target_date, "target_date")
            if date_result.is_error:
                return Result.fail(date_result)
            opt_date = date_result.value
        else:
            opt_date = date.today()

        task_list, analyses = await calendar_optimization_orchestrator.get_cognitive_load_analyses(
            user_uid=user_uid, target_date=opt_date
        )
        return Result.ok(
            {
                "date": opt_date.isoformat(),
                "task_count": len(task_list),
                "cognitive_analyses": analyses,
                "overload_risks": [a for a in analyses if a["is_overload_risk"]],
            }
        )

    return [optimize, cognitive_load]


# ---------------------------------------------------------------------------
# Jupyter Sync - Jupyter-Neo4j-Obsidian Workflow (extension)
# ---------------------------------------------------------------------------


def create_jupyter_sync_routes(
    _app: FastHTMLApp, rt: RouteDecorator, jupyter_sync: Any, user_service: Any
) -> list[Any]:
    """Register Jupyter-Neo4j-Obsidian sync endpoints (ADMIN-gated curriculum authoring)."""

    get_user_service = make_service_getter(user_service)

    @rt("/jupyter/fetch")
    @require_admin(get_user_service)
    @boundary_handler()
    async def fetch(request: Request, uid: str, current_user: Any = None) -> JSONResponse:
        """
        Fetch content from Neo4j for Jupyter editing.

        Query params:
            uid: Knowledge unit UID
        """
        return await jupyter_sync.get_content_for_jupyter(uid)

    @rt("/jupyter/save")
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def save(request: Request, uid: str, current_user: Any = None) -> JSONResponse:
        """Save Jupyter-edited content back to Neo4j. Expects JSON body with edited content."""
        content = await request.json()
        return await jupyter_sync.save_jupyter_changes(uid, content)

    @rt("/jupyter/sync-to-obsidian")
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def sync_to_obsidian(
        request: Request, uid: str, current_user: Any = None
    ) -> JSONResponse:
        """
        Sync Neo4j changes back to Obsidian markdown files.

        Args:
            uid: Knowledge unit UID
        """
        return await jupyter_sync.sync_to_obsidian(uid)

    @rt("/jupyter/detect-conflicts")
    @require_admin(get_user_service)
    @boundary_handler()
    async def detect_conflicts(
        request: Request, uid: str, current_user: Any = None
    ) -> JSONResponse:
        """
        Detect conflicts between Neo4j and Obsidian content.

        Args:
            uid: Knowledge unit UID
        """
        return await jupyter_sync.detect_conflicts(uid)

    return [fetch, save, sync_to_obsidian, detect_conflicts]


# ---------------------------------------------------------------------------
# Performance Optimization - Scale & Speed (extension)
# ---------------------------------------------------------------------------


def create_performance_routes(
    _app: FastHTMLApp, rt: RouteDecorator, performance_optimization: Any, user_service: Any
) -> list[Any]:
    """Register performance optimization endpoints (ADMIN-gated ops/diagnostics)."""

    get_user_service = make_service_getter(user_service)

    @rt("/performance/metrics")
    @require_admin(get_user_service)
    @boundary_handler()
    async def metrics(request: Request, current_user: Any = None) -> JSONResponse:
        """Get current performance metrics (response time, throughput, cache hit rate, etc.)."""
        return await performance_optimization.get_current_metrics()

    @rt("/performance/cache-stats")
    @require_admin(get_user_service)
    @boundary_handler()
    async def cache_stats(
        request: Request, current_user: Any = None
    ) -> Result[
        Any
    ]:  # skuel-lint: disable=SKUEL029 -- wrapped by @boundary_handler() which awaits the handler unconditionally (boundary.py)
        """Get cache performance statistics (hit rate, size, evictions, efficiency)."""
        stats = performance_optimization.inference_engine.get_cache_stats()
        return Result.ok(stats)

    @rt("/performance/optimize")
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def optimize_performance(request: Request, current_user: Any = None) -> JSONResponse:
        """Trigger performance optimization analysis and tuning."""
        return await performance_optimization.optimize_performance()

    @rt("/performance/scale-test")
    @require_admin(get_user_service)
    @boundary_handler()
    async def scale_test(  # skuel-lint: disable=SKUEL029 -- wrapped by @boundary_handler() which awaits the handler unconditionally (boundary.py)
        request: Request,
        current_user: Any = None,
        concurrent_users: int = 100,
        duration_seconds: int = 60,
    ) -> Result[dict[str, Any]]:
        """
        Run scale testing simulation.

        Args:
            concurrent_users: Number of concurrent users to simulate
            duration_seconds: Test duration
        """
        return Result.ok(
            {
                "message": "Scale test initiated",
                "concurrent_users": concurrent_users,
                "duration_seconds": duration_seconds,
                "status": "running",
            }
        )

    return [metrics, cache_stats, optimize_performance, scale_test]


# ---------------------------------------------------------------------------
# DomainRouteConfig + Multi-Factory wiring
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
    Wire advanced API routes using DomainRouteConfig (Multi-Factory variant).

    Primary: calendar_optimization_orchestrator routes via DomainRouteConfig.
    Extensions: jupyter_sync and performance_optimization factories appended
    conditionally after primary registration.

    See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
    """
    routes = register_domain_routes(app, rt, services, ADVANCED_CONFIG)

    if services and services.jupyter_sync:
        routes.extend(create_jupyter_sync_routes(app, rt, services.jupyter_sync, services.user))

    if services and services.performance_optimization:
        routes.extend(
            create_performance_routes(app, rt, services.performance_optimization, services.user)
        )


__all__ = ["create_advanced_routes"]
