"""
SKUEL Composition Root
======================

Clean bootstrap following the composition root pattern.
main.py should only do three things:
1. Load config
2. Build services (once)
3. Wire routes/handlers via parameters (no globals)

This eliminates:
- Service registry globals
- Route imports of service locators
- Hidden dependencies in request handlers
"""

__version__ = "1.0"


import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fasthtml.common import StaticFiles, fast_app

from adapters.inbound.middleware import RequestIDMiddleware
from core.config import UnifiedConfig
from core.ports.infrastructure_protocols import EventBusOperations
from core.utils.logging import get_logger
from services_bootstrap import Services, compose_services
from ui.theme import chartjs_headers, monster_headers

try:
    from starlette.applications import ASGIApp
except ImportError:
    # Fallback if starlette types aren't available
    ASGIApp = Any

logger = get_logger("skuel.bootstrap")


@dataclass(frozen=True)
class AppContainer:
    """
    Simple app container - the result of composition.
    Contains everything needed to run SKUEL with explicit dependencies.
    """

    app: Any  # FastHTML app
    rt: Any  # FastHTML router
    services: Services  # Business services (includes SearchRouter)
    config: UnifiedConfig  # Application configuration
    prometheus_metrics: Any  # Prometheus metrics


async def bootstrap_skuel() -> AppContainer:
    """
    Composition root: THE SINGLE PLACE where the entire app is wired together.

    Clean 4-step bootstrap process:
    1. Load configuration
    2. Build infrastructure (DB, event bus)
    3. Compose business services
    4. Wire routes with explicit dependencies

    Returns complete, ready-to-run application.
    """
    logger.info("🚀 Starting SKUEL bootstrap (composition root)")

    try:
        # Step 1: Load configuration
        config = _load_config()

        # Step 2: Build infrastructure
        (
            neo4j_adapter,
            event_bus,
            prometheus_metrics,
            metrics_cache,
            query_metrics_cache,
        ) = await _build_infrastructure()

        # Step 3: Compose business services
        services = await _compose_services(
            neo4j_adapter, event_bus, config, prometheus_metrics, metrics_cache
        )

        # Step 4: Wire routes
        static_dir = getattr(config.application, "static_directory", None)
        app, rt = _create_web_app(config, static_dir)

        await _wire_routes(app, rt, services, config, prometheus_metrics)

        container = AppContainer(
            app=app, rt=rt, services=services, config=config, prometheus_metrics=prometheus_metrics
        )

        # Store container on app state for lifespan access
        app.state.container = container
        # Also store services directly for test access
        app.state.services = services

        logger.info("🎉 SKUEL bootstrap complete - composition root pattern")
        return container

    except Exception as e:
        # Don't log here - let the main handler log it once
        raise RuntimeError(f"SKUEL bootstrap failed: {e}") from e


def _load_config() -> UnifiedConfig:
    """Step 1: Load and validate application configuration"""
    from core.config import get_settings, validate_environment

    # Validate environment requirements first
    # This will raise ConfigurationError if requirements not met
    validate_environment()
    logger.info("✅ Environment validated - all requirements met")

    # Load application settings
    config = get_settings()
    logger.info(f"✅ Configuration loaded: {config.environment}")
    return config


