"""Main bootstrap orchestration — compose_services() wires everything together."""

__version__ = "4.0"  # Entity type + cross-cutting system architecture

import os
from typing import TYPE_CHECKING, Any

from core.constants import EmbeddingGeometry
from core.events.embedding_publisher import EMBEDDING_EVENT_TYPES
from core.models.enums.neo_labels import NeoLabel
from core.ports import EventBusOperations
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from services_bootstrap._activity_services import _create_activity_services
from services_bootstrap._ai_wiring import _wire_ai_services
from services_bootstrap._backends import create_all_backends
from services_bootstrap._container import Services
from services_bootstrap._core_services import (
    _create_advanced_services,
    _create_core_services,
    _create_orchestration_services,
)
from services_bootstrap._event_wiring import _wire_event_subscribers
from services_bootstrap._intelligence_hub import _create_intelligence_hub
from services_bootstrap._learning_services import _create_learning_services

if TYPE_CHECKING:
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics

logger = get_logger("skuel.bootstrap")

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


def _bool_flag(name: str, *, default: bool) -> bool:
    """Strict tri-state env flag: unset → default, else must be a known boolean.

    Deliberately NOT IntelligenceTier.from_env's fail-open-to-FULL and
    deliberately NOT EMAIL_ENABLED's silent `not in (...)` → off: a typo in a
    capability-availability flag would silently DROP that capability on a stack
    whose health gate cannot see it. Malformed values fail composition instead —
    call this only inside compose_services' try, where the raise becomes
    Result.fail (same contract as the missing-credential raises).
    """
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise RuntimeError(f"{name}={raw!r} is not a recognised boolean")


