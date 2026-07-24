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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fasthtml.common import StaticFiles, fast_app
from starlette.middleware import Middleware

from adapters.inbound.auth.context_middleware import AuthContextMiddleware
from adapters.inbound.boundary import install_malformed_json_guard
from adapters.inbound.csrf import CSRFMiddleware
from adapters.inbound.middleware import (
    RequestIDMiddleware,
    RequestTimingMiddleware,
    StaticCacheHeadersMiddleware,
)
from core.config import UnifiedConfig
from core.ports.infrastructure_protocols import DrainableEventBusOperations, EventBusOperations
from core.ports.service_protocols import GraphAuthOperations
from core.utils.logging import get_logger
from services_bootstrap import Services, compose_services
from ui.theme import chartjs_headers, skuel_headers

try:
    from starlette.applications import ASGIApp
except ImportError:
    # Fallback if starlette types aren't available
    ASGIApp = Any

logger = get_logger("skuel.bootstrap")

# Module-level handle for the graph-health poller so the task isn't
# garbage-collected mid-flight (RUF006); lives until process exit.
_graph_health_task: "asyncio.Task[None] | None" = None


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
    event_bus: Any  # InMemoryEventBus — held for graceful drain on shutdown


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
            _query_metrics_cache,
        ) = await _build_infrastructure()

        # Step 3: Compose business services
        services = await _compose_services(
            neo4j_adapter, event_bus, config, prometheus_metrics, metrics_cache
        )

        # Step 4: Wire routes
        static_dir = getattr(config.application, "static_directory", None)
        if services.graph_auth is None:
            # Fail-fast: AuthContextMiddleware enforces graph sessions per
            # request — an app without graph_auth cannot revoke sessions
            raise RuntimeError("Service composition produced no graph_auth service")
        app, rt = _create_web_app(config, services.graph_auth, static_dir)

        await _wire_routes(app, rt, services, config, prometheus_metrics)

        container = AppContainer(
            app=app,
            rt=rt,
            services=services,
            config=config,
            prometheus_metrics=prometheus_metrics,
            event_bus=event_bus,
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
    async def update_graph_health_metrics() -> None:
        """
        Background task to query Neo4j for graph health statistics.

        Runs every 5 minutes to track:
        - Graph density (avg relationships per entity)
        - Relationship counts by layer
        - Lateral relationship breakdown
        - Blocking/dependency chains
        - Orphaned entities
        - Knowledge-subgraph structural health (ADR-080 Horizon-1): Ku count,
          orphan Kus, avg Ku degree, composition/prerequisite/ORGANIZES coverage
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

                # Query 4: Knowledge-subgraph structural health (ADR-080 Horizon-1).
                # Knowledge-scoped view — the raw signals the KnowledgeHealthService
                # interprets, matching KnowledgeHealthBackend. Degree/orphans exclude
                # learner-state telemetry (_TELEMETRY_EDGE_LIST) so the gauge stays
                # structural as usage grows; prerequisite/ORGANIZES counts scope BOTH
                # endpoints to knowledge nodes (DEPENDS_ON is also the Task edge;
                # ORGANIZES is used across domains).
                query_knowledge = """
                CALL () {
                    MATCH (k:Entity {entity_type: 'ku'})
                    WITH k, count{ (k)-[r]-() WHERE NOT type(r) IN
                        ['VIEWED','IN_PROGRESS','MASTERED','MARKED_AS_READ',
                         'BOOKMARKED','INTERESTED_IN','PINNED','PINNED_TODAY'] } AS deg
                    RETURN count(k) AS total_kus,
                           coalesce(avg(deg), 0.0) AS avg_degree,
                           count(CASE WHEN deg = 0 THEN 1 END) AS orphan_kus
                }
                CALL () {
                    MATCH (k:Entity {entity_type: 'ku'})
                    WHERE exists{ (:Entity {entity_type: 'path_step'})
                                  -[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(k) }
                    RETURN count(k) AS composed_kus
                }
                CALL () {
                    RETURN count{ (a)-[:PREREQUISITE_FOR|DEPENDS_ON|REQUIRES_PREREQUISITE|REQUIRES_STEP]->(b)
                        WHERE (a.entity_type IN ['ku','path_step','learning_path','exercise'])
                          AND (b.entity_type IN ['ku','path_step','learning_path','exercise'])
                    } AS prerequisite_edges
                }
                CALL () {
                    RETURN count{ (a)-[:ORGANIZES]->(b)
                        WHERE (a.entity_type IN ['ku','path_step','learning_path','exercise'])
                          AND (b.entity_type IN ['ku','path_step','learning_path','exercise'])
                    } AS organizes_edges
                }
                RETURN total_kus, avg_degree, orphan_kus, composed_kus,
                       prerequisite_edges, organizes_edges
                """
                result_knowledge = await neo4j_adapter.driver.execute_query(query_knowledge)
                if result_knowledge.records:
                    krec = result_knowledge.records[0]
                    prometheus_metrics.relationships.knowledge_kus_total.set(krec["total_kus"])
                    prometheus_metrics.relationships.knowledge_orphan_kus.set(krec["orphan_kus"])
                    prometheus_metrics.relationships.knowledge_avg_ku_degree.set(krec["avg_degree"])
                    prometheus_metrics.relationships.knowledge_composed_kus.set(
                        krec["composed_kus"]
                    )
                    prometheus_metrics.relationships.knowledge_prerequisite_edges.set(
                        krec["prerequisite_edges"]
                    )
                    prometheus_metrics.relationships.knowledge_organizes_edges.set(
                        krec["organizes_edges"]
                    )

                logger.debug("✅ Graph health metrics updated")

            except Exception as e:
                logger.error(f"Error updating graph health metrics: {e}")

    # Reference kept so the poller isn't garbage-collected mid-flight (RUF006);
    # module-level lifetime is intentional — it runs until process exit.
    global _graph_health_task
    _graph_health_task = asyncio.create_task(update_graph_health_metrics())
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
        error = services_result.expect_error()
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


def _create_web_app(
    _config: UnifiedConfig,
    graph_auth: GraphAuthOperations,
    static_directory: str | None = None,
) -> tuple[Any, Any]:
    """
    Create FastHTML app with headers but no routes yet.

    Args:
        config: Application configuration
        graph_auth: GraphAuthService for per-request session enforcement
            (AuthContextMiddleware fail-fasts on None)
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
            # SKUEL headers (output.css + Lucide + HTMX + Alpine + main.css + skuel.js)
            *skuel_headers(),
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

    # Malformed application/json bodies fail inside FastHTML's parameter
    # extraction — before any route guard runs — so without this chokepoint
    # they surface as 500s instead of a validation 400.
    install_malformed_json_guard(app)

    # Auth context — enforces the graph session per request (revoked sessions
    # force re-login) and mirrors session auth flags into a ContextVar so page
    # chrome (BasePage/navbar in ui/) reads auth state without importing
    # adapters. MUST run INSIDE SessionMiddleware to see request.session:
    # FastHTML appends the session middleware last (innermost), and
    # add_middleware() prepends (outermost) — so append directly instead of
    # using add_middleware(), which would place this outside the session.
    app.user_middleware.append(Middleware(AuthContextMiddleware, graph_auth=graph_auth))

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

    # One static mechanism: the /static mount below. fast_app() also installs
    # a root-scope extension catch-all (`/{fname:path}.{ext:static}` serving
    # from CWD) which (a) served ANY static-ext repo file publicly (verified:
    # /tailwind.config.js → 200) and (b) shadowed every root-scope .js/.html
    # route registered after it — /service-worker.js and /offline.html 404'd,
    # so the PWA service worker never installed (TECHNICAL_DEBT item 11).
    app.router.routes = [
        r for r in app.router.routes if "{fname:path}" not in getattr(r, "path", "")
    ]

    # Mount static files (will work even if directory creation failed).
    # Cache headers are applied via StaticCacheHeadersMiddleware below.
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # Add request ID middleware for log correlation
    # Adds X-Request-ID header to responses and sets context var for structured logs
    app.add_middleware(RequestIDMiddleware)

    # Add request timing middleware for performance diagnosis
    app.add_middleware(RequestTimingMiddleware)

    # Force browser revalidation of static assets (Cache-Control: no-cache).
    # Without this, heuristic caching can serve a stale asset without checking the
    # server — that once hid a fixed skuel.js behind a cached broken version.
    #
    # TODO(caching): Revisit static caching strategy. `no-cache` is blunt but
    # always-correct; a proper scheme would cache version-stamped vendor assets
    # (lucide/alpine/htmx/chart.js/vis-network) as immutable + long-lived and
    # content-hash app assets (skuel.js, output.css). Needs a planning pass to
    # understand cache semantics before changing. See memory:
    # project_lucide_mutationobserver_infinite_loop.
    app.add_middleware(StaticCacheHeadersMiddleware)

    # Browser security headers (SecurityHeadersMiddleware) are NOT registered
    # here: add_middleware would place them inside Starlette's
    # ServerErrorMiddleware, leaving unhandled-exception 500s unstamped
    # (Codex #794). main.py wraps the served app as the outermost ASGI layer
    # instead, covering every response including 500s.

    # CSRF defense-in-depth — mints csrf_token cookie on first response so the
    # HTMX layer can echo it back on state-changing requests. SameSite=Strict
    # on the session cookie is still the primary defense; this is the revert
    # lever if that ever gets loosened.
    app.add_middleware(CSRFMiddleware)

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

    # System routes (includes SystemService initialization).
    # Initialize the SystemService instance composed in compose.py — the SAME
    # object the AdminOrchestrator captured. Creating a fresh instance here would
    # register checkers on a throwaway the orchestrator never sees, leaving
    # /admin/system with empty component health.
    from core.services.system_service_init import initialize_system_service

    assert services.system is not None, "SystemService must be composed before initialization"
    init_result = await initialize_system_service(services.system, services)
    if init_result.is_error:
        raise ValueError(f"Failed to initialize SystemService: {init_result.error}")

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

    # -- Explore (merged Ku + PathStep discovery) --
    from adapters.inbound.explore_routes import create_explore_routes

    create_explore_routes(app, rt, services, None)

    # -- Curriculum --
    from adapters.inbound.ku_routes import create_ku_routes

    create_ku_routes(app, rt, services, None)

    from adapters.inbound.exercises_routes import create_exercises_routes

    create_exercises_routes(app, rt, services)

    from adapters.inbound.revised_exercises_routes import create_revised_exercises_routes

    create_revised_exercises_routes(app, rt, services)

    from adapters.inbound.pathways_routes import create_pathways_routes

    create_pathways_routes(app, rt, services, None)

    if services.askesis is not None:
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

    # -- UserEntry (ADR-054) — unified submissions + journals surface --
    from adapters.inbound.user_entry_routes import create_user_entry_routes

    create_user_entry_routes(app, rt, services, None)

    # -- PS+Activity Templates (Phase 5) --
    # 6 template CRUD route files + the engagement lifecycle endpoints. Templates
    # are SHARED-scope curriculum content, role-gated to TEACHER (admins satisfy
    # via has_permission). The engagement routes wrap PsEngagementService.
    from adapters.inbound.pathstep_choice_templates_routes import (
        create_pathstep_choice_templates_routes,
    )
    from adapters.inbound.pathstep_event_templates_routes import (
        create_pathstep_event_templates_routes,
    )
    from adapters.inbound.pathstep_goal_templates_routes import (
        create_pathstep_goal_templates_routes,
    )
    from adapters.inbound.pathstep_habit_templates_routes import (
        create_pathstep_habit_templates_routes,
    )
    from adapters.inbound.pathstep_principle_templates_routes import (
        create_pathstep_principle_templates_routes,
    )
    from adapters.inbound.pathstep_task_templates_routes import (
        create_pathstep_task_templates_routes,
    )
    from adapters.inbound.ps_engagement_routes import create_ps_engagement_routes

    create_pathstep_task_templates_routes(app, rt, services)
    create_pathstep_goal_templates_routes(app, rt, services)
    create_pathstep_habit_templates_routes(app, rt, services)
    create_pathstep_event_templates_routes(app, rt, services)
    create_pathstep_choice_templates_routes(app, rt, services)
    create_pathstep_principle_templates_routes(app, rt, services)
    create_ps_engagement_routes(app, rt, services)

    # Teacher-facing template authoring UI (panel on PS detail + full-page
    # create/edit forms). Wraps the JSON CRUD with HTML forms.
    from adapters.inbound.templates_ui import create_templates_ui_routes

    create_templates_ui_routes(app, rt, services)

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

    from adapters.inbound.self_checkin_routes import create_self_checkin_routes

    create_self_checkin_routes(app, rt, services, None)

    from adapters.inbound.search_routes import create_search_routes

    create_search_routes(app, rt, services)

    from adapters.inbound.picker_routes import create_picker_routes

    create_picker_routes(app, rt, services)

    from adapters.inbound.analytics_routes import create_analytics_routes

    create_analytics_routes(app, rt, services)

    from adapters.inbound.calendar_routes import create_calendar_routes

    create_calendar_routes(app, rt, services)

    from adapters.inbound.ingestion_routes import create_ingestion_routes

    create_ingestion_routes(app, rt, services)

    if services and services.vault_reconciler:
        from adapters.inbound.vault_routes import create_vault_routes

        create_vault_routes(
            app,
            rt,
            services.vault_reconciler,
            services.user,
            entry_grounding=services.entry_grounding,
        )

    if services and services.user:
        from adapters.inbound.device_routes import create_device_routes

        create_device_routes(app, rt, services.user)

    from adapters.inbound.home_routes import create_home_routes

    create_home_routes(app, rt, services)

    from adapters.inbound.today_routes import create_today_routes

    create_today_routes(app, rt, services)

    from adapters.inbound.journals_routes import create_journals_routes

    create_journals_routes(app, rt, services)

    from adapters.inbound.settings_routes import create_settings_routes

    create_settings_routes(app, rt, services)

    from adapters.inbound.notifications_routes import create_notifications_routes

    create_notifications_routes(app, rt, services)

    from adapters.inbound.groups_routes import create_groups_routes

    create_groups_routes(app, rt, services)

    from adapters.inbound.groups_hub_routes import create_groups_hub_routes

    create_groups_hub_routes(app, rt, services)

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
    from adapters.inbound.library_routes import create_library_routes

    create_library_routes(app, rt, services)

    from adapters.inbound.learning_paths_ui import create_learning_paths_ui_routes

    create_learning_paths_ui_routes(app, rt, services)

    # ========================================================================
    # Section 3: MANUAL ROUTES (custom wiring — not DomainRouteConfig)
    # ========================================================================

    from adapters.inbound.admin_dashboard_ui import create_admin_dashboard_routes

    assert services.admin_orchestrator is not None, "AdminOrchestrator not initialised"
    assert services.prereq_suggestions is not None, "PrereqSuggestionService not initialised"
    create_admin_dashboard_routes(
        app,
        rt,
        orchestrator=services.admin_orchestrator,
        prereq_suggestions=services.prereq_suggestions,
    )

    if services.cross_domain_analytics:
        from adapters.inbound.analytics_api import register_analytics_routes

        register_analytics_routes(app, services)

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


async def startup_skuel(
    container: AppContainer,
) -> None:  # skuel-lint: disable=SKUEL029 -- lifespan lifecycle: awaited by skuel_lifespan; spawns asyncio.create_task workers
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
            "✅ Embedding background worker started (12 embeddable entity types + content chunks)"
        )
    else:
        logger.info(
            "⏭️  Embedding background worker not available — no embeddings this process "
            "(ingestion never embeds inline, ADR-074)"
        )

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

        # Stop schema-change monitoring if it was started (opt-in via NEO4J_SCHEMA_MONITORING).
        # The detector owns its own poll task; stop_schema_monitoring() cancels it cleanly.
        if container.config.database.schema_monitoring_enabled:
            graph_adapter = container.services.graph_adapter
            if graph_adapter is not None:
                logger.info("🛑 Stopping schema-change monitoring...")
                await graph_adapter.stop_schema_monitoring()
                logger.info("✅ Schema-change monitoring stopped")

        # Drain in-flight event bus handlers before services are torn down so
        # handlers can still reach their service dependencies during the drain.
        if container.event_bus is not None and isinstance(
            container.event_bus, DrainableEventBusOperations
        ):
            drainable = container.event_bus
            pending = drainable.get_pending_task_count()
            if pending:
                logger.info(f"⏳ Draining {pending} event bus task(s) (5s timeout)...")
                try:
                    await drainable.wait_for_pending_tasks(timeout_seconds=5.0)
                    logger.info("✅ Event bus drained")
                except TimeoutError:
                    logger.warning("⚠️  Event bus drain timed out — cancelling remaining tasks")
                    drainable.cancel_all_tasks()

        # Single cleanup path through Services.stop()
        await container.services.cleanup()
        logger.info("✅ Application shutdown complete")
    except Exception as e:
        logger.warning(f"⚠️ Error during shutdown: {e}")
        # Re-raise to ensure shutdown failures are visible
        raise


async def skuel_lifespan(app):
    """
    Lifespan async generator for the SKUEL application.

    FastHTML's ``Lifespan`` wraps this generator itself (``async for state in
    ls(app)``), so it must be a bare async generator — NOT an
    ``@asynccontextmanager``. The ``try/finally`` still guarantees shutdown
    cleanup when the generator is closed, even with the reloader.
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