async def _build_infrastructure() -> tuple[Any, EventBusOperations, Any, Any, Any]:
    """Step 2: Build core infrastructure (database, event bus, metrics)"""
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.infrastructure.monitoring import MetricsCache, PrometheusMetrics, QueryMetricsCache

    # Import MetricsEventHandler here to avoid circular dependency
    from core.infrastructure.monitoring.metrics_event_handler import MetricsEventHandler

    # Import set_query_metrics_cache to wire global instance
    from core.utils.metrics import set_query_metrics_cache

    # Create Neo4j adapter and connect
    neo4j_adapter = Neo4jAdapter()
    await neo4j_adapter.connect()
    logger.info("✅ Neo4j adapter connected")

    # Initialize Prometheus metrics
    # Prometheus is THE source of truth for production monitoring
    prometheus_metrics = PrometheusMetrics()
    logger.info("✅ Prometheus metrics initialized (source of truth)")

    # Initialize metrics cache
    # Cache provides debugging access (last 100 items) while Prometheus is primary
    metrics_cache = MetricsCache(prometheus_metrics, enabled=True)
    logger.info("✅ MetricsCache initialized (debugging access to last 100 items)")

    # Initialize query metrics cache
    # Query-level performance tracking with Prometheus as source of truth
    query_metrics_cache = QueryMetricsCache(prometheus_metrics, enabled=True)
    set_query_metrics_cache(query_metrics_cache)
    logger.info("✅ QueryMetricsCache initialized and set as global instance")

    # Initialize event bus with metrics cache
    event_bus = InMemoryEventBus(metrics_cache=metrics_cache)
    logger.info("✅ Event bus initialized with MetricsCache")

    # Initialize metrics event handler
    # Subscribes to domain events and tracks entity creation/completion
    _metrics_handler = MetricsEventHandler(event_bus, prometheus_metrics)
    logger.info("✅ MetricsEventHandler initialized and subscribed to domain events")

    # Start background task to periodically update graph health metrics
    async def update_graph_health_metrics():
        """
        Background task to query Neo4j for graph health statistics.

        Runs every 5 minutes to track:
        - Graph density (avg relationships per entity)
        - Relationship counts by layer
        - Lateral relationship breakdown
        - Blocking/dependency chains
        - Orphaned entities
        """
        while True:
            try:
                await asyncio.sleep(300)  # Update every 5 minutes

                # Query 1: Overall graph stats (entities, relationships, density)
                query_stats = """
                MATCH (n)
                WITH count(n) as total_nodes
                MATCH ()-[r]->()
                WITH total_nodes, count(r) as total_rels
                RETURN
                    total_nodes,
                    total_rels,
                    CASE WHEN total_nodes > 0
                         THEN toFloat(total_rels) / total_nodes
                         ELSE 0.0
                    END as density
                """
                result_stats = await neo4j_adapter.driver.execute_query(query_stats)
                if result_stats.records:
                    record = result_stats.records[0]
                    prometheus_metrics.relationships.total_entities.set(record["total_nodes"])
                    prometheus_metrics.relationships.total_relationships.set(record["total_rels"])
                    prometheus_metrics.relationships.graph_density.set(record["density"])

                # Query 2: Orphaned entities (nodes with no relationships)
                query_orphaned = """
                MATCH (n)
                WHERE NOT (n)-[]-()
                RETURN count(n) as orphaned_count
                """
                result_orphaned = await neo4j_adapter.driver.execute_query(query_orphaned)
                if result_orphaned.records:
                    orphaned_count = result_orphaned.records[0]["orphaned_count"]
                    prometheus_metrics.relationships.orphaned_entities.set(orphaned_count)

                # Query 3: Specific relationship type counts
                query_rel_types = """
                MATCH ()-[r]->()
                RETURN type(r) as rel_type, count(*) as count
                """
                result_rel_types = await neo4j_adapter.driver.execute_query(query_rel_types)

                # Track specific relationship types
                blocks_count = 0
                enables_count = 0
                contains_count = 0
                organizes_count = 0

                # Layer counts
                hierarchical_count = 0
                lateral_count = 0
                semantic_count = 0
                cross_domain_count = 0

                # Lateral category counts
                structural_count = 0  # SIBLING, COUSIN
                dependency_count = 0  # BLOCKS, ENABLES
                semantic_lateral_count = 0  # RELATED_TO, SIMILAR_TO
                associative_count = 0  # ALTERNATIVE_TO, STACKS_WITH

                for record in result_rel_types.records:
                    rel_type = record["rel_type"]
                    count = record["count"]

                    # Specific types
                    if rel_type == "BLOCKS":
                        blocks_count = count
                        dependency_count += count
                        lateral_count += count
                    elif rel_type == "ENABLES":
                        enables_count = count
                        dependency_count += count
                        lateral_count += count
                    elif rel_type == "CONTAINS":
                        contains_count = count
                        hierarchical_count += count
                    elif rel_type == "ORGANIZES":
                        organizes_count = count
                        hierarchical_count += count
                    elif rel_type in ("SIBLING", "COUSIN"):
                        structural_count += count
                        lateral_count += count
                    elif rel_type in ("RELATED_TO", "SIMILAR_TO"):
                        semantic_lateral_count += count
                        lateral_count += count
                    elif rel_type in ("ALTERNATIVE_TO", "STACKS_WITH"):
                        associative_count += count
                        lateral_count += count
                    elif rel_type == "SERVES_LIFE_PATH":
                        cross_domain_count += count
                    elif ":" in rel_type:  # Semantic relationships (namespace:type)
                        semantic_count += count

                # Update specific relationship counts
                prometheus_metrics.relationships.blocking_relationships.set(blocks_count)
                prometheus_metrics.relationships.enables_relationships.set(enables_count)
                prometheus_metrics.relationships.contains_relationships.set(contains_count)
                prometheus_metrics.relationships.organizes_relationships.set(organizes_count)

                # Update layer counts
                prometheus_metrics.relationships.relationships_by_layer.labels(
                    layer="hierarchical"
                ).set(hierarchical_count)
                prometheus_metrics.relationships.relationships_by_layer.labels(layer="lateral").set(
                    lateral_count
                )
                prometheus_metrics.relationships.relationships_by_layer.labels(
                    layer="semantic"
                ).set(semantic_count)
                prometheus_metrics.relationships.relationships_by_layer.labels(
                    layer="cross_domain"
                ).set(cross_domain_count)

                # Update lateral category counts
                prometheus_metrics.relationships.lateral_by_category.labels(
                    category="structural"
                ).set(structural_count)
                prometheus_metrics.relationships.lateral_by_category.labels(
                    category="dependency"
                ).set(dependency_count)
                prometheus_metrics.relationships.lateral_by_category.labels(
                    category="semantic"
                ).set(semantic_lateral_count)
                prometheus_metrics.relationships.lateral_by_category.labels(
                    category="associative"
                ).set(associative_count)

                logger.debug("✅ Graph health metrics updated")

            except Exception as e:
                logger.error(f"Error updating graph health metrics: {e}")

    asyncio.create_task(update_graph_health_metrics())
    logger.info("✅ Graph health metrics update task started (5 min interval)")

    return neo4j_adapter, event_bus, prometheus_metrics, metrics_cache, query_metrics_cache


