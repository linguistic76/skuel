"""Intelligence hub wiring — UserContextIntelligence, ZPD, and Askesis."""

from typing import TYPE_CHECKING, Any

from core.ports import EventBusOperations, ZPDOperations
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.config.intelligence_tier import IntelligenceTier
    from core.ports.filtered_context_protocols import FilteredContextProvider
    from services_bootstrap._container import Services

logger = get_logger("skuel.bootstrap")


async def _create_intelligence_hub(
    services: "Services",
    activity_services: dict[str, Any],
    learning_services: dict[str, Any],
    submissions_backend: Any,
    calendar_service: Any,
    vector_search_service: Any,
    driver: Any,
    event_bus: EventBusOperations,
    tier: "IntelligenceTier",
    context_builder: Any,
    user_service: Any,
    context_service: Any,
    askesis_core_service: Any,
) -> None:
    """Create UserContextIntelligence factory, ZPD service, and Askesis.

    Mutates ``services``, ``context_builder``, ``user_service``, and ``context_service``
    to wire the intelligence hub into the running application.
    """
    from core.services.analytics_relationship_service import AnalyticsRelationshipService
    from core.services.report import ReportRelationshipService
    from core.services.submissions import SubmissionsRelationshipService
    from core.services.user.intelligence import UserContextIntelligenceFactory

    # Create processing domain relationship services
    # NOTE: JournalRelationshipService REMOVED (February 2026) - Journal merged into Entity model
    # SubmissionsRelationshipService handles all submission content relationships
    submissions_relationship_service = SubmissionsRelationshipService(backend=submissions_backend)
    report_relationship_service = ReportRelationshipService(backend=submissions_backend)
    analytics_relationship_service = AnalyticsRelationshipService(driver)
    logger.info(
        "✅ Processing domain relationship services created (Submissions, Report, Analytics)"
    )

    # ── ZPD Service (March 2026 — pedagogical core of Askesis) ──────────────
    # Gated by INTELLIGENCE_TIER=FULL — requires behavioral signals from
    # choices + habits intelligence services.
    # Returns empty assessment (not an error) when curriculum graph < 3 KUs.
    from adapters.persistence.neo4j.zpd_backend import ZPDBackend
    from core.services.zpd import ZPDService

    zpd_service: ZPDOperations | None = None
    if tier.ai_enabled:
        zpd_backend = ZPDBackend(driver)
        zpd_service = ZPDService(
            backend=zpd_backend,
            choices_intelligence=activity_services["choices"].intelligence,
            habits_intelligence=activity_services["habits"].intelligence,
        )
        services.zpd_service = zpd_service
        context_builder.zpd_service = zpd_service
        logger.info(
            "✅ ZPDService created (behavioral signals: choices + habits, wired to context_builder)"
        )

        # ZPD snapshot event subscriptions
        from adapters.persistence.neo4j.zpd_snapshot_backend import ZPDSnapshotBackend
        from core.services.zpd.zpd_event_handler import ZPDSnapshotHandler

        zpd_snapshot_backend = ZPDSnapshotBackend(driver)
        zpd_handler = ZPDSnapshotHandler(zpd_service, zpd_snapshot_backend)

        from core.events.curriculum_events import PathStepCompleted as ZPDPSCompleted
        from core.events.learning_events import KnowledgeMastered as ZPDKMastered
        from core.events.learning_events import (
            LearningPathProgressUpdated as ZPDLPProgress,
        )
        from core.events.submission_events import (
            ReportSubmitted as ZPDReportSubmitted,
        )
        from core.events.submission_events import (
            SubmissionApproved as ZPDSubApproved,
        )

        event_bus.subscribe(ZPDSubApproved, zpd_handler.handle_submission_approved)
        event_bus.subscribe(ZPDReportSubmitted, zpd_handler.handle_report_submitted)
        event_bus.subscribe(ZPDKMastered, zpd_handler.handle_knowledge_mastered)
        event_bus.subscribe(ZPDPSCompleted, zpd_handler.handle_path_step_completed)
        event_bus.subscribe(ZPDLPProgress, zpd_handler.handle_learning_path_progress)
        logger.info(
            "✅ ZPD snapshot handler subscribed to 5 events "
            "(SubmissionApproved, ReportSubmitted, KnowledgeMastered, "
            "PathStepCompleted, LearningPathProgressUpdated)"
        )
    else:
        logger.info("⏭️  ZPDService skipped (intelligence tier: CORE)")

    # ── FilteredContextProvider dict (11 domains with get_filtered_context) ──
    # Maps domain names to facades that implement FilteredContextProvider protocol.
    # Intelligence services use this for on-demand, per-domain filtered queries.
    filtered_providers: dict[str, FilteredContextProvider] = {
        # Activity Domains (6) — facades are the services dict values
        "tasks": activity_services["tasks"],
        "goals": activity_services["goals"],
        "habits": activity_services["habits"],
        "events": activity_services["events"],
        "choices": activity_services["choices"],
        "principles": activity_services["principles"],
        # Curriculum Domains (3) — facades from learning_services
        # "lessons" key uses PsService (merged Lesson into PathStep)
        "lessons": learning_services["path_steps"],
        "ku": learning_services["atomic_ku_service"],
        "path_steps": learning_services["path_steps"],
        "learning_paths": learning_services["learning_paths"],
    }
    # Exercise is created in compose_services, passed via services container
    if services.exercises is not None:
        filtered_providers["exercises"] = services.exercises  # type: ignore[assignment]  # ExerciseOperations satisfies FilteredContextProvider protocol

    # ── UserContextIntelligence factory (13-domain architecture) ────────────
    context_intelligence_factory = UserContextIntelligenceFactory(
        # Activity Domains (6) - All from unified activity_services
        tasks=activity_services["tasks"].relationships,
        goals=activity_services["goals"].relationships,
        habits=activity_services["habits"].relationships,
        events=activity_services["events"].relationships,
        choices=activity_services["choices"].relationships,
        principles=activity_services["principles"].relationships,
        # Curriculum Domains (3)
        lesson=learning_services["path_steps"],  # PsService (merged Lesson into PathStep)
        ps=learning_services["path_steps"].relationships,
        lp=learning_services["learning_paths"].relationships,  # Factory expects 'lp' parameter name
        # Processing Domains (3)
        submissions=submissions_relationship_service,  # SubmissionsRelationshipService
        report=report_relationship_service,  # ReportRelationshipService
        analytics=analytics_relationship_service,  # AnalyticsRelationshipService
        # Temporal Domain (1)
        calendar=calendar_service,
        # Optional: Vector search for semantic enhancements
        vector_search_service=vector_search_service,
        # Optional: ZPD service for curriculum-graph-aware path step ranking
        zpd_service=zpd_service,
        # FilteredContextProvider dict for on-demand domain queries
        filtered_providers=filtered_providers,
    )
    services.context_intelligence = context_intelligence_factory
    logger.info(
        "✅ UserContextIntelligence factory created (13 domain services + ZPD + %d filtered providers)",
        len(filtered_providers),
    )

    # Wire intelligence factory to UserService (post-construction wiring)
    user_service.intelligence_factory = context_intelligence_factory
    logger.info("✅ UserService wired with intelligence factory")

    # Wire intelligence factory to UserContextService (post-construction wiring)
    # This enables get_context_summary() to use factory.create() for intelligence queries
    context_service.intelligence_factory = context_intelligence_factory
    logger.info("✅ UserContextService wired with intelligence factory")

    # ── Askesis service — FULL tier only (no degraded mode) ─────────────────
    # March 2026: Gated behind tier.ai_enabled — Askesis requires all AI deps
    if tier.ai_enabled:
        from core.services.askesis_citation_service import AskesisCitationService
        from core.services.askesis_factory import create_askesis_service

        citation_service = AskesisCitationService(
            backend=learning_services["path_steps"].core.backend,
        )

        services.askesis = create_askesis_service(
            intelligence_factory=context_intelligence_factory,
            learning_services=learning_services,
            activity_services=activity_services,
            user_service=user_service,
            askesis_core_service=askesis_core_service,
            zpd_service=zpd_service,
            citation_service=citation_service,
        )
        logger.info(
            "✅ Askesis service created with intelligence_factory (13-domain synthesis + ZPD)"
        )
    else:
        logger.info("⏭️ Askesis service skipped (intelligence tier: CORE)")
