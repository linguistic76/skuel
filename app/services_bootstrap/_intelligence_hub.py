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
    user_entry_backend: Any,
    calendar_service: Any,
    vector_search_service: Any,
    driver: Any,
    event_bus: EventBusOperations,
    tier: "IntelligenceTier",
    context_builder: Any,
    user_service: Any,
    askesis_core_service: Any,
) -> None:
    """Create UserContextIntelligence factory, ZPD service, and Askesis.

    Mutates ``services``, ``context_builder``, and ``user_service`` to wire the
    intelligence hub into the running application.
    """
    from core.services.analytics_relationship_service import AnalyticsRelationshipService
    from core.services.report import ReportRelationshipService
    from core.services.user.intelligence import UserContextIntelligenceFactory
    from core.services.user_entry import UserEntryRelationshipService

    entry_relationship_service = UserEntryRelationshipService(backend=user_entry_backend)
    report_relationship_service = ReportRelationshipService(backend=user_entry_backend)
    analytics_relationship_service = AnalyticsRelationshipService(driver)
    logger.info("✅ Processing domain relationship services created (UserEntry, Report, Analytics)")

    # ── PsEngagementService post-wire to context_builder (ADR-059) ──────────
    # ps_engagement is core-tier (always wired by template_services). Bind it
    # to the builder here so build_rich() can populate active_ps_engagements
    # for engagement-aware daily planning in DailyPlanningMixin.
    if services.ps_engagement is not None:
        context_builder.ps_engagement_service = services.ps_engagement
        logger.info("✅ PsEngagementService wired to UserContextBuilder (ADR-059)")
    else:
        logger.warning(
            "⚠️ services.ps_engagement is None — daily plan will lack engagement buckets"
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
        from core.events.learning_loop_events import (
            ReportSubmitted as ZPDReportSubmitted,
        )
        from core.events.learning_loop_events import (
            UserEntryApproved as ZPDEntryApproved,
        )

        event_bus.subscribe(ZPDEntryApproved, zpd_handler.handle_submission_approved)
        event_bus.subscribe(ZPDReportSubmitted, zpd_handler.handle_report_submitted)
        event_bus.subscribe(ZPDKMastered, zpd_handler.handle_knowledge_mastered)
        event_bus.subscribe(ZPDPSCompleted, zpd_handler.handle_path_step_completed)
        event_bus.subscribe(ZPDLPProgress, zpd_handler.handle_learning_path_progress)
        logger.info(
            "✅ ZPD snapshot handler subscribed to 5 events "
            "(UserEntryApproved, ReportSubmitted, KnowledgeMastered, "
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
        "ku": learning_services["atomic_ku_service"],
        "ps": learning_services["ps"],
        "learning_paths": learning_services["learning_paths"],
    }
    # Exercise is created in compose_services, passed via services container
    if services.exercises is not None:
        filtered_providers["exercises"] = services.exercises  # type: ignore[assignment]  # ExerciseOperations satisfies FilteredContextProvider protocol

    # ── UserContextIntelligence factory (13-domain architecture) ────────────
    if services.exercises is None:
        raise RuntimeError(
            "UserContextIntelligence factory requires services.exercises (ExerciseService). "
            "compose_services must wire ExerciseService before _create_intelligence_hub."
        )
    activity_relationships = {
        name: activity_services[name].relationships
        for name in ("tasks", "goals", "habits", "events", "choices", "principles")
    }
    context_intelligence_factory = UserContextIntelligenceFactory(
        **activity_relationships,
        # Curriculum Domains (3)
        ps=learning_services["ps"],
        lp=learning_services["learning_paths"].relationships,  # factory param name
        exercises=services.exercises,
        # Processing Domains (3)
        user_entries=entry_relationship_service,
        report=report_relationship_service,
        analytics=analytics_relationship_service,
        # Temporal Domain (1)
        calendar=calendar_service,
        # Optional services
        vector_search_service=vector_search_service,
        zpd_service=zpd_service,
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

    # ── Askesis service — FULL tier only (no degraded mode) ─────────────────
    # March 2026: Gated behind tier.ai_enabled — Askesis requires all AI deps
    if tier.ai_enabled:
        from core.services.askesis_citation_service import AskesisCitationService
        from core.services.askesis_factory import create_askesis_service

        citation_service = AskesisCitationService(
            backend=learning_services["ps"].core.backend,
        )

        # ps_engagement is core-tier (no AI), so it's always wired by the
        # template_services bootstrap step before this hub runs. A None here
        # would mean the lifecycle layer didn't compose — fail fast.
        if services.ps_engagement is None:
            raise RuntimeError(
                "Askesis cannot be created without PsEngagementService — "
                "bootstrap order is broken (template_services must run first)."
            )

        # Askesis grounds answers in :ContentChunk vectors. Without vector_search_service
        # it silently degrades to graph-only context (Gap #6). FULL tier promises both
        # services; missing vector_search_service here means embedding bootstrap was
        # swallowed somewhere upstream.
        if vector_search_service is None:
            raise RuntimeError(
                "Askesis cannot be created without vector_search_service in FULL tier — "
                "chunk retrieval would silently fall back to graph-only context. "
                "Check embedding bootstrap (_learning_services.py)."
            )

        services.askesis = create_askesis_service(
            intelligence_factory=context_intelligence_factory,
            learning_services=learning_services,
            activity_services=activity_services,
            user_service=user_service,
            askesis_core_service=askesis_core_service,
            zpd_service=zpd_service,
            ps_engagement_service=services.ps_engagement,
            citation_service=citation_service,
        )
        logger.info(
            "✅ Askesis service created with intelligence_factory (13-domain synthesis + ZPD)"
        )
    else:
        logger.info("⏭️ Askesis service skipped (intelligence tier: CORE)")