async def _compose_services(
    neo4j_adapter: Any,
    event_bus: EventBusOperations,
    config: UnifiedConfig,
    prometheus_metrics: Any,
    metrics_cache: Any,
) -> Services:
    """
    Step 3: Compose all business services with dependency injection.

    This is the composition root boundary where Results are converted to exceptions.
    Following "Result inside, exception at boundary" pattern.

    Returns:
        Services with all business services wired
    """
    services_result = await compose_services(
        neo4j_adapter, event_bus, config, prometheus_metrics, metrics_cache
    )

    # Convert Result to exception at boundary
    if services_result.is_error:
        error = services_result.error
        logger.error(f"❌ Service composition failed: {error.message}")
        raise RuntimeError(f"Failed to compose services: {error.message}") from None

    services = services_result.value
    logger.info("✅ All services composed and ready")
    return services


async def _wire_routes(
    app: Any,
    rt: Any,
    services: Services,
    config: UnifiedConfig,
    prometheus_metrics: Any,
) -> None:
    """Step 4: Wire all routes with explicit service dependencies"""
    await _wire_all_routes(app, rt, services, config, prometheus_metrics)
    logger.info("✅ Routes wired with explicit dependencies")


def _create_web_app(_config: UnifiedConfig, static_directory: str | None = None) -> tuple[Any, Any]:
    """
    Create FastHTML app with headers but no routes yet.

    Args:
        config: Application configuration
        static_directory: Override static files directory (defaults to ./static relative to current working directory)

    Returns:
        Tuple of (FastHTML app, router)
    """

    # Import UI foundation
    from adapters.inbound.auth import get_session_middleware_config

    # Get session configuration for FastHTML
    session_config = get_session_middleware_config()

    app, rt = fast_app(
        debug=True,
        live=True,
        pico=False,  # Disable pico CSS
        hdrs=(
            # SKUEL MonsterUI theme headers (includes HTMX, Alpine.js, custom CSS/JS)
            *monster_headers(),
            # Chart.js for data visualization
            *chartjs_headers(),
        ),
        lifespan=skuel_lifespan,
        # FastHTML built-in session support
        secret_key=session_config["secret_key"],
        session_cookie=session_config["session_cookie"],
        max_age=session_config["max_age"],
        sess_https_only=session_config["https_only"],
        same_site=session_config["same_site"],
    )

    logger.info("✅ Session support configured (FastHTML built-in)")

    # Configure static files path (idempotent and path-safe)
    # Default: ./static relative to current working directory (not source file)
    static_path = Path(static_directory).resolve() if static_directory else Path.cwd() / "static"

    # INFRASTRUCTURE TOLERANCE: Static directory creation is the ONE exception to fail-fast.
    # Rationale:
    # - Static files are PRESENTATION layer, not business logic
    # - API routes can serve requests without CSS/JS
    # - This allows app to run in minimal/degraded mode for debugging
    # - All BUSINESS dependencies (Neo4j, Deepgram, etc.) still fail-fast
    try:
        static_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Static directory ensured: {static_path}")
    except (PermissionError, OSError) as e:
        logger.warning(f"⚠️ Cannot create static directory: {static_path} - {e}")
        logger.warning("📝 INFRASTRUCTURE TOLERANCE: App will run but static files won't serve")

    # Mount static files (will work even if directory creation failed)
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # Add request ID middleware for log correlation
    # Adds X-Request-ID header to responses and sets context var for structured logs
    app.add_middleware(RequestIDMiddleware)

    return app, rt