async def compose_services(
    neo4j_adapter: Any,
    event_bus: EventBusOperations | None = None,
    config: Any = None,
    prometheus_metrics: "PrometheusMetrics | None" = None,
    metrics_cache: Any = None,
) -> Result[Services]:
    """
    Bootstrap function: creates all services with their dependencies.

    This is THE SINGLE PLACE where service wiring happens.
    No magic, no reflection, just explicit constructor injection.

    Following "Result inside, exception at boundary" pattern.

    **FAIL-FAST DESIGN**: All dependencies are REQUIRED. Service composition
    will fail immediately if any required API key or service is unavailable.

    Args:
        neo4j_adapter: Database adapter (satisfies GraphPort) - REQUIRED,
        event_bus: Event bus adapter (optional, will create default if None),
        config: UnifiedConfig for accessing configuration (optional, will load if None)
        prometheus_metrics: PrometheusMetrics for instrumentation (optional — January 2026)
        metrics_cache: MetricsCache for performance tracking (optional)

    Returns:
        Result[Services]: Success with wired services or failure with detailed error.
        SearchRouter is available via services.search_router.

    Raises:
        ValueError: If any required dependency is missing
    """
    logger.info("🔧 Composing service dependencies (FAIL-FAST mode)...")

    # Load config if not provided
    if config is None:
        from core.config import get_settings

        config = get_settings()

    # Determine intelligence tier (ADR-043)
    from core.config.intelligence_tier import IntelligenceTier

    tier = IntelligenceTier.from_env()
    if tier.ai_enabled:
        logger.info("🧠 Intelligence tier: FULL (analytics + AI services)")
    else:
        logger.info("🧠 Intelligence tier: CORE (analytics only — no API costs)")

    try:
        # ========================================================================
        # CREATE EVENT BUS (Event-Driven Architecture)
        # ========================================================================

        # Create event bus if not provided
        if not event_bus:
            from adapters.infrastructure.event_bus import InMemoryEventBus

            event_bus = InMemoryEventBus()
            logger.info("✅ InMemoryEventBus created (event-driven architecture enabled)")
        else:
            logger.info("✅ Using provided event bus")
        # ========================================================================
        # VALIDATE ALL REQUIRED DEPENDENCIES (FAIL-FAST)
        # ========================================================================

        from core.config.credential_store import get_credential

        # Validate Neo4j database connection
        try:
            driver = neo4j_adapter.get_driver()
        except (AttributeError, RuntimeError) as e:
            logger.error(f"❌ Neo4j driver unavailable: {e}")
            raise ValueError(
                "Neo4j database connection is REQUIRED. "
                "Ensure NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD are configured."
            ) from e

        if not driver:
            logger.error("❌ Neo4j driver is None")
            raise ValueError(
                "Cannot initialize services without Neo4j driver. "
                "Check your Neo4j connection configuration."
            )

        logger.info("✅ Neo4j driver validated")

        # Wrap the shared driver so every query gets a server-side per-tx timeout.
        # The wrapper proxies session() / execute_query() / begin_transaction() and
        # injects neo4j.Query(timeout=) / begin_transaction(timeout=) — see
        # adapters/persistence/neo4j/timed_driver.py for the rationale (no global
        # "default tx timeout" knob exists on AsyncDriver). 0 = unbounded.
        from adapters.persistence.neo4j.timed_driver import TimedDriver

        raw_driver = driver
        default_timeout = config.database.transaction_timeout or None  # 0 -> unbounded
        driver = TimedDriver(raw_driver, default_timeout=default_timeout)

        # Create QueryExecutor adapter — THE single path for raw Cypher in core services
        from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

        query_executor = Neo4jQueryExecutor(driver)
        logger.info("✅ QueryExecutor created (hexagonal architecture port)")

        # ========================================================================
        # SYNC AUTH INDEXES AND CLEANUP (Startup Tasks)
        # ========================================================================
        from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager

        # Use the RAW (unwrapped) driver for startup DDL. Vector index creation on
        # the :Entity label (and large full-text/domain indexes) can exceed the
        # default 120s tx timeout on a large graph; aborting at bootstrap would be
        # wrong. The wrapped `driver` is used everywhere else.
        schema_manager = Neo4jSchemaManager(raw_driver)

        # Schema sync fail-fast policy:
        # The sync_* methods return Result.ok(dict) even when individual indexes
        # fail — per-index failures live in the returned `failed:[]` list.
        # Bootstrap escalates a non-empty `failed:[]` (or Result.is_error) to a
        # RuntimeError for everything that affects correctness or fundamental
        # functionality. drop_stale_indexes is cosmetic (leftover indexes cost
        # disk, not correctness) and stays warn-only.
        def _check_schema_sync(result: Any, label: str, *, key: str = "created") -> dict[str, Any]:
            if result.is_error:
                raise RuntimeError(
                    f"Schema sync failed ({label}): {result.error}. "
                    "Bootstrap cannot proceed without required Neo4j indexes."
                )
            payload = result.value
            failed = payload.get("failed", [])
            if failed:
                raise RuntimeError(
                    f"Schema sync had per-index failures ({label}): {failed}. "
                    "Check Neo4j logs — common causes: missing privileges, "
                    "constraint creation against existing duplicate rows, "
                    "or missing plugins. Bootstrap cannot proceed."
                )
            created = payload.get(key, [])
            return {"created": created}

        # Create auth-specific indexes (rate limiting, session lookup, email uniqueness).
        # User(email) UNIQUE failure means two accounts could share an email
        # (data-integrity bug); Session(session_token) failure means every
        # authenticated request scans the Session label.
        auth_index_result = await schema_manager.sync_auth_indexes()
        auth_summary = _check_schema_sync(auth_index_result, "auth indexes")
        created = auth_summary["created"]
        logger.info(f"✅ Auth indexes synced: {', '.join(created) if created else 'all exist'}")

        # Create vector indexes for semantic search (FULL tier only — ADR-043).
        # CORE tier has no embeddings, so vector indexes are unnecessary. At FULL
        # tier a missing vector index means db.index.vector.queryNodes() returns
        # zero results — Askesis RAG silently degrades to graph-only (Gap #6).
        if tier.ai_enabled:
            vector_labels = [
                "Entity",  # Base label — covers all entity types via multi-label
                "ContentChunk",  # RAG chunks
                "ReferenceChunk",  # Canon reference-book chunks (own index, SearchRouter-invisible)
                "Ku",  # Ku→Ku similarity — "Related concepts" on /explore/ku/{uid}
                "PathStep",  # PS→PS similarity — "Related concepts" on /explore/ps/{uid}
            ]
            vector_result = await schema_manager.sync_vector_indexes(
                entity_labels=vector_labels,
                dimension=EmbeddingGeometry.DIMENSION,
                similarity="cosine",
            )
            vector_summary = _check_schema_sync(vector_result, "vector indexes")
            created = vector_summary["created"]
            logger.info(
                f"✅ Vector indexes synced: {', '.join(created) if created else 'all exist'}"
            )
        else:
            logger.info("⏭️  Vector indexes skipped (intelligence tier: CORE)")

        # Drop stale indexes from removed labels. Cosmetic — failures leave a
        # leftover index but no correctness impact. Warn-only by design.
        stale_result = await schema_manager.drop_stale_indexes()
        if stale_result.is_ok:
            dropped = stale_result.value.get("dropped", [])
            failed = stale_result.value.get("failed", [])
            if dropped:
                logger.info(f"✅ Dropped stale indexes: {', '.join(dropped)}")
            if failed:
                logger.warning(f"⚠️ Could not drop {len(failed)} stale indexes: {failed}")
        else:
            logger.warning(f"⚠️ Stale-index drop had issues: {stale_result.error}")

        # Sync domain indexes (UID, user_uid, status, date, composite).
        # Missing UID indexes turn every entity lookup into a full label scan.
        domain_idx_result = await schema_manager.sync_domain_indexes()
        domain_summary = _check_schema_sync(domain_idx_result, "domain indexes")
        logger.info(f"✅ Domain indexes synced: {len(domain_summary['created'])} created/verified")

        # Sync full-text indexes (Cypher-first search foundation — always created).
        # Missing fulltext indexes break SearchRouter for that domain.
        fulltext_result = await schema_manager.sync_fulltext_indexes()
        fulltext_summary = _check_schema_sync(fulltext_result, "fulltext indexes")
        logger.info(
            f"✅ Fulltext indexes synced: {len(fulltext_summary['created'])} created/verified"
        )

        # Conversation persistence indexes (ADR-078 — discussion sessions).
        # Missing session_id/turn_id uniqueness would let a MERGE double-create;
        # missing user_uid index turns the revisit-list query into a label scan.
        conversation_idx_result = await schema_manager.sync_conversation_indexes()
        conversation_summary = _check_schema_sync(conversation_idx_result, "conversation indexes")
        logger.info(
            f"✅ Conversation indexes synced: {len(conversation_summary['created'])} created/verified"
        )

        # ========================================================================
        # SCHEMA-CHANGE MONITORING (opt-in — NEO4J_SCHEMA_MONITORING)
        # ========================================================================
        # Baseline the schema-change detector against the schema we just synced,
        # then start its background poll. On drift it invalidates the adapter's
        # query-optimization caches (see core/services/schema_change_detector.py).
        # OFF by default: CORE tier spins up no background workers
        # (docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md). Non-fatal —
        # monitoring is an optimization, never a correctness requirement.
        if config.database.schema_monitoring_enabled:
            interval = config.database.schema_monitoring_interval
            monitor_result = await neo4j_adapter.initialize_schema_monitoring(
                interval_seconds=interval
            )
            if monitor_result.is_error:
                logger.warning(
                    f"⚠️ Schema-change monitoring failed to start: {monitor_result.error}"
                )
            else:
                logger.info(f"✅ Schema-change monitoring started (poll interval: {interval}s)")
        else:
            logger.info("⏭️  Schema-change monitoring disabled (NEO4J_SCHEMA_MONITORING off)")

        # THE app-wide SessionBackend: startup cleanup here, session revocation
        # on privilege change (UserService below), and GraphAuthService
        from adapters.persistence.neo4j.session_backend import SessionBackend

        session_backend = SessionBackend(driver)

        # Cleanup expired sessions and reset tokens (daily maintenance at startup)
        cleanup_sessions = await session_backend.cleanup_expired_sessions()
        cleanup_tokens = await session_backend.cleanup_expired_tokens()

        if cleanup_sessions.is_ok and cleanup_tokens.is_ok:
            sessions_cleaned = cleanup_sessions.value
            tokens_cleaned = cleanup_tokens.value
            if sessions_cleaned > 0 or tokens_cleaned > 0:
                logger.info(
                    f"✅ Cleanup: {sessions_cleaned} expired sessions, {tokens_cleaned} expired tokens"
                )
            else:
                logger.debug("✅ Cleanup: no expired sessions or tokens")
        else:
            logger.warning("⚠️ Cleanup had issues - continuing startup")

        # Validate optional API keys (WARN only — all AI keys are FULL-tier gated below)
        # OPENAI_API_KEY: checked here for early visibility; enforced in the LLM block below.
        # DEEPGRAM_API_KEY: FULL tier only (Digital layer) — checked in the Deepgram block below.
        openai_key_value = get_credential("OPENAI_API_KEY", fallback_to_env=True)
        if not openai_key_value or openai_key_value in ["your-openai-api-key-here", "", "sk-"]:
            logger.warning(
                "⚠️ OPENAI_API_KEY not configured: enables LLM chat, content processing, and AI features"
            )
            logger.warning(
                "   App will run with basic features only (set INTELLIGENCE_TIER=full to enable)"
            )
        else:
            logger.info("✅ OPENAI_API_KEY validated")

        # ========================================================================
        # CREATE DOMAIN BACKENDS (100% Dynamic Pattern)
        # ========================================================================
        backends = create_all_backends(
            driver, query_executor, prometheus_metrics=prometheus_metrics
        )

        # Unpack backends for readability
        connection_fetch_backend = backends["connection_fetch_backend"]
        tasks_backend = backends["tasks_backend"]
        events_backend = backends["events_backend"]
        habits_backend = backends["habits_backend"]
        habit_completions_backend = backends["habit_completions_backend"]
        goals_backend = backends["goals_backend"]
        invoice_backend = backends["invoice_backend"]
        transcription_backend = backends["transcription_backend"]
        users_backend = backends["users_backend"]
        ps_backend = backends["ps_backend"]
        ku_backend = backends["ku_backend"]
        principles_backend = backends["principles_backend"]
        # reflection_backend shelved (2026-03-28)
        choices_backend = backends["choices_backend"]
        progress_backend = backends["progress_backend"]
        user_entry_backend = backends["user_entry_backend"]
        activity_report_backend = backends["activity_report_backend"]
        askesis_backend = backends["askesis_backend"]
        # Activity template backends (Phase 4 — PsEngagementService)
        task_template_backend = backends["task_template_backend"]
        goal_template_backend = backends["goal_template_backend"]
        habit_template_backend = backends["habit_template_backend"]
        event_template_backend = backends["event_template_backend"]
        choice_template_backend = backends["choice_template_backend"]
        principle_template_backend = backends["principle_template_backend"]

        # Create user service FIRST (foundation service with no dependencies).
        # The UserContextQueryExecutor (MEGA/CONSOLIDATED Cypher, below the boundary)
        # is built here and injected, so neither UserService nor UserContextBuilder
        # imports the adapter (ADR-044/SKUEL022). Shared by the builder created below.
        from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
        from core.services.user_service import create_user_service

        user_context_query_executor = UserContextQueryExecutor(query_executor)

        # Vault-agent device enrollment (ADR-075) — auth infrastructure, so it
        # rides behind the UserService facade like sessions do.
        from adapters.persistence.neo4j.device_backend import DeviceBackend
        from core.services.user.device_service import DeviceService

        device_service = DeviceService(DeviceBackend(driver))

        user_service = create_user_service(
            users_backend,
            user_context_query_executor,
            event_bus=event_bus,
            metrics_cache=metrics_cache,
            device_service=device_service,
            session_invalidator=session_backend,
        )
        logger.info("✅ UserService created (foundation service)")

        # Ensure system user exists for infrastructure operations.
        # Fail-fast: system-owned content (e.g. ingestion defaults, see
        # core/services/ingestion/config.py) creates OWNS edges against
        # (:User {uid: "user_system"}). If that node doesn't exist the MATCH
        # yields zero rows, MERGE silently no-ops, and the entity becomes an
        # orphan with no warning. Bootstrap should die here rather than ship
        # an app with broken system-owned content.
        logger.info("Ensuring system user exists...")
        system_user_result = await user_service.ensure_system_user()
        if system_user_result.is_error:
            raise RuntimeError(
                f"Bootstrap requires the system user (uid='user_system') for "
                f"infrastructure-owned content. ensure_system_user() failed: "
                f"{system_user_result.error}"
            )
        logger.info("✅ System user ready")

        # Create user relationship backend (pinning, following, etc.)
        from adapters.persistence.neo4j.user_relationship_backend import (
            UserRelationshipBackend,
        )

        user_relationships = UserRelationshipBackend(executor=query_executor)
        logger.info("✅ UserRelationshipBackend created (pinning, following)")

        # Create graph-native authentication service (January 2026)
        # Sessions stored in Neo4j with bcrypt password hashing; reuses the
        # app-wide SessionBackend created above the startup cleanup
        from core.auth.graph_auth import GraphAuthService

        # Email service for password reset (March 2026, tier-gated May 2026)
        # Gated by EMAIL_ENABLED to match the embeddings pattern: opt-in via flag,
        # fail-fast on missing credential when opted in. Default off keeps local-dev
        # quiet. graph_auth handles email_service=None — password reset returns
        # Result.ok(True) without sending (prevents email-enumeration leak).
        email_service = None
        email_enabled = os.environ.get("EMAIL_ENABLED", "").lower() in ("true", "1", "yes")
        if email_enabled:
            from core.config.credential_store import get_credential

            resend_api_key = get_credential("RESEND_API_KEY", fallback_to_env=True)
            if not resend_api_key:
                raise RuntimeError(
                    "EMAIL_ENABLED=true but RESEND_API_KEY is not set in keychain or env. "
                    "Add it via the credential setup flow, or set EMAIL_ENABLED=false "
                    "to disable password reset emails."
                )
            from adapters.outbound.email_service import ResendEmailService

            resend_from = os.environ.get("RESEND_FROM_EMAIL", "noreply@skuel.app")
            email_service = ResendEmailService(api_key=resend_api_key, from_email=resend_from)
            logger.info("✅ ResendEmailService created (password reset emails)")
        else:
            logger.info("⏭️  Email service skipped (EMAIL_ENABLED not set)")

        app_url = os.environ.get("APP_URL", "http://localhost:8000")

        graph_auth = GraphAuthService(
            user_backend=users_backend,
            session_backend=session_backend,
            email_service=email_service,
            app_url=app_url,
        )
        logger.info("✅ GraphAuthService created (graph-native authentication)")

        # Create user context service (context-aware intelligence)
        # NOTE: UserContextBuilder now owns user resolution (Option A architecture, Nov 2025)
        # This eliminates repetitive user lookup in every service method.
        #
        # ONE builder (July 2026): UserService constructs THE app-wide
        # UserContextBuilder in its __init__ (it needs user_service=self for user
        # resolution — a true circular dependency, so the builder can't be built
        # first and injected). Compose REUSES that instance everywhere. A second
        # compose-level builder here previously shadowed it: _intelligence_hub
        # post-wired zpd_service/ps_engagement onto the compose copy only, so
        # UserService.get_rich_unified_context (the production daily-plan path)
        # never ran the ZPD capstone — zpd_assessment was always None.
        from core.services.user import UserContextService

        context_builder = user_service.context_builder
        if context_builder is None:
            raise RuntimeError(
                "UserService.context_builder is None — bootstrap must construct "
                "UserService with the UserContextQueryExecutor so the single "
                "app-wide UserContextBuilder exists (see create_user_service above)."
            )
        context_service = UserContextService(
            context_builder=context_builder,
            user_service=user_service,
            tasks_service=None,  # Will be wired after tasks service is created
        )
        logger.info("✅ UserContextService created (context-aware intelligence)")
        logger.info("   - Single UserContextBuilder (owned by UserService) shared app-wide")

        # Create cross-domain backend (shared by graph intelligence, cross-domain query,
        # and cross-domain analytics services)
        from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend

        cross_domain_backend = CrossDomainBackend(query_executor)
        logger.info("✅ CrossDomainBackend created")

        # Knowledge-subgraph structural-health gauge (ADR-080 Horizon-1). Executor-
        # based corpus reader, tier-independent (pure graph analytics, CORE-safe).
        from adapters.persistence.neo4j.backends.curriculum_backends import (
            EmbeddingCoverageBackend,
            KnowledgeHealthBackend,
        )

        knowledge_health_backend = KnowledgeHealthBackend(query_executor)
        logger.info("✅ KnowledgeHealthBackend created")

        # Embedding-coverage (retrievability) probe — a count query, so it is
        # tier-independent too: it measures the gaps CORE-tier periods leave.
        embedding_coverage_backend = EmbeddingCoverageBackend(query_executor)
        logger.info("✅ EmbeddingCoverageBackend created")

        # Wire cross-domain backend to UserService (post-construction — UserService created first)
        user_service.wire_cross_domain_backend(cross_domain_backend)
        logger.info("✅ UserService wired with CrossDomainBackend (stats aggregation)")

        # Create graph intelligence (needed by tasks service)
        from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService

        graph_intelligence = GraphIntelligenceService(cross_domain_backend)
        logger.info("✅ GraphIntelligenceService created")

        # Create inference services (passed through to TasksService)
        from core.services.entity_inference_service import EntityInferenceService
        from core.services.insight.insight_generation_service import InsightGenerationService

        ku_inference_service = EntityInferenceService()
        ku_generation_service = InsightGenerationService()
        logger.info("✅ Inference services created (ku_inference, ku_generation)")

        # Create InsightStore
        from adapters.persistence.neo4j.insight_backend import InsightBackend
        from core.services.insight import InsightStore

        insight_backend = InsightBackend(query_executor)
        insight_store = InsightStore(insight_backend)
        logger.info("✅ InsightStore created (event-driven insights)")

        # Search event recorder (discovery analytics) — persists search.executed
        # events as :SearchEvent nodes. Tier-independent: a plain graph write.
        from adapters.persistence.neo4j.search_event_backend import SearchEventBackend
        from core.services.search_event_recorder import SearchEventRecorder

        search_event_backend = SearchEventBackend(query_executor)
        search_event_recorder = SearchEventRecorder(backend=search_event_backend)
        logger.info("✅ SearchEventRecorder created (search behavioral log)")

        # ========================================================================
        # ACTIVITY KNOWLEDGE INTELLIGENCE (shared singleton for all 6 domains)
        # ========================================================================
        # Created here (not in _create_learning_services) to break circular
        # dependency: activity_services needs this, learning_services needs activity_services.
        from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
        from core.models.entity import Entity
        from core.services.knowledge import ActivityKnowledgeIntelligenceService

        activity_entity_backend = UniversalNeo4jBackend[Entity](
            driver, NeoLabel.ENTITY, Entity, base_label=NeoLabel.ENTITY
        )
        activity_knowledge_intelligence = ActivityKnowledgeIntelligenceService(
            backend=activity_entity_backend,
            graph_intel=graph_intelligence,
        )
        logger.info("✅ ActivityKnowledgeIntelligenceService created")

        # ========================================================================
        # ACTIVITY DOMAIN SERVICES (6) - Unified creation
        # ========================================================================
        # Cross-domain query service — graph-direct cross-domain reads
        # (replaces the "fetch all of A, fetch all of B, loop in Python" pattern)
        from core.services.cross_domain import CrossDomainQueryService

        cross_domain_query = CrossDomainQueryService(cross_domain_backend)
        logger.info("✅ CrossDomainQueryService created")

        activity_services = _create_activity_services(
            tasks_backend=tasks_backend,
            events_backend=events_backend,
            habits_backend=habits_backend,
            habit_completions_backend=habit_completions_backend,
            goals_backend=goals_backend,
            choices_backend=choices_backend,
            principles_backend=principles_backend,
            # reflection_backend removed — PrinciplesReflectionService shelved (2026-03-28)
            graph_intelligence=graph_intelligence,
            cross_domain_query=cross_domain_query,
            event_bus=event_bus,
            ku_inference_service=ku_inference_service,
            ku_generation_service=ku_generation_service,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        )
        logger.info("✅ Activity Domain services created (6 facades with embedded intelligence)")

        # Deepgram API key — FULL tier only (transcription is the Digital layer: ADR-043),
        # with a per-capability opt-out (TRANSCRIPTION_ENABLED, default true).
        # Ceiling FIRST, flag second — CORE never reads a paid credential. Do not reorder.
        deepgram_api_key: str | None = None
        transcription_enabled = tier.ai_enabled and _bool_flag(
            "TRANSCRIPTION_ENABLED", default=True
        )
        if not transcription_enabled:
            reason = (
                "intelligence tier: CORE — audio transcription is FULL tier"
                if not tier.ai_enabled
                else "TRANSCRIPTION_ENABLED=false"
            )
            logger.info(f"⏭️  Transcription skipped ({reason})")
        else:
            from core.config.credential_store import get_credential

            deepgram_api_key = get_credential("DEEPGRAM_API_KEY", fallback_to_env=True)
            if not deepgram_api_key:
                raise RuntimeError(
                    "FULL-tier bootstrap requires DEEPGRAM_API_KEY for audio transcription. "
                    "Set TRANSCRIPTION_ENABLED=false to run FULL without transcription, "
                    "set INTELLIGENCE_TIER=core to run without any AI services, or "
                    "set DEEPGRAM_API_KEY in the credential store / environment."
                )
            logger.info("✅ DEEPGRAM_API_KEY validated")

        # Create core services (Finance only in CORE; Finance + Transcription in FULL)
        core_services = _create_core_services(
            invoice_backend=invoice_backend,
            transcription_backend=transcription_backend,
            user_service=user_service,
            deepgram_api_key=deepgram_api_key,
            event_bus=event_bus,
        )
        logger.info("✅ Core services created (Finance + event bus wiring)")

        tasks_service = activity_services["tasks"]

        # Wire tasks_service into context_service for context-aware operations
        context_service.tasks_service = tasks_service
        logger.info("✅ UserContextService wired with TasksService")

        # Late-wire tasks_service into the knowledge generator. True circular
        # dependency: the generator is constructed before TasksService (which holds a
        # reference to it), so it cannot receive tasks_service at construction. Without
        # this back-reference the APPLIES_KNOWLEDGE pattern detector and completed-task
        # knowledge extraction have no relationship/task access and degrade to no-ops.
        # See: /docs/patterns/KNOWLEDGE_APPLICATION_TRACKING.md
        ku_generation_service.tasks_service = tasks_service
        logger.info("✅ InsightGenerationService wired with TasksService")

        # Note: TranscriptionService is already created in core_services with Deepgram wiring
        # Note: MarkdownSyncService DELETED (January 2026) - use UnifiedIngestionService

        # Create knowledge components using 100% dynamic backend pattern
        # IMPORTANT: chunking_service AND content_adapter must be created BEFORE
        # UnifiedIngestionService so chunks persist to Neo4j at ingest time.
        from adapters.persistence.neo4j.neo4j_connection import get_connection
        from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
        from adapters.persistence.neo4j.neo4j_reference_chunk_adapter import (
            Neo4jReferenceChunkAdapter,
        )
        from core.services.entity_chunking_service import EntityChunkingService

        chunking_service = EntityChunkingService()
        logger.info("✅ EntityChunkingService created for automatic chunk generation")

        # Content adapter — used by ingestion (store_content_with_chunks), batch
        # re-chunking, and the embedding worker (store_chunk_embeddings).
        connection = get_connection()
        content_adapter = Neo4jContentAdapter(connection)

        # Reference-chunk adapter — the canon ingest door's parallel to
        # content_adapter. Wired into the worker so an in-process
        # ReferenceChunkEmbeddingRequested embeds onto :ReferenceChunk. NOT
        # wired into vector_search / SearchRouter — that omission IS the
        # isolation guarantee (canon invisible to /search).
        reference_chunk_adapter = Neo4jReferenceChunkAdapter(connection)

        # Create UnifiedIngestionService (ADR-014: Merged MD + YAML ingestion)
        # Wires the chunk pipeline end-to-end: chunk generation → Neo4j persistence →
        # ChunkEmbeddingRequested event → background worker.
        # event_bus is wired only in FULL tier (same gate + rationale as
        # BatchChunkingService below): ingestion uses it exclusively for the
        # post-persist embedding step (*EmbeddingRequested per persisted entity +
        # ChunkEmbeddingRequested for chunks — ADR-074), and in CORE the embedding
        # worker isn't running, so publishing would be a queue-with-no-listener.
        from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
        from adapters.persistence.neo4j.ingestion_service_factory import (
            make_unified_ingestion_service,
        )

        ingestion_backend = IngestionBackend(executor=query_executor)

        unified_ingestion = make_unified_ingestion_service(
            driver=driver,
            ingestion_backend=ingestion_backend,
            chunking_service=chunking_service,  # Automatic chunk generation for KU entities
            content_adapter=content_adapter,  # Persist :ContentChunk nodes for RAG retrieval
            event_bus=event_bus if tier.ai_enabled else None,
            user_service=user_service,  # Role lookup for audience:public gate (Finding 2)
        )

        # Batch chunk regeneration (Phase 2, May 2026) — admin tool used when
        # CHUNKING_ALGORITHM_VERSION changes or chunks drift from their source.
        # event_bus is wired only in FULL tier; in CORE the embedding worker
        # isn't running, so publishing ChunkEmbeddingRequested would be a
        # queue-with-no-listener. CORE-tier regen produces fresh chunks; admins
        # sweep embeddings separately via migrate_chunk_embeddings.py.
        from adapters.persistence.neo4j.batch_chunking_backend import BatchChunkingBackend
        from core.services.chunks.batch_chunking_service import BatchChunkingService

        batch_chunking_service = BatchChunkingService(
            backend=BatchChunkingBackend(driver),
            chunking_service=chunking_service,
            content_adapter=content_adapter,
            event_bus=event_bus if tier.ai_enabled else None,
        )
        if tier.ai_enabled:
            logger.info("✅ BatchChunkingService created (regen + re-embed via event bus)")
        else:
            logger.info(
                "✅ BatchChunkingService created (CORE tier: regen-only, no event publication)"
            )

        logger.info(
            "✅ Content services created (includes UnifiedIngestionService with automatic chunking)"
        )

        # Create the chat clients BEFORE learning services, from the single
        # chat-provider chokepoint (mirror of create_embedding_client, ADR-068):
        # one credential read, one place providers are decided.
        # Gated by intelligence tier (ADR-043): CORE skips entirely; FULL requires it.
        chat_clients = None
        llm_service = None
        if not tier.ai_enabled:
            logger.info("⏭️  Chat clients + LLM service skipped (intelligence tier: CORE)")
        else:
            from adapters.external.llm import create_chat_client
            from core.services.llm_service import LLMConfig, LLMProvider, LLMService

            try:
                # Askesis's RAG LLMService routes through the multi-provider caller
                # (chat_clients.caller): modern gpt-4o default, overridable per call —
                # Claude becomes reachable the moment ANTHROPIC_API_KEY is wired, no
                # code change. LLMService holds no SDK or credential (W1).
                chat_clients = create_chat_client()
                llm_config = LLMConfig(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4o",  # modern default for RAG / intelligence; per-call overridable
                )
                llm_service = LLMService(config=llm_config, caller=chat_clients.caller)
                logger.info(
                    "✅ Chat clients created (OpenAI required, Anthropic optional); "
                    "LLM service created (gpt-4o default for RAG generation, per-call overridable)"
                )
            except Exception as e:  # safety-net: surface FULL-tier LLM init failure loudly
                logger.error(f"FULL-tier chat clients / LLM service failed to initialize: {e}")
                raise RuntimeError(
                    "FULL-tier bootstrap requires the chat clients / LLM service. "
                    "Set INTELLIGENCE_TIER=core to run without LLM features, or fix the "
                    f"underlying init error: {e}"
                ) from e

        # Create learning services (graph_intelligence already created above)
        learning_services = _create_learning_services(
            driver=driver,
            progress_backend=progress_backend,
            knowledge_backend=ps_backend,
            atomic_ku_backend=ku_backend,
            chunking_service=chunking_service,
            user_service=user_service,
            graph_intelligence=graph_intelligence,
            llm_service=llm_service,  # Pass LLM service for askesis RAG
            tier=tier,  # single IntelligenceTier.from_env() read lives above
            event_bus=event_bus,  # Event-driven architecture
            prometheus_metrics=prometheus_metrics,  # Metrics instrumentation
            query_executor=query_executor,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        )
        logger.info("✅ Learning services created")

        # Build template + engagement layer (Phase 4 — PS+Activity Templates).
        # PS service must already exist (it's inside learning_services).
        from services_bootstrap._template_services import _create_template_services

        template_services = _create_template_services(
            executor=query_executor,
            ps_service=learning_services["ps"],
            task_template_backend=task_template_backend,
            goal_template_backend=goal_template_backend,
            habit_template_backend=habit_template_backend,
            event_template_backend=event_template_backend,
            choice_template_backend=choice_template_backend,
            principle_template_backend=principle_template_backend,
            tasks_backend=tasks_backend,
            goals_backend=goals_backend,
            habits_backend=habits_backend,
            events_backend=events_backend,
            choices_backend=choices_backend,
            principles_backend=principles_backend,
        )

        # Extract embeddings and vector search services for use by intelligence services and SearchRouter
        embeddings_service = learning_services["embeddings_service"]
        vector_search_service = learning_services["vector_search_service"]

        # ========================================================================
        # CREATE BACKGROUND WORKERS (January 2026)
        # ========================================================================

        # Create embedding background worker (async embedding generation for all activity domains)
        # Worker processes EmbeddingRequested events in batches for zero-latency user experience.
        # Tier-gated via embeddings_service: CORE tier legitimately runs without the worker.
        embedding_worker = None
        if embeddings_service:
            from core.services.background.embedding_worker import EmbeddingBackgroundWorker

            embedding_worker = EmbeddingBackgroundWorker(
                event_bus=event_bus,
                embeddings_service=embeddings_service,
                content_adapter=content_adapter,  # Unlocks _process_chunk_batch
                reference_chunk_adapter=reference_chunk_adapter,  # Canon chunks (own index)
                prometheus_metrics=prometheus_metrics,  # Real-time metrics exposure
                batch_size=25,  # Process 25 entities per batch (cost-optimized)
                batch_interval_seconds=30,  # Run every 30 seconds
            )
            logger.info("✅ Embedding background worker created (batch_size=25, interval=30s)")
            logger.info(
                f"   Worker handles: {len(EMBEDDING_EVENT_TYPES)} embeddable entity types"
                " + content chunks"
            )
        else:
            logger.info("⏭️  Embedding background worker skipped (embeddings_service not available)")

        # ========================================================================
        # CREATE LATERAL RELATIONSHIP SERVICES (January 2026)
        # ========================================================================
        # Core lateral relationships infrastructure - foundational graph architecture
        # Enables explicit modeling of sibling, cousin, dependency, and semantic relationships
        # across all 8 hierarchical domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP)

        from adapters.persistence.neo4j.backends.collab_backends import LateralRelationshipBackend
        from core.services.lateral_relationships import LateralRelationshipService

        # Create backend + service for lateral relationships (domain-agnostic)
        # Ownership verification happens at route level via domain_service param
        lateral_backend = LateralRelationshipBackend(executor=query_executor)
        lateral_service = LateralRelationshipService(backend=lateral_backend)
        logger.info("✅ LateralRelationshipService created (9 domains, ownership at route level)")

        # Create Askesis core service (CRUD operations for AI assistant instances)
        from core.services.askesis.askesis_core_service import AskesisCoreService

        askesis_core_service = AskesisCoreService(backend=askesis_backend)
        logger.info("✅ Askesis core service created (CRUD operations)")

        # NOTE: Askesis service now created in after intelligence_factory is available
        # This eliminates post-construction wiring (January 2026 architecture evolution)

        # Wire AI services into domain facades (ADR-030: Two-Tier Intelligence)
        askesis_ai, context_aware_ai = _wire_ai_services(
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            _activity_services=activity_services,
            learning_services=learning_services,
            user_service=user_service,
            graph_intelligence=graph_intelligence,
        )

        # Create calendar service
        from core.services.calendar_service import CalendarService

        calendar_service = CalendarService(
            tasks_service=activity_services["tasks"],
            events_service=activity_services["events"],
            habits_service=activity_services["habits"],
            goals_service=activity_services["goals"],
        )
        logger.info("✅ Calendar service created")

        # Create system service (health checks and monitoring)
        from core.services.system_service import SystemService

        system_service = SystemService()
        logger.info("✅ System service created (health checks enabled)")

        # AdminStatsService: cross-domain stats for admin dashboard
        from core.services.admin_stats_service import AdminStatsService

        # Create visualization services:
        # - VisualizationService: pure formatter (no domain deps)
        # - VisualizationAggregationService: fetches data + delegates formatting
        from core.services.analytics.visualization_aggregation_service import (
            VisualizationAggregationService,
        )
        from core.services.visualization_service import VisualizationService

        _vis_formatter = VisualizationService()
        visualization_service = VisualizationAggregationService(
            tasks_service=activity_services["tasks"],
            habits_service=activity_services["habits"],
            goals_service=activity_services["goals"],
            visualization_service=_vis_formatter,
        )
        logger.info("✅ Visualization service created (Chart.js/Gantt adapters)")

        # Content enrichment shares the OpenAI adapter from the chat chokepoint
        # (one adapter serves ContentEnrichment, the caller and reports).
        # None on CORE — ContentEnrichmentService handles that gracefully.
        from core.services.content_enrichment_service import ContentEnrichmentService

        openai_chat = chat_clients.openai if chat_clients else None

        content_enrichment = ContentEnrichmentService(
            backend=user_entry_backend,
            transcription_service=core_services["transcription"],
            chat_port=openai_chat,  # None in CORE tier — already handles None gracefully
            event_bus=event_bus,  # Event-driven architecture
        )
        logger.info("✅ Content enrichment service created")

        # Create report and exercise services
        from adapters.persistence.neo4j.backends.exercise_backends import (
            EntryReportBackend,
            ExerciseBackend,
        )
        from core.models.exercises.exercise import Exercise
        from core.models.report.entry_report import EntryReport
        from core.services.exercises import ExerciseService
        from core.services.report.report_mastery_service import ReportMasteryService

        report_mastery_service = ReportMasteryService(
            user_entry_backend=user_entry_backend,
            ku_interaction_service=learning_services["ps"].mastery,
        )
        logger.info("✅ ReportMasteryService created")

        # UnifiedLLMCaller: the multi-provider chat path (gpt* → OpenAI,
        # claude* → Anthropic), assembled at the chat chokepoint. None on CORE.
        from core.services.report import EntryReportService

        llm_caller = chat_clients.caller if chat_clients else None

        entry_report_backend = EntryReportBackend(
            driver=driver,
            label=NeoLabel.ENTRY_REPORT,
            entity_class=EntryReport,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )

        # EntryReportService: always created so typed reads (get,
        # list_for_submission) work in both CORE and FULL tiers. AI report
        # *generation* still requires llm_caller — returns a system error
        # when llm_caller is None (CORE tier).
        entry_report_service = EntryReportService(
            llm_caller=llm_caller,
            backend=entry_report_backend,  # mastery-loop reads + canonical report-node creation
            ku_interaction_service=learning_services["ps"].mastery,  # closes mastery loop
            report_mastery_service=report_mastery_service,
            event_bus=event_bus,  # EntryReportGenerated → ADR-051 result transition
        )

        exercise_backend = ExerciseBackend(
            driver=driver,
            label=NeoLabel.EXERCISE,
            entity_class=Exercise,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )

        exercise_service = ExerciseService(backend=exercise_backend, event_bus=event_bus)

        # ResourceService: curated content (books, talks, films, podcasts)
        from adapters.persistence.neo4j.backends.misc_backends import ResourceBackend
        from core.models.resource.resource import Resource as ResourceModel
        from core.services.resource_service import ResourceService

        resource_backend = ResourceBackend(
            driver=driver,
            label=NeoLabel.RESOURCE,
            entity_class=ResourceModel,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
        resource_service = ResourceService(backend=resource_backend)

        logger.info("✅ Report, exercise, and resource services created")

        # Create revised exercise service (four-phase learning loop)
        from adapters.persistence.neo4j.backends.exercise_backends import RevisedExerciseBackend
        from core.models.exercises.revised_exercise import RevisedExercise
        from core.services.revised_exercises import RevisedExerciseService

        revised_exercise_backend = RevisedExerciseBackend(
            driver=driver,
            label=NeoLabel.REVISED_EXERCISE,
            entity_class=RevisedExercise,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
        revised_exercise_service = RevisedExerciseService(
            backend=revised_exercise_backend, event_bus=event_bus
        )
        logger.info("✅ RevisedExerciseService created (four-phase learning loop)")

        # Create form services (general-purpose form system)
        from adapters.persistence.neo4j.backends.forms_backends import (
            FormSubmissionBackend,
            FormTemplateBackend,
        )
        from core.models.forms.form_submission import FormSubmission
        from core.models.forms.form_template import FormTemplate
        from core.services.forms import FormSubmissionService, FormTemplateService

        form_template_backend = FormTemplateBackend(
            driver=driver,
            label=NeoLabel.FORM_TEMPLATE,
            entity_class=FormTemplate,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
        # Create group service (ADR-040: Teacher Exercise Workflow)
        from adapters.persistence.neo4j.backends.collab_backends import GroupBackend
        from core.models.group.group import Group
        from core.services.groups import GroupService

        group_backend = GroupBackend(
            driver=driver,
            label=NeoLabel.GROUP,
            entity_class=Group,
            prometheus_metrics=prometheus_metrics,
        )

        group_service = GroupService(backend=group_backend, event_bus=event_bus)
        logger.info("✅ GroupService created (ADR-040)")

        form_template_service = FormTemplateService(
            backend=form_template_backend, event_bus=event_bus
        )

        form_submission_backend = FormSubmissionBackend(
            driver=driver,
            label=NeoLabel.FORM_SUBMISSION,
            entity_class=FormSubmission,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
        form_submission_service = FormSubmissionService(
            backend=form_submission_backend,
            event_bus=event_bus,
            form_template_service=form_template_service,
        )
        logger.info("✅ Form services created (FormTemplate + FormSubmission)")

        # Create interaction service (User Interaction Contract — EntityType.INTERACTION)
        from adapters.persistence.neo4j.backends.misc_backends import InteractionBackend
        from core.models.interaction.interaction import Interaction
        from core.services.interaction import InteractionService

        interaction_backend = InteractionBackend(
            driver=driver,
            label=NeoLabel.INTERACTION,
            entity_class=Interaction,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
        interaction_service = InteractionService(
            backend=interaction_backend,
            event_bus=event_bus,
        )
        logger.info("✅ InteractionService created (User Interaction Contract)")

        # Create teacher review service (ADR-040: Teacher Exercise Workflow)
        from core.services.report.teacher_review_service import TeacherReviewService

        teacher_review_service = TeacherReviewService(
            user_entry_backend=user_entry_backend,
            report_backend=entry_report_backend,
            exercise_backend=exercise_backend,
            group_backend=group_backend,
            ku_interaction_service=learning_services["ps"].mastery,
            report_mastery_service=report_mastery_service,
            event_bus=event_bus,
        )
        logger.info("✅ TeacherReviewService created (ADR-040)")

        # Create notification service
        from adapters.persistence.neo4j.backends.collab_backends import NotificationBackend
        from core.services.notifications.notification_service import NotificationService

        notification_backend = NotificationBackend(executor=query_executor)
        notification_service = NotificationService(executor=notification_backend)
        logger.info("✅ NotificationService created")

        # Create sharing backend + service (cross-domain, queries :Entity nodes)
        from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
        from core.models.entity import Entity
        from core.services.sharing import UnifiedSharingService

        sharing_backend = SharingBackend(
            driver, NeoLabel.ENTITY, Entity, prometheus_metrics=prometheus_metrics
        )
        unified_sharing_service = UnifiedSharingService(backend=sharing_backend)

        # Wire sharing into services that were created earlier without sharing.
        # Both ExerciseService (ASSIGNED scope -> SHARED_WITH_GROUP, ADR-053)
        # and FormSubmissionService need the sharing service post-hoc.
        form_submission_service.sharing_service = unified_sharing_service
        exercise_service.sharing_service = unified_sharing_service

        # LIFEPATH SERVICE (Domain #14: The Destination)
        # "Everything flows toward the life path"
        # Vision capture → Alignment measurement → Recommendations
        # =====================================================================
        from adapters.persistence.neo4j.lifepath_backend import LifePathBackend
        from core.services.lifepath import LifePathService

        lifepath_backend = LifePathBackend(query_executor)
        lifepath_service = LifePathService(
            backend=lifepath_backend,
            lp_service=learning_services["learning_paths"],
            ku_service=learning_services["ps"],
            user_service=user_service,
            llm_service=llm_service,
            # The alignment metric's substance half. Unwired, alignment refuses
            # rather than reporting mastery alone under a substance heading.
            cross_domain_backend=cross_domain_backend,
        )
        logger.info("✅ LifePath service created (Vision→Action bridge)")

        # Create instruction resolver (stateless — works without AI).
        # Consumed by UserEntryProcessingService for LLM-driven enrichment.
        from core.services.output import InstructionResolver

        instruction_resolver = InstructionResolver()
        logger.info("✅ InstructionResolver created")

        # Batch transcription service (Tier 1: audio → txt) — FULL tier only.
        # Tier 2 (BatchProcessingService) retired with ADR-054 Commit 6a — the
        # LLM-driven txt→md path now lives inside UserEntryProcessingService.
        batch_transcription = None
        if core_services["deepgram_adapter"]:
            from core.services.transcription import BatchTranscriptionService

            batch_transcription = BatchTranscriptionService(
                deepgram_adapter=core_services["deepgram_adapter"],
                max_concurrent=5,
            )
            logger.info("✅ BatchTranscriptionService created (Tier 1: audio → txt)")
        else:
            # Adapter absence = transcription disabled upstream (CORE tier or
            # TRANSCRIPTION_ENABLED=false) — the specific reason was logged there.
            logger.info(
                "⏭️  BatchTranscriptionService skipped (no Deepgram adapter — transcription disabled)"
            )

        # Learning loop query service — read-side peer of LearningLoopEventHandlerService.
        # Owns Cypher that traverses Interaction/Exercise/Report edges, keeping
        # UserEntry search free of learning-loop shape.
        from core.services.user_entry.learning_loop_query import LearningLoopQueryService

        learning_loop_query_service = LearningLoopQueryService(
            user_entry_backend=user_entry_backend,
        )
        logger.info("✅ LearningLoopQueryService created (UserEntry read-side peer)")

        # ADR-054 — UserEntry facade + processing dispatcher (the successor to
        # the former submissions + journal services).
        from core.services.user_entry import (
            AssessmentService,
            UserEntryProcessingService,
            UserEntryService,
        )

        user_entry_service = UserEntryService(
            backend=user_entry_backend,
            sharing_service=unified_sharing_service,
            interaction_service=interaction_service,
            event_bus=event_bus,
            group_service=group_service,
            user_service=user_service,  # Role gate for visibility=PUBLIC (Finding 2)
        )

        # Wire UserEntryService into the ingestion service so YAML uploads of
        # ``type: user_entry`` route through the same create_entry() pipeline
        # as the /submit form (ADR-054 — one path forward).
        unified_ingestion.user_entry_service = user_entry_service

        # Wire UserEntryService into EntryReportService (constructed earlier,
        # before user_entry_service existed) so generate_entry_response can do
        # the ownership-verified fetch + journal-chain eligibility check (ADR-069).
        entry_report_service.entry_service = user_entry_service

        # Wire ExerciseService into UserEntryService so create_entry() can
        # propagate exercise.enrichment_mode into entry.metadata for
        # InstructionResolver template dispatch (LLM_SUMMARY / TRANSCRIBE_AND_STRUCTURE).
        user_entry_service.exercise_service = exercise_service

        # Optional Digital pre-pass: LLM bridge tags untagged prose before the
        # Analog parser runs. FULL tier only; a keyless bridge would error on
        # every transform() call, so it degrades to None (parser-only) too.
        # Built before JournalService so the journals "Suggested activities"
        # panel and the EXTRACT_ACTIVITIES processor share one instance.
        dsl_bridge = None
        if tier.ai_enabled:
            from adapters.external.llm import create_llm_dsl_bridge

            bridge = create_llm_dsl_bridge()
            dsl_bridge = bridge if bridge.chat_port is not None else None
            if dsl_bridge is None:
                logger.info("⏭️  DSL bridge skipped (no OpenAI key) — parser-only extraction")
        else:
            logger.info("⏭️  DSL bridge skipped (intelligence tier: CORE) — parser-only extraction")

        # Canon retrieval: draws curated book passages from the walled reference
        # shelf to voice-infuse a summoned journal stage (Phase 3), and the
        # user's own non-private vault notes via the owner-scoped content chunk
        # index (canon P3 — two substrates, two ports, one contract). FULL tier
        # only — without embeddings there is no query vector, so it stays None
        # and the journal degrades to ungrounded. The reference adapter is NOT
        # wired into SearchRouter (that omission is the isolation guarantee).
        # Conversation persistence (ADR-078) — owner-private discussion sessions.
        # Tier-independent: pure storage, no LLM/embeddings, so it is created in
        # both CORE and FULL (unlike JournalService below). Thin standalone
        # backend (mirrors SessionBackend/DeviceBackend), NEVER the universal
        # Entity path — that is the structural understanding wall.
        from adapters.persistence.neo4j.backends.conversation_backend import ConversationBackend
        from core.services.conversation import ConversationService

        conversation_service = ConversationService(ConversationBackend(driver))
        logger.info("✅ ConversationService created (ADR-078 discussion store)")

        canon_retrieval_service = None
        if embeddings_service is not None:
            from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
            from core.services.canon import CanonRetrievalService

            canon_retrieval_service = CanonRetrievalService(
                reference_search=reference_chunk_adapter,
                embeddings_service=embeddings_service,
                # Stateless executor wrapper — a second instance is free
                # (precedented by the semantic-search wiring below).
                content_chunk_search=VectorSearchBackend(executor=query_executor),
            )
            logger.info("✅ CanonRetrievalService created (canon journaling companion)")

        # JournalService: DNWF three-stage workflow (FULL tier only, requires llm_caller)
        journal_service = None
        if llm_caller is not None:
            from core.services.journal import JournalService

            journal_service = JournalService(
                llm_caller=llm_caller,
                user_entry_service=user_entry_service,
                goals_service=activity_services["goals"],
                tasks_service=activity_services["tasks"],
                habits_service=activity_services["habits"],
                dsl_bridge=dsl_bridge,
                canon_retrieval_service=canon_retrieval_service,
                # ADR-081 D2: every typed turn grounds on the canonical
                # UnifiedUserContext.build() via the curated projection.
                context_builder=context_builder,
            )
            logger.info("✅ JournalService created")

        # JournalBatchService: the zero-persistence je_in/upload → je_out batch
        # pipeline (ADR-073). Tier-independent — created in CORE too, where each
        # mode degrades to its tier-error message (no Deepgram / no LLM).
        from core.services.journal import JournalBatchService

        journal_batch_service = JournalBatchService(
            batch_transcription_service=batch_transcription,
            llm_caller=llm_caller,
            journal_service=journal_service,
        )
        logger.info("✅ JournalBatchService created (je_in/upload → je_out pipeline)")

        # DSL activity extractor (ADR-069 — Pipeline.EXTRACT_ACTIVITIES).
        # Domain facades are the create surfaces; ps/lp/calendar/lifepath
        # carry no create-capable method today and finance was retired with
        # ADR-052, so those inject None (their parsed lines count in *_found
        # and skip cleanly).
        from core.services.dsl import ActivityExtractorService

        activity_extractor = ActivityExtractorService(
            tasks_service=activity_services["tasks"],
            habits_service=activity_services["habits"],
            goals_service=activity_services["goals"],
            events_service=activity_services["events"],
            principles_service=activity_services["principles"],
            choices_service=activity_services["choices"],
            finance_service=None,
            ku_service=learning_services["atomic_ku_service"],
            ps_service=None,
            lp_service=None,
            calendar_service=None,
            lifepath_service=None,
        )

        user_entry_processor = UserEntryProcessingService(
            entry_service=user_entry_service,
            transcription_adapter=core_services["deepgram_adapter"],
            llm_caller=llm_caller,
            instruction_resolver=instruction_resolver,
            event_bus=event_bus,
            activity_extractor=activity_extractor,
            dsl_bridge=dsl_bridge,
            user_service=user_service,
            goals_service=activity_services["goals"],
        )

        # Wire the processor into the ingestion service so a `pipeline:
        # extract_activities` periodic note auto-extracts its `- [ ]` lines into
        # Tasks on ingest (ADR-069). Same late-binding pattern as
        # `unified_ingestion.user_entry_service` above — `unified_ingestion` is
        # built earlier (:588), the processor depends on it, so this closes the
        # cycle without a circular import.
        unified_ingestion.user_entry_processor = user_entry_processor

        user_entry_assessment = AssessmentService(backend=user_entry_backend)

        # Vault bridge — ADR-070 bidirectional Obsidian ↔ SKUEL sync.
        # One descriptor-driven reconciler serves BOTH vaults: the admin content
        # vault (INGESTION_PATH, curriculum) and per-user personal vaults — the
        # primary one (VAULT_ROOT, bound to SKUEL_PERSONAL_VAULT_OWNER) plus a
        # member-vault family at {SKUEL_USER_VAULTS_ROOT}/{user_uid}/ for every
        # other user. Each vault is its own governed root with its own
        # fail-closed allowlist, owner account, and filesystem bridge.
        from pathlib import Path

        from adapters.vault.filesystem_adapter import FilesystemVaultAdapter
        from core.models.type_hints import UserUID
        from core.services.ingestion.config import build_sync_allowlist
        from core.services.vault.vault_descriptor import (
            VaultDescriptor,
            VaultKind,
            VaultRegistry,
        )
        from core.services.vault.vault_reconciler import VaultReconciler

        _personal_root = config.vault.vault_path
        _content_root = config.vault.ingestion_path
        # The account the content vault *acts as* (ADR-070). Canonical acts-as
        # ownership model: core/services/vault/vault_descriptor.py module docstring
        # (VaultRegistry.resolve_by_path).
        _content_owner = UserUID(config.vault.content_owner_uid)
        # The account VAULT_ROOT belongs to; every other user's personal vault
        # resolves to their own member directory under user_vaults_path.
        _personal_owner = UserUID(config.vault.personal_vault_owner_uid)

        # Resources/ is the raw reference library (full book texts, no `type:`
        # frontmatter) — DELIBERATELY walled, permanently (Arc D ruling
        # 2026-07-03: descriptor-only). Resource nodes are ingested from small
        # descriptor .md files elsewhere in the content vault (`Res/`); the raw
        # texts stay reference-only on disk. Full-text ingestion (bodies →
        # chunks → embeddings, one-Resource-many-files design) is a possible
        # later capability with its own design pass — do not remove this wall
        # without that ruling.
        _content_allowlist = build_sync_allowlist(
            _content_root,
            content_root=_content_root,
            excluded_dirs=frozenset({_content_root / "Resources"}),
            # The je_pro consent gate is a personal-vault concept — a content
            # folder merely named je_pro is curriculum, not a doorway.
            gates_je_pro=False,
        )

        _content_descriptor = VaultDescriptor(
            kind=VaultKind.CONTENT,
            root=_content_root,
            owner_uid=_content_owner,
            allowlist=_content_allowlist,
            bridge=FilesystemVaultAdapter(allowed_root=_content_root),
            supports_task_round_trip=False,  # curriculum writeback: designed-for, deferred
        )

        # Personal-vault transport (ADR-075 Decision 6). Fail-fast on an
        # unknown value; "filesystem" (default) keeps Stage 1 byte-for-byte.
        # The content vault above is server-local by definition and stays
        # filesystem regardless.
        _vault_transport = config.vault.validated_transport()

        def _build_personal_descriptor(owner_uid: UserUID, root: Path) -> VaultDescriptor:
            """One user's personal vault: per-root doorway wall + root-bound bridge.

            The wall is fail-closed (knowledge/ + notes + je_pro doorway folders) and
            code-sourced — NOT read from the ambient SKUEL_VAULT_SYNC_ALLOWED_DIRS
            env var, which used to shadow .env and silently wall off a folder.

            On the ``local_agent`` transport (ADR-075) the bridge speaks to the
            user's connected agent instead of the local disk, and ``root``
            becomes the server-side staging mirror the ``mirror_pull`` puller
            keeps faithful to the device before each ingest.
            """
            allowlist = build_sync_allowlist(root, content_root=_content_root)
            if _vault_transport == "local_agent":
                from adapters.inbound.agent_channel_registry import agent_channel_registry
                from adapters.vault.local_agent_adapter import LocalAgentVaultAdapter
                from core.services.vault.mirror_sync import VaultMirrorPuller

                agent_bridge = LocalAgentVaultAdapter(
                    registry=agent_channel_registry, mirror_root=root
                )
                resolved_root = root.resolve()
                # Server-side top-level folder names scope the pull + its
                # deletion sweep. The whole-vault-open combined-root shape
                # cannot reach here: validated_transport() rejects any
                # local_agent config whose mirror roots overlap INGESTION_PATH
                # (Kody #531), so the allowlist is always the doorway set.
                allowed_folders = frozenset(
                    d.relative_to(resolved_root).parts[0]
                    for d in allowlist.allowed_dirs
                    if d != resolved_root and d.is_relative_to(resolved_root)
                )
                return VaultDescriptor(
                    kind=VaultKind.PERSONAL,
                    root=root,
                    owner_uid=owner_uid,
                    allowlist=allowlist,
                    bridge=agent_bridge,
                    supports_task_round_trip=True,
                    mirror_pull=VaultMirrorPuller(
                        transport=agent_bridge,
                        mirror_root=root,
                        allowed_folders=allowed_folders,
                    ),
                )
            return VaultDescriptor(
                kind=VaultKind.PERSONAL,
                root=root,
                owner_uid=owner_uid,
                allowlist=allowlist,
                bridge=FilesystemVaultAdapter(allowed_root=root),
                supports_task_round_trip=True,
            )

        # Primary personal vault (VAULT_ROOT), bound to its real owner — no
        # placeholder stamping. Other users resolve to member vaults on demand
        # through the same factory.
        _personal_descriptor = _build_personal_descriptor(_personal_owner, _personal_root)
        vault_registry = VaultRegistry(
            content=_content_descriptor,
            personal=_personal_descriptor,
            user_vaults_root=config.vault.user_vaults_path,
            personal_descriptor_factory=_build_personal_descriptor,
        )

        # Residual single-file / domain ingestion doors (/api/ingest/file, etc.)
        # inherit the primary personal vault's wall; the reconciler passes each
        # vault's own allowlist explicitly.
        unified_ingestion.sync_allowlist = _personal_descriptor.allowlist
        logger.info(
            "✅ Vault sync allowlists active (fail-closed): "
            f"personal={len(_personal_descriptor.allowlist.allowed_dirs)} dir(s) "
            f"under {_personal_root} (owner: {_personal_owner}), "
            f"content=whole-vault under {_content_root} "
            f"(excluded: {len(_content_allowlist.excluded_dirs)} reference dir(s)); "
            f"member vaults under {config.vault.user_vaults_path}"
        )
        # Give the ingestion mechanism the registry so the OWNER of USER_OWNED
        # entities is resolved from the vault a file lives in (by-path), identical
        # across every ingest surface (dashboard / reconciler / script / watcher).
        unified_ingestion.vault_registry = vault_registry
        vault_reconciler = VaultReconciler(
            registry=vault_registry,
            unified_ingestion=unified_ingestion,
            user_entry_service=user_entry_service,
            tasks_service=activity_services["tasks"],
            user_service=user_service,
            # Retrievability probe (sync honesty): before/after embedding-
            # coverage counts so sync stats can say how much of the synced
            # content is not yet vector-searchable. Tier-independent.
            embedding_coverage=embedding_coverage_backend,
        )
        logger.info(
            "✅ UserEntry service + processing dispatcher + AssessmentService created (ADR-054)"
        )
        logger.info(
            "✅ VaultReconciler wired (ADR-070) — content + per-user personal "
            f"descriptors (personal transport: {_vault_transport}, ADR-075)"
        )

        # Create progress report generator and schedule service
        from adapters.persistence.neo4j.backends.misc_backends import ReportScheduleBackend
        from core.models.report_schedule import ReportSchedule
        from core.services.report.progress_report_generator import ProgressReportGenerator
        from core.services.report.progress_schedule_service import ProgressScheduleService

        progress_schedule_backend = ReportScheduleBackend(
            driver, NeoLabel.REPORT_SCHEDULE, ReportSchedule, prometheus_metrics=prometheus_metrics
        )
        progress_schedule_service = ProgressScheduleService(backend=progress_schedule_backend)

        # Create ActivityReportService (processor-neutral ActivityReport CRUD)
        from core.services.report.activity_report_service import ActivityReportService
        from core.services.report.review_queue_service import ReviewQueueService

        activity_report_service = ActivityReportService(
            backend=activity_report_backend,
            context_builder=context_builder,
            event_bus=event_bus,
        )
        from adapters.persistence.neo4j.backends.collab_backends import ReviewQueueBackend

        review_queue_backend = ReviewQueueBackend(executor=query_executor)
        review_queue_service = ReviewQueueService(backend=review_queue_backend)
        logger.info("✅ ActivityReportService + ReviewQueueService created")

        from adapters.persistence.neo4j.backends.misc_backends import ActivityReportGeneratorBackend

        report_generator_backend = ActivityReportGeneratorBackend(executor=query_executor)
        progress_generator = ProgressReportGenerator(
            report_backend=report_generator_backend,
            executor=query_executor,
            activity_report_service=activity_report_service,
            context_builder=context_builder,
            chat_port=openai_chat,
            insight_store=insight_store,
            event_bus=event_bus,
            analytics_service=None,  # Post-wired below after analytics_service creation
            knowledge_intelligence=activity_knowledge_intelligence,
        )

        # Create progress report background worker (February 2026)
        # Worker checks hourly for due schedules and generates ActivityReport Entity nodes
        from core.services.background.progress_report_worker import ProgressReportWorker

        progress_report_worker = ProgressReportWorker(
            schedule_service=progress_schedule_service,
            progress_generator=progress_generator,
            check_interval_seconds=3600,  # Hourly check
        )
        logger.info("✅ Progress report generator, schedule service, and background worker created")

        # Create analytics service
        from core.services.analytics_service import AnalyticsService

        analytics_service = AnalyticsService(
            tasks_service=activity_services["tasks"],
            habits_service=activity_services["habits"],
            goals_service=activity_services["goals"],
            events_service=activity_services["events"],
            choices_service=activity_services["choices"],
            principle_service=activity_services["principles"],
            content_enrichment=content_enrichment,  # ✅ ContentEnrichmentService - Layer 2 reporting
            ku_service=learning_services["ps"],  # Layer 0 reporting
            lp_service=learning_services["learning_paths"],  # Layer 0 reporting
            lifepath_service=lifepath_service,  # alignment snapshot history
            event_bus=event_bus,  # Event-driven report generation
            cross_domain_backend=cross_domain_backend,  # Cross-domain analytics queries
            knowledge_health_backend=knowledge_health_backend,  # ADR-080 Horizon-1 gauge
            embedding_coverage_backend=embedding_coverage_backend,  # retrievability block
        )
        logger.info("✅ Analytics service created")

        # Post-wire analytics_service into progress generator (created before analytics)
        progress_generator.analytics_service = analytics_service
        logger.info(
            "✅ ProgressReportGenerator wired with AnalyticsService + knowledge intelligence"
        )

        # =====================================================================
        # Create orchestration services (GoalTaskGenerator and HabitEventScheduler only)
        orchestration = _create_orchestration_services(
            goals_backend=goals_backend,
            tasks_backend=tasks_backend,
            habits_backend=habits_backend,
            events_backend=events_backend,
        )
        logger.info("✅ Orchestration services created")

        from core.orchestrator.profile_orchestrator import ProfileOrchestrator

        profile_orchestrator = ProfileOrchestrator(
            tasks_service=activity_services["tasks"],
            goals_service=activity_services["goals"],
            habits_service=activity_services["habits"],
            events_service=activity_services["events"],
            choices_service=activity_services["choices"],
            principles_service=activity_services["principles"],
            sharing_service=unified_sharing_service,
        )
        logger.info("✅ Profile Orchestrator created")

        # ADR-054: the former SubmissionsOrchestrator + JournalOrchestrator are retired.
        # UserEntryOrchestrator is the sole facade for submissions + journals.
        from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator
        from core.services.report import ReportRelationshipService

        report_relationship_service = ReportRelationshipService(backend=user_entry_backend)

        user_entry_orchestrator = UserEntryOrchestrator(
            user_entry_service=user_entry_service,
            exercises_service=exercise_service,
            teacher_review_service=teacher_review_service,
            user_service=user_service,
            activity_report_service=activity_report_service,
            revised_exercise_service=revised_exercise_service,
            entry_report_service=entry_report_service,
            sharing_service=unified_sharing_service,
            assessment_service=user_entry_assessment,
            report_relationship_service=report_relationship_service,
        )
        logger.info("✅ UserEntry Orchestrator created (ADR-054)")

        from core.orchestrator.explore_orchestrator import ExploreOrchestrator

        explore_orchestrator = ExploreOrchestrator(
            ku_service=learning_services["atomic_ku_service"],
            ps_service=learning_services["ps"],
            user_relationship_service=user_relationships,
            exercises_service=exercise_service,
            learning_loop_query_service=learning_loop_query_service,
            form_template_service=form_template_service,
        )
        logger.info("✅ Explore Orchestrator created")

        from core.orchestrator.library_orchestrator import LibraryOrchestrator

        library_orchestrator = LibraryOrchestrator(
            exercises_service=exercise_service,
            resource_service=resource_service,
            ku_service=learning_services["atomic_ku_service"],
            ps_service=learning_services["ps"],
            user_entry_service=user_entry_service,
            user_relationship_service=user_relationships,
        )
        logger.info("✅ Library Orchestrator created")

        admin_stats_service = AdminStatsService(
            backend=cross_domain_backend,
            search_event_backend=search_event_backend,
        )

        from core.orchestrator.teacher_orchestrator import TeacherOrchestrator

        teacher_orchestrator = TeacherOrchestrator(
            teacher_review_service=teacher_review_service,
            admin_stats=admin_stats_service,
        )
        logger.info("✅ Teacher Orchestrator created")

        from core.orchestrator.admin_orchestrator import AdminOrchestrator

        admin_orchestrator = AdminOrchestrator(
            user_service=user_service,
            admin_stats=admin_stats_service,
            system_service=system_service,
            analytics_service=analytics_service,  # ADR-080 knowledge-health gauge
        )
        logger.info("✅ Admin Orchestrator created")

        # Prerequisite-edge suggestions (Discovery Analytics PR 4) — read-only
        # candidate backend + the ONE sanctioned vault-write adapter (approve
        # writes an Edge YAML into {INGESTION_PATH}/edges/, never the graph).
        # Tier-independent construction: llm_service is None on CORE, where the
        # queue degrades to undirected pairs the admin classifies himself.
        from adapters.persistence.neo4j.prereq_candidate_backend import PrereqCandidateBackend
        from adapters.vault.content_edge_writer import ContentVaultEdgeWriter
        from core.services.prereq_suggestion_service import PrereqSuggestionService

        prereq_suggestions = PrereqSuggestionService(
            backend=PrereqCandidateBackend(query_executor),
            edge_writer=ContentVaultEdgeWriter(config.vault.ingestion_path),
            llm_service=llm_service,
        )
        logger.info("✅ PrereqSuggestionService created (admin edge-suggestion queue)")

        # Entry→Ku grounding (Entry-Enrichment PR 3). Tier-independent
        # construction: the candidate stage only READS stored vectors through
        # the Ku vector index, so CORE (which composes no shared vector-search
        # service — that one bundles the embeddings client) gets a client-less
        # instance; llm_service is None on CORE, where candidates write
        # vector-only. Triggers: post-sync pass in the vault sync doors +
        # scripts/ground_knowledge_entries.py backfill.
        from adapters.persistence.neo4j.entry_grounding_backend import EntryGroundingBackend
        from core.services.entry_grounding_service import EntryGroundingService

        grounding_vector_search = vector_search_service
        if grounding_vector_search is None:
            from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
            from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

            grounding_vector_search = Neo4jVectorSearchService(
                VectorSearchBackend(executor=query_executor)
            )

        entry_grounding = EntryGroundingService(
            backend=EntryGroundingBackend(query_executor),
            vector_search=grounding_vector_search,
            event_bus=event_bus,
            llm_service=llm_service,
        )
        logger.info("✅ EntryGroundingService created (entry→Ku grounding)")

        from core.orchestrator.activity_review_orchestrator import ActivityReviewOrchestrator

        activity_review_orchestrator = ActivityReviewOrchestrator(
            activity_report=activity_report_service,
            user_service=user_service,
            review_queue=review_queue_service,
            context_builder=context_builder,
        )
        logger.info("✅ Activity Review Orchestrator created")

        from core.orchestrator.pathways_orchestrator import PathwaysOrchestrator

        pathways_orchestrator = PathwaysOrchestrator(
            lp_service=learning_services["learning_paths"],
            user_progress=learning_services["user_progress"],
        )
        logger.info("✅ Pathways Orchestrator created")

        from core.orchestrator.lateral_relationships_orchestrator import (
            LateralRelationshipsOrchestrator,
        )

        lateral_orchestrator = LateralRelationshipsOrchestrator(
            lateral_service=lateral_service,
            tasks_service=activity_services["tasks"],
            goals_service=activity_services["goals"],
            habits_service=activity_services["habits"],
            events_service=activity_services["events"],
            choices_service=activity_services["choices"],
            principles_service=activity_services["principles"],
        )
        logger.info("✅ Lateral Relationships Orchestrator created")

        # Create advanced services
        advanced = _create_advanced_services(
            driver, query_executor=query_executor, cross_domain_backend=cross_domain_backend
        )
        await advanced["performance_optimization"].initialize()
        logger.info("✅ Advanced services created")

        from core.orchestrator.calendar_optimization_orchestrator import (
            CalendarOptimizationOrchestrator,
        )

        calendar_optimization_orchestrator = CalendarOptimizationOrchestrator(
            calendar_service=advanced["calendar_optimization"],
            tasks_service=activity_services["tasks"],
            events_service=activity_services["events"],
        )
        logger.info("✅ Calendar Optimization Orchestrator created")

        from ui.today.orchestrator import TodayOrchestrator

        today_orchestrator = TodayOrchestrator(
            tasks_service=activity_services["tasks"],
            goals_service=activity_services["goals"],
            habits_service=activity_services["habits"],
            events_service=activity_services["events"],
            principles_service=activity_services["principles"],
            lifepath_service=lifepath_service,
            user_relationship_service=user_relationships,
        )
        logger.info("✅ Today Orchestrator created")

        # Wire orchestration services into context_service
        context_service.goal_task_generator = orchestration["goal_task_generator"]
        context_service.habits_service = activity_services["habits"]
        logger.info("✅ UserContextService wired with GoalTaskGenerator and HabitsService")

        # Post-wire goals_service into habits (cross-domain dependency)
        activity_services["habits"].goals_service = activity_services["goals"]
        # HabitsGoalAnalyticsService shelved (2026-03-28)
        logger.info("✅ HabitsService wired with GoalsService")

        # Post-wire habits_service into goals intelligence (cross-domain dependency)
        activity_services["goals"].intelligence.habits_service = activity_services["habits"]
        logger.info("✅ GoalsIntelligenceService wired with HabitsService")

        # Exercise linker for UserEntry → FULFILLS_EXERCISE validation.
        # Subscribed to UserEntryCreated inside _wire_event_subscribers.
        from core.services.user_entry.exercise_linker import UserEntryExerciseLinker

        user_entry_exercise_linker = UserEntryExerciseLinker(backend=user_entry_backend)
        logger.info("✅ UserEntryExerciseLinker created")

        # Wire all event subscribers (context invalidation + cross-domain + intelligence)
        _wire_event_subscribers(
            event_bus=event_bus,
            user_service=user_service,
            activity_services=activity_services,
            learning_services=learning_services,
            user_entry_exercise_linker=user_entry_exercise_linker,
            notification_service=notification_service,
            advanced=advanced,
            analytics_service=analytics_service,
            user_entry_backend=user_entry_backend,
            insight_store=insight_store,
            group_backend=group_backend,
            ps_engagement=template_services["ps_engagement"],
            search_event_recorder=search_event_recorder,
            interaction_service=interaction_service,
        )
        logger.info("✅ All services initialized")

        # Compose the services container
        services = Services(
            # Activity Domains (6) - All from unified activity_services
            tasks=activity_services["tasks"],
            goals=activity_services["goals"],
            habits=activity_services["habits"],
            events=activity_services["events"],
            choices=activity_services["choices"],
            principles=activity_services["principles"],
            # Finance (NOT an Activity Domain - separate facade)
            finance=core_services["finance"],
            # Curriculum
            ku=learning_services["atomic_ku_service"],
            resource=resource_service,
            activity_knowledge_intelligence=learning_services["activity_knowledge_intelligence"],
            # Content
            content_enrichment=content_enrichment,
            report_mastery=report_mastery_service,  # Explicit mastery propagation
            entry_report=entry_report_service,  # LLM report on submissions/journals
            exercises=exercise_service,  # Reusable LLM instruction templates
            revised_exercises=revised_exercise_service,  # Four-phase learning loop revisions
            form_templates=form_template_service,  # General-purpose form templates
            form_submissions=form_submission_service,  # User form submissions
            interaction_service=interaction_service,  # User Interaction Contract
            # Batch transcription (Tier 1). Tier 2 BatchProcessingService retired
            # in ADR-054 Commit 6a — lives inside UserEntryProcessingService now.
            batch_transcription=batch_transcription,
            # Group & Teaching (ADR-040: Teacher exercise workflow)
            groups=group_service,
            teacher_review=teacher_review_service,
            # Notifications
            notifications=notification_service,
            # Note: audio_service removed (Dec 2025) - use transcription service directly
            # Sharing
            sharing=unified_sharing_service,  # Cross-domain sharing and visibility control
            # UserEntry (ADR-054) — unified user-authored content
            user_entry=user_entry_service,
            user_entry_processor=user_entry_processor,
            user_entry_assessment=user_entry_assessment,
            vault_reconciler=vault_reconciler,
            # Progress report (February 2026)
            progress_report_generator=progress_generator,
            progress_schedule=progress_schedule_service,
            # Activity report + review queue (March 2026 refactor)
            activity_report=activity_report_service,
            review_queue=review_queue_service,
            # System
            # Note: sync field removed (January 2026) - use unified_ingestion
            unified_ingestion=unified_ingestion,  # ADR-014: Merged MD + YAML ingestion
            batch_chunking_service=batch_chunking_service,  # Phase 2 admin tool
            calendar=calendar_service,
            system=system_service,
            admin_stats=admin_stats_service,
            visualization=visualization_service,  # Chart.js/Vis.js/Gantt adapters
            transcription=core_services["transcription"],
            # User management
            user=core_services["user"],
            user_relationships=user_relationships,  # UserRelationshipBackend (pinning, following)
            graph_auth=graph_auth,  # Graph-native authentication (January 2026)
            context=context_service,  # Context-aware intelligence (NEW: 2025-11-18)
            # Learning services
            user_progress=learning_services["user_progress"],
            # unified_progress DELETED (January 2026) - use user_progress
            lp=learning_services["learning_paths"],  # ku, ps, lp short-name consistency
            ps=learning_services["ps"],  # ku, ps, lp short-name consistency
            ps_engagement=template_services["ps_engagement"],  # PS+Activity lifecycle (Phase 4)
            # PS+Activity Template CRUD services (Phase 5 — May 2026)
            task_templates=template_services["task_templates"],
            goal_templates=template_services["goal_templates"],
            habit_templates=template_services["habit_templates"],
            event_templates=template_services["event_templates"],
            choice_templates=template_services["choice_templates"],
            principle_templates=template_services["principle_templates"],
            learning_intelligence=learning_services["learning_intelligence"],
            askesis=None,  # Created in PHASE 4 after intelligence_factory (January 2026)
            askesis_core=askesis_core_service,  # Priority 1.1: CRUD operations for Askesis AI
            # Infrastructure
            graph_adapter=neo4j_adapter,
            event_bus=event_bus,
            prometheus_metrics=prometheus_metrics,
            neo4j_driver=driver,
            query_executor=query_executor,
            connection_fetch_backend=connection_fetch_backend,  # Activity UI connections
            insight_store=insight_store,  # Event-driven insights
            # GenAI services (Neo4j native - January 2026)
            embeddings_service=embeddings_service,
            vector_search_service=vector_search_service,
            # Background workers (January 2026)
            embedding_worker=embedding_worker,
            progress_report_worker=progress_report_worker,
            # Analytics
            analytics=analytics_service,
            cross_domain_analytics=advanced["cross_domain_analytics"],
            # LifePath (Domain #14: The Destination)
            lifepath=lifepath_service,
            # Orchestration (Activity Domains already assigned above)
            goal_task_generator=orchestration["goal_task_generator"],
            habit_event_scheduler=orchestration["habit_event_scheduler"],
            admin_orchestrator=admin_orchestrator,
            prereq_suggestions=prereq_suggestions,
            entry_grounding=entry_grounding,
            profile_orchestrator=profile_orchestrator,
            user_entry_orchestrator=user_entry_orchestrator,
            explore_orchestrator=explore_orchestrator,
            library_orchestrator=library_orchestrator,
            teacher_orchestrator=teacher_orchestrator,
            activity_review_orchestrator=activity_review_orchestrator,
            pathways_orchestrator=pathways_orchestrator,
            lateral_orchestrator=lateral_orchestrator,
            calendar_optimization_orchestrator=calendar_optimization_orchestrator,
            today_orchestrator=today_orchestrator,
            # Advanced
            jupyter_sync=advanced["jupyter_sync"],
            performance_optimization=advanced["performance_optimization"],
            # Cross-cutting AI services (require LLM/embeddings)
            askesis_ai=askesis_ai,
            context_aware_ai=context_aware_ai,
            # Journal domain — DNWF three-stage workflow (FULL tier only)
            journal=journal_service,
            journal_batch=journal_batch_service,
            # Conversation store — owner-private discussion sessions (ADR-078)
            conversation=conversation_service,
            # Lateral relationship services (January 2026 - Core graph architecture)
            lateral=lateral_service,
            # Intelligence tier (ADR-043)
            intelligence_tier=tier,
        )

        # Create UserContextIntelligence factory, ZPD service, and Askesis
        _create_intelligence_hub(
            services=services,
            activity_services=activity_services,
            learning_services=learning_services,
            user_entry_backend=user_entry_backend,
            calendar_service=calendar_service,
            vector_search_service=vector_search_service,
            driver=driver,
            event_bus=event_bus,
            tier=tier,
            context_builder=context_builder,
            user_service=user_service,
            askesis_core_service=askesis_core_service,
            canon_service=canon_retrieval_service,
        )

        # ========================================================================
        # CREATE SEARCH ROUTER (One Path Forward, January 2026)
        # ========================================================================
        # SearchRouter = THE path for all search. No fallback needed.
        # Activity Domains → graph_aware_faceted_search()
        # Curriculum Domains → simple text search via domain services
        # Cross-domain → aggregates from all searchable domains
        from core.orchestrator.search_router import SearchRouter

        # Explicit DI: each keyword matches the Services field of the same name
        # (the invariant test_search_router_registry pins), so a container
        # rename can no longer silently strand a domain out of search.
        search_router = SearchRouter(
            tasks=services.tasks,
            goals=services.goals,
            habits=services.habits,
            events=services.events,
            choices=services.choices,
            principles=services.principles,
            finance=services.finance,
            ku=services.ku,
            ps=services.ps,
            lp=services.lp,
            exercises=services.exercises,
            revised_exercises=services.revised_exercises,
            user_entry=services.user_entry,
            lifepath=services.lifepath,
            calendar=services.calendar,
            user=services.user,
            vector_search_service=services.vector_search_service,
            event_bus=services.event_bus,
        )
        services.search_router = search_router
        logger.info("✅ SearchRouter created (One Path Forward)")

        # Post-wire SearchRouter onto Askesis's ContextRetriever — chunk (RAG)
        # retrieval flows through the router (Scoped Ask, PR2). Askesis is built
        # before the router (FULL tier only), so this is a post-construction wire.
        # services.askesis is protocol-typed (AskesisOperations); narrow to the
        # concrete facade to reach its internal context_retriever.
        from core.services.askesis_service import AskesisService

        if isinstance(services.askesis, AskesisService):
            services.askesis.context_retriever.search_router = search_router
            logger.info("✅ SearchRouter wired to Askesis ContextRetriever (Scoped Ask)")

        # ========================================================================
        # VALIDATE POST-CONSTRUCTION WIRING (fail-fast if any was missed)
        # ========================================================================
        post_wiring_checks = {
            "context_service.tasks_service": context_service.tasks_service,
            "context_service.goal_task_generator": context_service.goal_task_generator,
            "context_service.habits_service": context_service.habits_service,
            "user_service.intelligence_factory": user_service.intelligence_factory,
            "services.context_intelligence": services.context_intelligence,
            "services.search_router": services.search_router,
            "form_submission_service.sharing_service": form_submission_service.sharing_service,
            # habits.goal_analytics shelved (2026-03-28)
        }
        # Askesis is FULL-tier only (None in CORE) — only assert its wiring when present.
        if isinstance(services.askesis, AskesisService):
            post_wiring_checks["askesis.context_retriever.search_router"] = (
                services.askesis.context_retriever.search_router
            )
        missing = [name for name, value in post_wiring_checks.items() if value is None]
        if missing:
            raise ValueError(
                f"Post-construction wiring incomplete — these attributes are None: "
                f"{', '.join(missing)}"
            )
        logger.info(
            f"✅ Post-construction wiring validated ({len(post_wiring_checks)} attributes checked)"
        )

        logger.info("✅ Service composition complete")
        return Result.ok(services)

    except TypeError, AttributeError, ImportError, NameError:
        # Programming errors must propagate — they indicate real bugs in wiring,
        # not runtime configuration failures. Masking them as Result.fail() hides
        # the root cause during development.
        raise
    except Exception as e:  # safety-net: bootstrap boundary catches config/infra failures
        import traceback

        logger.error(f"❌ Service composition failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return Result.fail(
            Errors.system(
                f"Service initialization failed: {e!s}",
                service="ServiceContainer",
                error_type=type(e).__name__,
            )
        )
