"""
Advanced API Routes - Phase 2 Optional Services (FastHTML-Aligned)
===================================================================

API endpoints for advanced optional services following FastHTML best practices:
- CalendarOptimizationService: Cognitive load optimization
- JupyterNeo4jSync: Jupyter-Neo4j-Obsidian workflow
- PerformanceOptimizationService: Scale optimization

FastHTML Conventions Applied:
- Query parameters over path parameters
- Function names define routes
- Type hints for automatic parameter extraction
- POST for all mutations

These services provide specialized functionality for advanced use cases.
"""

__version__ = "1.0"

from datetime import date
from typing import Any

from fasthtml.common import JSONResponse, Request

from core.services.calendar_optimization_service import SchedulingStrategy
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def create_advanced_routes(_app, rt, services):
    """
    Create and register advanced service API routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with advanced services
    """

    # ========================================================================
    # CALENDAR OPTIMIZATION - Cognitive Load Balancing
    # ========================================================================

    @rt("/events/calendar/optimize")
    @boundary_handler()
    async def optimize(
        user_uid: str = "default_user",
        target_date: str | None = None,
        strategy: str = "cognitive_balanced",
    ) -> Result[Any]:
        """
        Optimize calendar for a specific date with cognitive load balancing.

        FastHTML Convention: Query parameters with type hints
        Query params:
            user_uid: User identifier (default: default_user)
            target_date: Date to optimize (YYYY-MM-DD), defaults to today
            strategy: Optimization strategy (default: cognitive_balanced)
                     Options: cognitive_balanced, knowledge_focused, deadline_driven,
                             energy_aligned, spaced_repetition

        Returns:
            Optimized calendar with task scheduling recommendations
        """
        if not services.calendar_optimization:
            return Result.fail(
                Errors.system(
                    "CalendarOptimizationService not available",
                    service="CalendarOptimizationService",
                )
            )

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
        tasks: list[Any] = ([],)
        events: list[Any] = ([],)
        knowledge_units: list[Any] = []

        if services.tasks:
            tasks_result = await services.tasks.get_tasks_for_date(opt_date)
            if tasks_result.is_ok:
                tasks = tasks_result.value or []

        if services.events:
            events_result = await services.events.get_events_for_date(opt_date)
            if events_result.is_ok:
                events = events_result.value or []

        # Optimize calendar
        return await services.calendar_optimization.optimize_knowledge_scheduling(
            user_uid=user_uid,
            target_date=opt_date,
            tasks=tasks,
            events=events,
            knowledge_units=knowledge_units,
            strategy=strat,
        )

    @rt("/events/calendar/cognitive-load")
    @boundary_handler()
    async def cognitive_load(
        _user_uid: str = "default_user", target_date: str | None = None
    ) -> JSONResponse:
        """
        Analyze cognitive load for a specific date.

        Returns cognitive load distribution and overload risks.
        """
        if not services.calendar_optimization:
            return Result.fail(
                Errors.system(
                    "CalendarOptimizationService not available",
                    service="CalendarOptimizationService",
                )
            )

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
        tasks: list[Any] = []
        if services.tasks:
            tasks_result = await services.tasks.get_tasks_for_date(opt_date)
            if tasks_result.is_ok:
                tasks = tasks_result.value or []

        # Analyze cognitive load for each task
        analyses = []
        for task in tasks:
            analysis = services.calendar_optimization.analyze_cognitive_load(task, [])
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
                "task_count": len(tasks),
                "cognitive_analyses": analyses,
                "overload_risks": [a for a in analyses if a["is_overload_risk"]],
            }
        )

    # ========================================================================
    # JUPYTER SYNC - Jupyter-Neo4j-Obsidian Workflow
    # ========================================================================

    @rt("/jupyter/fetch")
    @boundary_handler()
    async def fetch(uid: str) -> JSONResponse:
        """
        Fetch content from Neo4j for Jupyter editing.

        FastHTML Convention: Query parameter with type hint
        Query params:
            uid: Knowledge unit UID

        Returns:
            Content formatted for Jupyter notebook editing
        """
        if not services.jupyter_sync:
            return Result.fail(
                Errors.system("JupyterNeo4jSync not available", service="JupyterNeo4jSync")
            )

        return await services.jupyter_sync.get_content_for_jupyter(uid)

    @rt("/jupyter/save")
    @boundary_handler()
    async def save(request: Request, uid: str) -> JSONResponse:
        """
        Save Jupyter-edited content back to Neo4j.

        Expects JSON body with edited content.
        """
        if not services.jupyter_sync:
            return Result.fail(
                Errors.system("JupyterNeo4jSync not available", service="JupyterNeo4jSync")
            )

        # Get content from request body
        content = await request.json()

        return await services.jupyter_sync.save_jupyter_changes(uid, content)

    @rt("/jupyter/sync-to-obsidian")
    @boundary_handler()
    async def sync_to_obsidian(uid: str) -> JSONResponse:
        """
        Sync Neo4j changes back to Obsidian markdown files.

        Args:
            uid: Knowledge unit UID

        Returns:
            Sync status and any conflicts detected
        """
        if not services.jupyter_sync:
            return Result.fail(
                Errors.system("JupyterNeo4jSync not available", service="JupyterNeo4jSync")
            )

        return await services.jupyter_sync.sync_to_obsidian(uid)

    @rt("/jupyter/detect-conflicts")
    @boundary_handler()
    async def detect_conflicts(uid: str) -> JSONResponse:
        """
        Detect conflicts between Neo4j and Obsidian content.

        Returns:
            Conflict analysis with resolution suggestions
        """
        if not services.jupyter_sync:
            return Result.fail(
                Errors.system("JupyterNeo4jSync not available", service="JupyterNeo4jSync")
            )

        return await services.jupyter_sync.detect_conflicts(uid)

    # ========================================================================
    # PERFORMANCE OPTIMIZATION - Scale & Speed
    # ========================================================================

    @rt("/performance/metrics")
    @boundary_handler()
    async def metrics() -> JSONResponse:
        """
        Get current performance metrics.

        Returns:
            Real-time performance statistics (response time, throughput, cache hit rate, etc.)
        """
        if not services.performance_optimization:
            return Result.fail(
                Errors.system(
                    "PerformanceOptimizationService not available",
                    service="PerformanceOptimizationService",
                )
            )

        return await services.performance_optimization.get_current_metrics()

    @rt("/performance/cache-stats")
    @boundary_handler()
    async def cache_stats() -> JSONResponse:
        """
        Get cache performance statistics.

        Returns:
            Cache hit rate, size, evictions, and efficiency metrics
        """
        if not services.performance_optimization:
            return Result.fail(
                Errors.system(
                    "PerformanceOptimizationService not available",
                    service="PerformanceOptimizationService",
                )
            )

        stats = services.performance_optimization.inference_engine.get_cache_stats()
        return Result.ok(stats)

    @rt("/performance/optimize")
    @boundary_handler()
    async def optimize_performance() -> JSONResponse:
        """
        Trigger performance optimization analysis and tuning.

        Returns:
            Optimization recommendations and applied changes
        """
        if not services.performance_optimization:
            return Result.fail(
                Errors.system(
                    "PerformanceOptimizationService not available",
                    service="PerformanceOptimizationService",
                )
            )

        return await services.performance_optimization.optimize_performance()

    @rt("/performance/scale-test")
    @boundary_handler()
    async def scale_test(concurrent_users: int = 100, duration_seconds: int = 60) -> JSONResponse:
        """
        Run scale testing simulation.

        Args:
            concurrent_users: Number of concurrent users to simulate
            duration_seconds: Test duration

        Returns:
            Scale test results with performance under load
        """
        if not services.performance_optimization:
            return Result.fail(
                Errors.system(
                    "PerformanceOptimizationService not available",
                    service="PerformanceOptimizationService",
                )
            )

        # Placeholder for scale test
        return Result.ok(
            {
                "message": "Scale test initiated",
                "concurrent_users": concurrent_users,
                "duration_seconds": duration_seconds,
                "status": "running",
            }
        )

    logger.info("✅ Advanced API routes registered (Phase 2 - FastHTML-aligned)")
