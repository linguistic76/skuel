"""Intelligence hub wiring — UserContextIntelligence, ZPD, and Askesis."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from core.ports import EventBusOperations, ZPDOperations
from core.ports.filtered_context_protocols import FilteredContextProvider
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.config.intelligence_tier import IntelligenceTier
    from services_bootstrap._container import Services

logger = get_logger("skuel.bootstrap")


def _filtered_context_providers(
    activity_services: Mapping[str, object],
    learning_services: Mapping[str, object],
    exercises: object,
) -> dict[str, FilteredContextProvider]:
    """Map each domain name to the facade that serves its filtered context.

    The composition root holds its services in ``Any``-valued dicts, so an
    annotation on the returned dict would prove nothing about what is put in it.
    Each facade is checked against ``FilteredContextProvider`` here, and one that
    does not expose ``get_filtered_context`` stops the boot rather than reaching
    a caller.

    Raises:
        RuntimeError: naming the domain whose facade is not a provider.
    """
    candidates: dict[str, object] = {
        "tasks": activity_services["tasks"],
        "goals": activity_services["goals"],
        "habits": activity_services["habits"],
        "events": activity_services["events"],
        "choices": activity_services["choices"],
        "principles": activity_services["principles"],
        "ps": learning_services["ps"],
        "learning_paths": learning_services["learning_paths"],
        "exercises": exercises,
    }
    providers: dict[str, FilteredContextProvider] = {}
    for domain, facade in candidates.items():
        if not isinstance(facade, FilteredContextProvider):
            raise RuntimeError(
                f"filtered_providers[{domain!r}] is a {type(facade).__name__}, which has no "
                "get_filtered_context — only a FilteredContextProvider may be registered."
            )
        providers[domain] = facade
    return providers


def _create_intelligence_hub(
    services: Services,
    activity_services: dict[str, Any],
    learning_services: dict[str, Any],
    user_entry_backend: Any,
    calendar_service: Any,
    vector_search_service: Any,
    driver: Any,
    event_bus: EventBusOperations,
    tier: IntelligenceTier,
    context_builder: Any,
    user_service: Any,
    askesis_core_service: Any,
    canon_service: Any = None,
) -> None:
    """Create UserContextIntelligence factory, ZPD service, and Askesis.

    Mutates ``services``, ``context_builder``, and ``user_service`` to wire the
    intelligence hub into the running application.

    ``canon_service`` is the CanonRetrievalService built in compose_services —
    forwarded into Askesis for PS-scoped readings grounding (ADR-077). None when
    embeddings are absent (guided pipeline degrades canon-free).
    """
    from core.services.report import ReportRelationshipService
    from core.services.user.intelligence import UserContextIntelligenceFactory

    report_relationship_service = ReportRelationshipService(backend=user_entry_backend)
    logger.info("✅ Processing domain relationship service created (Report)")

    # ── PsEngagementService post-wire to context_builder (ADR-059) ──────────
    # ps_engagement is core-tier (always wired by template_services before this
    # hub runs). A None here means the lifecycle layer didn't compose — fail
    # fast rather than silently leaving daily planning without engagement
    # buckets. Same invariant the Askesis branch below enforces.
    if services.ps_engagement is None:
        raise RuntimeError(
            "UserContextBuilder cannot wire engagement-aware daily planning "
            "without PsEngagementService — bootstrap order is broken "
            "(template_services must run before _create_intelligence_hub)."
        )
    context_builder.ps_engagement_service = services.ps_engagement
    logger.info("✅ PsEngagementService wired to UserContextBuilder (ADR-059)")

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

    # ── UserContextIntelligence factory ─────────────────────────────────────
    if services.exercises is None:
        raise RuntimeError(
            "UserContextIntelligence factory requires services.exercises (ExerciseService). "
            "compose_services must wire ExerciseService before _create_intelligence_hub."
        )
    # Intelligence services ask a provider by domain name for its filtered view.
    filtered_providers = _filtered_context_providers(
        activity_services, learning_services, services.exercises
    )
    context_intelligence_factory = UserContextIntelligenceFactory(
        # Activity Domains (6) — facade services (not .relationships)
        tasks=activity_services["tasks"],
        goals=activity_services["goals"],
        habits=activity_services["habits"],
        events=activity_services["events"],
        choices=activity_services["choices"],
        principles=activity_services["principles"],
        # Curriculum Domains (3)
        ps=learning_services["ps"],
        lp=learning_services["learning_paths"].relationships,  # factory param name
        exercises=services.exercises,
        # Processing Domain (1)
        report=report_relationship_service,
        # Temporal Domain (1)
        calendar=calendar_service,
        # Optional services
        vector_search_service=vector_search_service,
        zpd_service=zpd_service,
        filtered_providers=filtered_providers,
    )
    services.context_intelligence = context_intelligence_factory
    logger.info(
        "✅ UserContextIntelligence factory created (11 domain services + ZPD + %d filtered providers)",
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

        # Askesis grounds answers in :ContentChunk vectors, reached via
        # SearchRouter.retrieve_scoped_chunks (which reads services.vector_search_service).
        # FULL tier promises vector search; a None here means embedding bootstrap was
        # swallowed upstream and the router would have nothing to retrieve from.
        if vector_search_service is None:
            raise RuntimeError(
                "Askesis cannot be created without vector_search_service in FULL tier — "
                "SearchRouter chunk retrieval would have no vector backend. "
                "Check embedding bootstrap (_learning_services.py)."
            )

        # ZPDService is created in this same tier.ai_enabled branch above; in FULL
        # tier it is always non-None. create_askesis_service requires a concrete
        # ZPDOperations (Askesis pedagogy is ZPD-grounded) — fail fast rather than
        # pass None through the boundary the two-block control flow hides from mypy.
        if zpd_service is None:
            raise RuntimeError(
                "Askesis (FULL tier) requires ZPDService — it was not created in the "
                "tier.ai_enabled branch. Bootstrap order or ZPD wiring is broken."
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
            canon_service=canon_service,
        )
        logger.info(
            "✅ Askesis service created with intelligence_factory (13-domain synthesis + ZPD)"
        )
    else:
        logger.info("⏭️ Askesis service skipped (intelligence tier: CORE)")