async def _wire_all_routes(
    app: Any,
    rt: Any,
    services: Services,
    _config: UnifiedConfig,
    prometheus_metrics: Any,
) -> None:
    """Wire all routes with explicit service dependencies.

    Organized into 4 sections:
    1. INFRASTRUCTURE — system health, auth, admin, monitoring, metrics, graphql
    2. ENTITY DOMAIN ROUTES — all use DomainRouteConfig / register_domain_routes
       (NO guards needed: register_domain_routes returns [] if service is None)
    3. MANUAL ROUTES — custom wiring that doesn't fit DomainRouteConfig
    4. PWA ROUTES — root-scope static asset serving

    IMPORT BOUNDARY: Route modules are imported here to prevent them from importing
    the composition root. This maintains clean dependency direction.

    DEPENDENCY INJECTION CONTRACT: All route module create_*_routes() functions
    MUST accept services as explicit parameters. Route modules MUST NOT pull
    services from any global registry, service locator, or DI container.
    """

    # ========================================================================
    # Section 1: INFRASTRUCTURE (always registered)
    # ========================================================================

    # System routes (includes SystemService initialization)
    from core.services.system_service import SystemService
    from core.services.system_service_init import initialize_system_service

    system_service = SystemService()
    init_result = await initialize_system_service(system_service, services)
    if init_result.is_error:
        raise ValueError(f"Failed to initialize SystemService: {init_result.error}")
    services.system_service = system_service

    from adapters.inbound.system_routes import create_system_routes

    create_system_routes(app, rt, services)

    from adapters.inbound.auth_routes import create_auth_routes

    create_auth_routes(app, rt, services, None)

    from adapters.inbound.admin_routes import create_admin_routes

    create_admin_routes(app, rt, services, None)

    from adapters.inbound.monitoring_routes import create_monitoring_routes

    create_monitoring_routes(app, rt, services)

    from adapters.inbound.metrics_routes import create_metrics_routes

    create_metrics_routes(app, rt)

    from adapters.inbound.graphql_routes import create_graphql_routes

    create_graphql_routes(app, rt, services)

    # ========================================================================
    # Section 2: ENTITY DOMAIN ROUTES
    # All use DomainRouteConfig / register_domain_routes internally.
    # NO guards needed — register_domain_routes returns [] if service is None.
    # ========================================================================

    # -- Curriculum --
    from adapters.inbound.ku_routes import create_ku_routes

    create_ku_routes(app, rt, services, None)

    from adapters.inbound.exercises_routes import create_exercises_routes

    create_exercises_routes(app, rt, services)

    from adapters.inbound.revised_exercises_routes import create_revised_exercises_routes

    create_revised_exercises_routes(app, rt, services)

    from adapters.inbound.pathways_routes import create_pathways_routes

    create_pathways_routes(app, rt, services, None)

    from adapters.inbound.askesis_routes import create_askesis_routes

    create_askesis_routes(app, rt, services, None)

    # -- Activity Domain read-focused UI --
    from adapters.inbound.tasks_routes import create_tasks_routes

    create_tasks_routes(app, rt, services)

    from adapters.inbound.goals_routes import create_goals_routes

    create_goals_routes(app, rt, services)

    from adapters.inbound.habits_routes import create_habits_routes

    create_habits_routes(app, rt, services)

    from adapters.inbound.events_routes import create_events_routes

    create_events_routes(app, rt, services)

    from adapters.inbound.choices_routes import create_choices_routes

    create_choices_routes(app, rt, services)

    from adapters.inbound.principles_routes import create_principles_routes

    create_principles_routes(app, rt, services)

    # -- Submissions --
    from adapters.inbound.submissions_routes import create_submissions_routes

    create_submissions_routes(app, rt, services, None)

    # -- Journals --
    from adapters.inbound.journals_routes import create_journals_routes

    create_journals_routes(app, rt, services)

    # -- Forms --
    from adapters.inbound.form_templates_routes import create_form_templates_routes

    create_form_templates_routes(app, rt, services)

    from adapters.inbound.form_submissions_routes import create_form_submissions_routes

    create_form_submissions_routes(app, rt, services)

    # -- Other entity domains --
    from adapters.inbound.finance_routes import create_finance_routes

    create_finance_routes(app, rt, services, None)

    from adapters.inbound.lifepath_routes import create_lifepath_routes

    create_lifepath_routes(app, rt, services)

    from adapters.inbound.context_routes import create_context_aware_routes

    create_context_aware_routes(app, rt, services)

    from adapters.inbound.insights_routes import create_insights_routes

    create_insights_routes(app, rt, services, None)

    from adapters.inbound.search_routes import create_search_routes

    create_search_routes(app, rt, services)

    from adapters.inbound.analytics_routes import create_analytics_routes

    create_analytics_routes(app, rt, services)

    from adapters.inbound.calendar_routes import create_calendar_routes

    create_calendar_routes(app, rt, services)

    from adapters.inbound.ingestion_routes import create_ingestion_routes

    create_ingestion_routes(app, rt, services)

    from adapters.inbound.upload_routes import create_upload_routes

    create_upload_routes(app, rt, services)

    from adapters.inbound.notifications_routes import create_notifications_routes

    create_notifications_routes(app, rt, services)

    from adapters.inbound.groups_routes import create_groups_routes

    create_groups_routes(app, rt, services)

    from adapters.inbound.teaching_routes import create_teaching_routes

    create_teaching_routes(app, rt, services)

    from adapters.inbound.transcription_routes import create_transcription_routes

    create_transcription_routes(app, rt, services, None)

    # -- Graph / Visualization --
    from adapters.inbound.hierarchy_routes import create_hierarchy_routes

    create_hierarchy_routes(app, rt, services)

    from adapters.inbound.lateral_routes import create_lateral_routes

    create_lateral_routes(app, rt, services)

    from adapters.inbound.visualization_routes import create_visualization_routes

    create_visualization_routes(app, rt, services, None)

    from adapters.inbound.timeline_routes import create_timeline_routes

    create_timeline_routes(app, rt, services)

    from adapters.inbound.orchestration_routes import create_orchestration_routes

    create_orchestration_routes(app, rt, services)

    from adapters.inbound.advanced_routes import create_advanced_routes

    create_advanced_routes(app, rt, services)

    # -- Hubs --
    from adapters.inbound.study_routes import create_study_routes

    create_study_routes(app, rt, services)

    from adapters.inbound.curriculum_hub_routes import create_curriculum_hub_routes

    create_curriculum_hub_routes(app, rt, services)

    # ========================================================================
    # Section 3: MANUAL ROUTES (custom wiring — not DomainRouteConfig)
    # ========================================================================

    from adapters.inbound.admin_dashboard_ui import create_admin_dashboard_routes

    create_admin_dashboard_routes(app, rt, services)

    if services.cross_domain_analytics:
        from adapters.inbound.analytics_api import register_analytics_routes

        register_analytics_routes(app, services)

    # ORGANIZES hierarchy routes absorbed into path_steps_api.py (Lesson→PathStep merge)

    from adapters.inbound.ai_routes import create_ai_routes

    create_ai_routes(app, rt, services)

    from adapters.inbound.user_profile_ui import setup_user_profile_routes

    setup_user_profile_routes(rt, services)

    if services.user_relationships:
        from adapters.inbound.user_pins_api import create_user_pins_routes

        create_user_pins_routes(app, rt, services.user_relationships)

    # ========================================================================
    # Section 4: PWA ROUTES
    # ========================================================================

    from adapters.inbound.pwa_routes import create_pwa_routes

    create_pwa_routes(rt)

    # ========================================================================
    # Startup summary
    # ========================================================================

    route_count = len(getattr(app, "routes", []))
    logger.info(f"Route wiring complete: {route_count} routes registered")


