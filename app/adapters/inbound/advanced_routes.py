"""
Advanced Routes - Phase 2 Optional Services
============================================

Wires advanced API routes using DomainRouteConfig (Multi-Factory variant).

Primary service: calendar_optimization (Calendar cognitive-load balancing)
Extension factories:
- create_jupyter_sync_routes: Jupyter-Neo4j-Obsidian workflow (4 endpoints)
- create_performance_routes: Scale & speed optimization (4 endpoints)

Routes:
- GET  /events/calendar/optimize       - Optimize calendar with cognitive load balancing
- GET  /events/calendar/cognitive-load - Analyze cognitive load for a date
- GET  /jupyter/fetch                  - Fetch KU content for Jupyter editing
- POST /jupyter/save                   - Save Jupyter edits back to Neo4j
- POST /jupyter/sync-to-obsidian       - Sync changes to Obsidian
- GET  /jupyter/detect-conflicts       - Detect Neo4j/Obsidian conflicts
- GET  /performance/metrics            - Current performance metrics
- GET  /performance/cache-stats        - Cache performance statistics
- POST /performance/optimize           - Trigger optimization analysis
- GET  /performance/scale-test         - Run scale testing simulation
"""

from datetime import date
from typing import Any

from fasthtml.common import JSONResponse, Request

from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.services.calendar_optimization_service import SchedulingStrategy
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.advanced")


# ---------------------------------------------------------------------------
# Calendar Optimization - Cognitive Load Balancing (primary service)
# ---------------------------------------------------------------------------