# ============================================================================
# LIFECYCLE MANAGEMENT
# ============================================================================


async def startup_skuel(container: AppContainer) -> None:
    """Handle application startup events"""
    logger.info("🌟 SKUEL Application started on http://localhost:8000")

    # Start embedding background worker (async background task - January 2026)
    # Worker processes EmbeddingRequested events in batches for zero-latency user experience
    if container.services.embedding_worker:
        background_task = asyncio.create_task(
            container.services.embedding_worker.start(), name="embedding_worker"
        )
        # Store task reference on app state for shutdown cleanup
        container.app.state.embedding_worker_task = background_task
        logger.info(
            "✅ Embedding background worker started (processes Tasks, Goals, Habits, Events, Choices, Principles)"
        )
    else:
        logger.info("⏭️  Embedding background worker not available (embeddings only via ingestion)")

    # Start progress report background worker (February 2026)
    # Worker checks hourly for due schedules and generates AI_FEEDBACK Entity nodes
    if container.services.progress_report_worker:
        progress_task = asyncio.create_task(
            container.services.progress_report_worker.start(), name="progress_report_worker"
        )
        container.app.state.progress_report_worker_task = progress_task
        logger.info("✅ Progress report worker started (hourly schedule check)")
    else:
        logger.info("⏭️  Progress report worker not available")