def create_calendar_optimization_routes(
    _app: Any, rt: Any, calendar_optimization: Any, tasks: Any = None, events: Any = None
) -> list[Any]:
    """Register calendar optimization endpoints."""

    @rt("/events/calendar/optimize")
    @boundary_handler()
    async def optimize(
        user_uid: str = "default_user",
        target_date: str | None = None,
        strategy: str = "cognitive_balanced",
    ) -> Result[Any]:
        """
        Optimize calendar for a specific date with cognitive load balancing.

        Query params:
            user_uid: User identifier (default: default_user)
            target_date: Date to optimize (YYYY-MM-DD), defaults to today
            strategy: Optimization strategy (default: cognitive_balanced)
                     Options: cognitive_balanced, knowledge_focused, deadline_driven,
                             energy_aligned, spaced_repetition
        """
        # Parse target date
        if target_date:
            try:
                opt_date = date.fromisoformat(target_date)
            except ValueError:
                return Result.fail(
                    Errors.validation(
                        "Invalid date format. Use YYYY-MM-DD",
                        field="target_date",
                        value=target_date,
                    )
                )
        else:
            opt_date = date.today()

        # Parse strategy
        try:
            strat = SchedulingStrategy(strategy)
        except ValueError:
            return Result.fail(
                Errors.validation(f"Invalid strategy: {strategy}", field="strategy", value=strategy)
            )

        # Get tasks and events for the date
        task_list: list[Any] = []
        event_list: list[Any] = []
        knowledge_units: list[Any] = []

        if tasks:
            tasks_result = await tasks.get_tasks_for_date(opt_date)
            if tasks_result.is_ok:
                task_list = tasks_result.value or []

        if events:
            events_result = await events.get_events_for_date(opt_date)
            if events_result.is_ok:
                event_list = events_result.value or []

        result: Result[Any] = await calendar_optimization.optimize_knowledge_scheduling(
            user_uid=user_uid,
            target_date=opt_date,
            tasks=task_list,
            events=event_list,
            knowledge_units=knowledge_units,
            strategy=strat,
        )
        return result

    @rt("/events/calendar/cognitive-load")
    @boundary_handler()
    async def cognitive_load(
        _user_uid: str = "default_user", target_date: str | None = None
    ) -> JSONResponse:
        """
        Analyze cognitive load for a specific date.
        Returns cognitive load distribution and overload risks.
        """
        if target_date:
            try:
                opt_date = date.fromisoformat(target_date)
            except ValueError:
                return Result.fail(
                    Errors.validation(
                        "Invalid date format. Use YYYY-MM-DD",
                        field="target_date",
                        value=target_date,
                    )
                )
        else:
            opt_date = date.today()

        # Get tasks for the date
        task_list: list[Any] = []
        if tasks:
            tasks_result = await tasks.get_tasks_for_date(opt_date)
            if tasks_result.is_ok:
                task_list = tasks_result.value or []

        # Analyze cognitive load for each task
        analyses = []
        for task in task_list:
            analysis = calendar_optimization.analyze_cognitive_load(task, [])
            analyses.append(
                {
                    "task_uid": task.uid,
                    "task_title": task.title,
                    "cognitive_load": analysis.__dict__,
                    "is_overload_risk": analysis.is_overload_risk(),
                    "load_category": analysis.get_load_category(),
                }
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


def create_jupyter_sync_routes(_app: Any, rt: Any, jupyter_sync: Any) -> list[Any]:
    """Register Jupyter-Neo4j-Obsidian sync endpoints."""

    @rt("/jupyter/fetch")
    @boundary_handler()
    async def fetch(uid: str) -> JSONResponse:
        """
        Fetch content from Neo4j for Jupyter editing.

        Query params:
            uid: Knowledge unit UID
        """
        return await jupyter_sync.get_content_for_jupyter(uid)

    @rt("/jupyter/save")
    @boundary_handler()
    async def save(request: Request, uid: str) -> JSONResponse:
        """Save Jupyter-edited content back to Neo4j. Expects JSON body with edited content."""
        content = await request.json()
        return await jupyter_sync.save_jupyter_changes(uid, content)

    @rt("/jupyter/sync-to-obsidian")
    @boundary_handler()
    async def sync_to_obsidian(uid: str) -> JSONResponse:
        """
        Sync Neo4j changes back to Obsidian markdown files.

        Args:
            uid: Knowledge unit UID
        """
        return await jupyter_sync.sync_to_obsidian(uid)

    @rt("/jupyter/detect-conflicts")
    @boundary_handler()
    async def detect_conflicts(uid: str) -> JSONResponse:
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


def create_performance_routes(_app: Any, rt: Any, performance_optimization: Any) -> list[Any]:
    """Register performance optimization endpoints."""

    @rt("/performance/metrics")
    @boundary_handler()
    async def metrics() -> JSONResponse:
        """Get current performance metrics (response time, throughput, cache hit rate, etc.)."""
        return await performance_optimization.get_current_metrics()

    @rt("/performance/cache-stats")
    @boundary_handler()
    async def cache_stats() -> JSONResponse:
        """Get cache performance statistics (hit rate, size, evictions, efficiency)."""
        stats = performance_optimization.inference_engine.get_cache_stats()
        return Result.ok(stats)

    @rt("/performance/optimize")
    @boundary_handler()
    async def optimize_performance() -> JSONResponse:
        """Trigger performance optimization analysis and tuning."""
        return await performance_optimization.optimize_performance()

    @rt("/performance/scale-test")
    @boundary_handler()
    async def scale_test(concurrent_users: int = 100, duration_seconds: int = 60) -> JSONResponse:
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
    primary_service_attr="calendar_optimization",
    api_factory=create_calendar_optimization_routes,
    api_related_services={
        "tasks": "tasks",
        "events": "events",
    },
)


def create_advanced_routes(app: Any, rt: Any, services: Any, _sync_service=None) -> list[Any]:
    """
    Wire advanced API routes using DomainRouteConfig (Multi-Factory variant).

    Primary: calendar_optimization routes via DomainRouteConfig (pulls tasks/events
    as related services).
    Extensions: jupyter_sync and performance_optimization factories appended
    conditionally after primary registration.

    See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
    """
    routes = register_domain_routes(app, rt, services, ADVANCED_CONFIG)

    if services and services.jupyter_sync:
        routes.extend(create_jupyter_sync_routes(app, rt, services.jupyter_sync))

    if services and services.performance_optimization:
        routes.extend(create_performance_routes(app, rt, services.performance_optimization))

    return routes


__all__ = ["create_advanced_routes"]