async def shutdown_skuel(container: AppContainer) -> None:
    """Handle application shutdown with proper resource cleanup"""
    logger.info("👋 Shutting down SKUEL Application")

    try:
        # Stop embedding background worker if running (January 2026)
        embedding_worker_task = getattr(container.app.state, "embedding_worker_task", None)
        if embedding_worker_task and not embedding_worker_task.done():
            logger.info("🛑 Stopping embedding background worker...")
            embedding_worker_task.cancel()
            try:
                await embedding_worker_task
            except asyncio.CancelledError:
                logger.info("✅ Embedding background worker stopped")
            except Exception as e:
                logger.warning(f"⚠️  Error stopping embedding worker: {e}")

        # Stop progress report background worker if running (February 2026)
        progress_worker_task = getattr(container.app.state, "progress_report_worker_task", None)
        if progress_worker_task and not progress_worker_task.done():
            logger.info("🛑 Stopping progress report worker...")
            progress_worker_task.cancel()
            try:
                await progress_worker_task
            except asyncio.CancelledError:
                logger.info("✅ Progress report worker stopped")
            except Exception as e:
                logger.warning(f"⚠️  Error stopping progress report worker: {e}")

        # Single cleanup path through Services.stop()
        await container.services.cleanup()
        logger.info("✅ Application shutdown complete")
    except Exception as e:
        logger.warning(f"⚠️ Error during shutdown: {e}")
        # Re-raise to ensure shutdown failures are visible
        raise


@asynccontextmanager
async def skuel_lifespan(app):
    """
    Modern lifespan context manager for SKUEL application.

    Replaces deprecated @app.on_event("startup"/"shutdown") with proper
    async context manager that guarantees cleanup even with reloader.
    """
    # Get container from app state
    container = app.state.container

    # Startup
    await startup_skuel(container)
    logger.info("🚀 SKUEL lifespan startup complete")

    try:
        yield
    finally:
        # Shutdown (always runs)
        await shutdown_skuel(container)
        logger.info("🛑 SKUEL lifespan shutdown complete")
