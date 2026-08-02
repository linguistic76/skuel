"""
Enhanced Principles Service - Facade Pattern
=============================================

Principles service facade that delegates to specialized sub-services.
Uses Entity model with EntityType.PRINCIPLE discrimination.

Architecture: Shell delegates to 3 focused mixins in the same directory:
  _embodiment_mixin.py  — expressions, alignment history, portfolio, integrity
  _gravity_mixin.py     — cross-domain links (goals, habits, knowledge, choices)
  _enrichment_mixin.py  — analytics summary, search, sources, prioritization

Sub-Services:
- PrinciplesCoreService: CRUD operations for principles
- PrinciplesSearchService: Search and discovery (DomainSearchOperations[Entity] protocol)
- PrinciplesAlignmentService: Alignment assessment and motivational intelligence
- PrinciplesLearningService: Learning path integration and framing
- UnifiedRelationshipService (PRINCIPLES_CONFIG): Cross-domain links and integrity calculation
- PrinciplesIntelligenceService: Pure Cypher analytics

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.principle_enums import PrincipleCategory, PrincipleStrength
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.models.principle.principle_request import PrincipleCreateRequest
from core.models.principle.principle_update_intent import PrincipleUpdateIntent
from core.models.type_hints import EntityUID, UserUID
from core.ports.domain_protocols import PrinciplesOperations
from core.services.activity_domain_config import CommonSubServices, create_common_sub_services
from core.services.base_service import BaseService
from core.services.cross_domain import CrossDomainQueryService
from core.services.domain_config import create_activity_domain_config
from core.services.filtered_context import build_filtered_context
from core.services.mixins import KnowledgeIntelligenceDelegationMixin

# Import sub-services and their types
from core.services.principles import (
    PrinciplesAlignmentService,
    PrinciplesLearningService,
    PrinciplesPlanningService,
)
from core.services.principles._embodiment_mixin import _EmbodimentMixin
from core.services.principles._enrichment_mixin import _EnrichmentMixin
from core.services.principles._gravity_mixin import _GravityMixin

# Unified relationship service
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_stats import compute_principle_stats
from core.utils.list_helpers import SortConfig, apply_entity_sort
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_created_at_attr, get_title_or_name_lower
from core.utils.type_converters import normalize_enum_str

if TYPE_CHECKING:
    from datetime import date

    from core.models.context_types import ContextualPrinciple, PracticeOpportunity
    from core.models.pathways.lp_position import LpPosition
    from core.models.principle.principle_types import PrincipleDecision
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.intelligence_protocols import KnowledgeIntelligenceOperations
    from core.ports.query_types import ListContext
    from core.ports.search_protocols import PrinciplesSearchOperations
    from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
    from core.services.insight.insight_store import InsightStore
    from core.services.principles.principle_event_handler_service import (
        PrincipleEventHandlerService,
    )
    from core.services.principles.principles_ai_service import PrinciplesAIService
    from core.services.principles.principles_alignment_service import (
        AlignmentAssessment,
        MotivationalProfile,
    )
    from core.services.principles.principles_core_service import PrinciplesCoreService
    from core.services.principles.principles_intelligence_service import (
        PrinciplesIntelligenceService,
    )
    from core.services.user import UserContext


# ========================================================================
# MODULE-LEVEL HELPERS (filter, sort, stats)
# ========================================================================


def _compute_principle_metadata(_all_principles: list[Any]) -> dict[str, Any]:
    """Compute principle metadata — categories from the PrincipleCategory enum."""
    return {"categories": [c.value for c in PrincipleCategory]}


def _compute_principle_stats(all_principles: list[Any]) -> dict[str, int | float]:
    """Dict projection of PrincipleStats for the cross-domain ListContext contract."""
    s = compute_principle_stats(all_principles)
    return {"total": s.total, "core": s.core, "active": s.active}


def _get_principle_strength_value(p: Any) -> int:
    """Get numeric strength value for sorting/filtering."""
    return PrincipleStrength.from_value(getattr(p, "strength", PrincipleStrength.MODERATE)).rank()


def _apply_principle_filters(
    principles: list[Any],
    category_filter: str = "all",
    strength_filter: str = "all",
    status_filter: str = "all",
) -> list[Any]:
    """Apply status, category, and strength filters to principle list."""
    # Status filter
    match status_filter:
        case "active":
            principles = [
                p
                for p in principles
                if p.status
                not in (EntityStatus.COMPLETED, EntityStatus.ARCHIVED, EntityStatus.CANCELLED)
            ]
        case "completed":
            principles = [p for p in principles if p.status == EntityStatus.COMPLETED]
        case "archived":
            principles = [p for p in principles if p.status == EntityStatus.ARCHIVED]

    # Category filter
    if category_filter != "all":
        principles = [
            p
            for p in principles
            if normalize_enum_str(getattr(p, "category", None)) == category_filter.lower()
        ]

    # Strength filter
    if strength_filter == "core":
        principles = [p for p in principles if _get_principle_strength_value(p) >= 5]
    elif strength_filter == "strong":
        principles = [p for p in principles if _get_principle_strength_value(p) == 4]
    elif strength_filter == "developing":
        principles = [p for p in principles if _get_principle_strength_value(p) in (2, 3)]
    elif strength_filter == "aspirational":
        principles = [p for p in principles if _get_principle_strength_value(p) <= 1]

    return principles


def _by_strength(p: Any) -> int:
    """Sort key for principles by strength (SKUEL012: named function, no lambda)."""
    return _get_principle_strength_value(p)


_PRINCIPLE_SORT_CONFIG: SortConfig = {
    "strength": (_by_strength, True),
    "title": (get_title_or_name_lower, False),
    "created_at": (get_created_at_attr, True),
}


def _apply_principle_sort(principles: list[Any], sort_by: str = "strength") -> list[Any]:
    """Sort principles using declarative config."""
    return apply_entity_sort(principles, sort_by, _PRINCIPLE_SORT_CONFIG, "strength")


class PrinciplesService(
    _EmbodimentMixin,
    _GravityMixin,
    _EnrichmentMixin,
    KnowledgeIntelligenceDelegationMixin,
    BaseService[PrinciplesOperations, Principle, PrincipleUpdateIntent],
):
    """
    Principles service facade with specialized sub-services.

    This facade:
    1. Delegates to 6 specialized sub-services for core operations
    2. Uses explicit delegation methods (~35 methods) for sub-service access
    3. Retains explicit methods for complex operations
    4. Provides clean separation of concerns

    SKUEL Architecture:
    - Uses explicit delegation methods (February 2026)
    - Mixins: _EmbodimentMixin, _GravityMixin, _EnrichmentMixin (April 2026)
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    _config = create_activity_domain_config(
        dto_class=PrincipleDTO,
        model_class=Principle,
        domain_name="principles",
        date_field="created_at",
        completed_statuses=(),  # Principles don't have completion status
        category_field="principle_category",  # Principles store category as 'principle_category'
    )

    # ========================================================================
    # CLASS-LEVEL TYPE ANNOTATIONS
    # ========================================================================
    core: PrinciplesCoreService
    search: PrinciplesSearchOperations  # type: ignore[assignment]  # search service implements callable protocol
    alignment: PrinciplesAlignmentService
    planning: PrinciplesPlanningService
    learning: PrinciplesLearningService
    relationships: UnifiedRelationshipService
    intelligence: PrinciplesIntelligenceService
    event_handler: PrincipleEventHandlerService
    ai: PrinciplesAIService | None

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_principle(self, principle_uid: str) -> Result[Principle]:
        return await self.core.get_principle(principle_uid)

    async def get_user_principles(self, user_uid: UserUID) -> Result[list[Principle]]:
        return await self.core.get_user_principles(user_uid)

    async def get_user_items_in_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
        date_field: str | list[str] | None = None,
    ) -> Result[list[Principle]]:
        return await self.core.get_user_items_in_range(
            user_uid, start_date, end_date, include_completed, date_field
        )

    # Alignment delegations
    async def assess_goal_alignment(
        self, goal_uid: str, user_uid: UserUID
    ) -> Result[AlignmentAssessment]:
        return await self.alignment.assess_goal_alignment(goal_uid, user_uid)

    async def assess_habit_alignment(
        self, habit_uid: str, user_uid: UserUID
    ) -> Result[AlignmentAssessment]:
        return await self.alignment.assess_habit_alignment(habit_uid, user_uid)

    async def get_motivational_profile(self, user_uid: UserUID) -> Result[MotivationalProfile]:
        return await self.alignment.get_motivational_profile(user_uid)

    async def get_embodiment_rates_7d(
        self, principle_uids: list[EntityUID], user_uid: UserUID
    ) -> Result[dict[str, float]]:
        return await self.alignment.get_embodiment_rates_7d(principle_uids, user_uid)

    async def make_principle_based_decision(
        self, user_uid: UserUID, decision_description: str, options: list[str], context: str = ""
    ) -> Result[PrincipleDecision]:
        return await self.alignment.make_principle_based_decision(
            user_uid, decision_description, options, context
        )

    # Learning delegations
    async def frame_principle_practice_with_learning(
        self, principle_uid: str, learning_position: LpPosition
    ) -> Result[dict[str, Any]]:
        return await self.learning.frame_principle_practice_with_learning(
            principle_uid, learning_position
        )

    async def assess_principle_learning_alignment(
        self, principle_uid: str, learning_position: LpPosition
    ) -> Result[dict[str, Any]]:
        return await self.learning.assess_principle_learning_alignment(
            principle_uid, learning_position
        )

    async def suggest_learning_supported_principles(
        self, learning_position: LpPosition, principle_category_filter: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        return await self.learning.suggest_learning_supported_principles(
            learning_position, principle_category_filter
        )

    async def track_principle_learning_development(
        self,
        principle_uid: str,
        learning_position: LpPosition,
        _practice_history: list[dict[str, Any]] | None = None,
    ) -> Result[dict[str, Any]]:
        return await self.learning.track_principle_learning_development(
            principle_uid, learning_position, _practice_history
        )

    # Intelligence delegations
    async def assess_principle_alignment(
        self, principle_uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.assess_principle_alignment(principle_uid, min_confidence)

    async def get_principle_adherence_trends(
        self, principle_uid: str, days: int = 90
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_principle_adherence_trends(principle_uid, days)

    async def get_principle_conflict_analysis(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        return await self.intelligence.get_principle_conflict_analysis(user_uid)

    async def get_quick_principle_impact(self, principle_uid: str) -> Result[dict[str, Any]]:
        return await self.intelligence.get_quick_principle_impact(principle_uid)

    async def batch_analyze_principle_adoption(
        self, principle_uids: list[str]
    ) -> Result[dict[str, dict[str, Any]]]:
        return await self.intelligence.batch_analyze_principle_adoption(principle_uids)

    async def get_choice_guidance_effectiveness(
        self, principle_uid: str, user_uid: UserUID, period_days: int = 90
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_choice_guidance_effectiveness(
            principle_uid, user_uid, period_days
        )

    async def analyze_learning_patterns(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        return await self.intelligence.analyze_learning_patterns(user_uid, timeframe_days)

    async def record_principle_reflection(
        self,
        principle_uid: str,
        user_uid: UserUID,
        alignment_level: str,
        evidence: str,
        trigger_type: str | None = None,
        trigger_uid: str | None = None,
        conflicting_principle_uid: str | None = None,
        reflection_quality_score: float = 0.0,
    ) -> Result[dict[str, Any]]:
        """
        Record a principle reflection and publish domain events.

        Publishes PrincipleReflectionRecorded. If conflicting_principle_uid is
        supplied, also publishes PrincipleConflictRevealed.
        """
        import contextlib

        from core.events import publish_event
        from core.events.principle_events import (
            PrincipleConflictRevealed,
            PrincipleReflectionRecorded,
        )
        from core.models.enums.principle_enums import TriggerType
        from core.utils.uid_generator import UIDGenerator

        trigger: TriggerType | None = None
        if trigger_type:
            with contextlib.suppress(ValueError):
                trigger = TriggerType(trigger_type)

        reflection_uid = str(UIDGenerator.generate_uid("refl"))

        reflection_event = PrincipleReflectionRecorded(
            reflection_uid=reflection_uid,
            principle_uid=principle_uid,
            user_uid=user_uid,
            alignment_level=alignment_level,
            evidence=evidence,
            trigger_type=trigger,
            trigger_uid=trigger_uid,
            reflection_quality_score=reflection_quality_score,
        )
        await publish_event(self.event_bus, reflection_event, self.logger)

        if conflicting_principle_uid:
            conflict_event = PrincipleConflictRevealed(
                reflection_uid=reflection_uid,
                principle_uid=principle_uid,
                conflicting_principle_uid=conflicting_principle_uid,
                user_uid=user_uid,
            )
            await publish_event(self.event_bus, conflict_event, self.logger)

        return Result.ok(
            {
                "reflection_uid": reflection_uid,
                "principle_uid": principle_uid,
                "alignment_level": alignment_level,
                "conflict_revealed": conflicting_principle_uid is not None,
            }
        )

    # Search delegations
    async def get_related_principles(
        self, principle_uid: str, limit: int = 10
    ) -> Result[list[Principle]]:
        return await self.search.get_related_principles(principle_uid, limit)

    async def get_principles_by_category(
        self, category: PrincipleCategory | str, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Principle]]:
        return await self.search.get_by_category(category, user_uid, limit)

    async def get_principles_needing_review(
        self,
        user_uid: UserUID | None = None,
        days_threshold: int = 90,
        limit: int = 20,
    ) -> Result[list[Principle]]:
        return await self.search.get_needing_review(user_uid, days_threshold, limit)

    async def get_upcoming(
        self, days_ahead: int = 30, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Principle]]:
        return await self.search.get_upcoming(days_ahead, user_uid, limit)

    async def get_overdue(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Principle]]:
        return await self.search.get_overdue(user_uid, limit)

    async def get_active(self, user_uid: UserUID, limit: int = 100) -> Result[list[Principle]]:
        return await self.search.get_active(user_uid, limit)

    async def get_principles_for_goal(
        self, goal_uid: str, limit: int = 10
    ) -> Result[list[Principle]]:
        return await self.search.get_for_goal(goal_uid, limit)

    async def get_principles_for_habit(
        self, habit_uid: str, limit: int = 10
    ) -> Result[list[Principle]]:
        return await self.search.get_for_habit(habit_uid, limit)

    # Planning delegations
    async def get_principles_needing_attention_for_user(
        self,
        context: UserContext,
        limit: int = 5,
    ) -> Result[list[ContextualPrinciple]]:
        return await self.planning.get_principles_needing_attention_for_user(context, limit)

    async def get_contextual_principles_for_user(
        self,
        context: UserContext,
        limit: int = 3,
    ) -> Result[list[ContextualPrinciple]]:
        return await self.planning.get_contextual_principles_for_user(context, limit)

    async def get_principle_practice_opportunities_for_user(
        self,
        context: UserContext,
        principle_uid: str | None = None,
        limit: int = 5,
    ) -> Result[list[PracticeOpportunity]]:
        return await self.planning.get_principle_practice_opportunities_for_user(
            context, principle_uid, limit
        )

    async def get_aligned_principles_for_user(
        self,
        context: UserContext,
        limit: int = 5,
    ) -> Result[list[ContextualPrinciple]]:
        """Context-relevant principles to embody today. For the daily plan P8 slot."""
        return await self.planning.get_contextual_principles_for_user(context, limit)

    def __init__(
        self,
        backend: PrinciplesOperations,
        graph_intel: GraphIntelligenceService,
        cross_domain_query: CrossDomainQueryService,
        event_bus: EventBusOperations | None = None,
        insight_store: InsightStore | None = None,
        activity_knowledge_intelligence: KnowledgeIntelligenceOperations | None = None,
        ai_service: PrinciplesAIService | None = None,
    ) -> None:
        """
        Initialize enhanced principles service with specialized sub-services.

        Args:
            backend: Protocol-based backend for principle operations
            graph_intel: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            cross_domain_query: CrossDomainQueryService for graph-derived alignment (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)
            insight_store: InsightStore for persisting event-driven insights (optional)
        """
        super().__init__(backend, "principles")

        self.graph_intel = graph_intel
        self.event_bus = event_bus
        # Optional AI service (ADR-030: AI features are optional)
        self.ai: PrinciplesAIService | None = ai_service
        self.logger = get_logger("skuel.services.principles")  # structlog BoundLogger
        self.alignment_cache: dict[str, AlignmentAssessment] = {}

        # Initialize all common sub-services via factory, including event_handler,
        # learning, and knowledge_intelligence.
        common: CommonSubServices[
            PrinciplesCoreService, PrinciplesSearchOperations, PrinciplesIntelligenceService
        ] = create_common_sub_services(
            domain="principles",
            backend=backend,
            graph_intel=graph_intel,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        )
        assert common.core is not None  # 'core' not in skip
        assert common.search is not None  # 'search' not in skip
        assert common.relationships is not None  # 'relationships' not in skip
        assert common.intelligence is not None  # 'intelligence' not in skip
        self.core = common.core
        self.search = common.search
        self.relationships = common.relationships
        self.intelligence = common.intelligence

        # Domain-specific sub-services (not common to all facades)
        self.alignment = PrinciplesAlignmentService(
            backend=backend,
            cross_domain_query=cross_domain_query,
            event_bus=event_bus,
        )
        self.learning: PrinciplesLearningService = common.learning

        # Planning sub-service (January 2026 - context-aware recommendations)
        self.planning = PrinciplesPlanningService(
            backend=backend,
            relationship_service=self.relationships,
        )

        # Event handler sub-service from factory
        self.event_handler: PrincipleEventHandlerService = common.event_handler

        # Knowledge intelligence (shared singleton — domain-agnostic)
        self.knowledge_intelligence = common.knowledge_intelligence  # always passed by bootstrap

        self.logger.info(
            "PrinciplesService facade initialized with 8 sub-services: "
            "core, search, alignment, learning, relationships, intelligence, "
            "planning, event_handler, knowledge_intelligence"
        )

    # ========================================================================
    # CORE CRUD OPERATIONS - Delegate to PrinciplesCoreService
    # ========================================================================

    async def create_principle(
        self, request: PrincipleCreateRequest, user_uid: UserUID
    ) -> Result[Principle]:
        """Create a principle from a validated request."""
        return await self.core.create_principle(request, user_uid)

    # Update path (ADR-066 typed update contract) ----------------------------
    async def update_principle(
        self, principle_uid: str, intent: PrincipleUpdateIntent
    ) -> Result[Principle]:
        """THE Principles update path (ADR-066): route the typed intent through the core
        service, which writes only the set fields at the single ``backend.update`` seam and
        fires ``PrincipleUpdated`` (and ``PrincipleStrengthChanged`` on a strength change).
        Principles carry no edge fields, so there is nothing to split off."""
        return await self.core.update_principle(principle_uid, intent)

    async def update(self, uid: str, updates: PrincipleUpdateIntent) -> Result[Principle]:
        """Override the inherited CRUD update (generated JSON route, no ownership check).

        Routes the typed intent through the one event-firing update path
        (``PrinciplesCoreService.update_principle``) — the inherited base ``update`` on the
        facade would skip the core's events."""
        return await self.core.update_principle(uid, updates)

    async def update_for_user(
        self, uid: str, updates: PrincipleUpdateIntent, user_uid: UserUID
    ) -> Result[Principle]:
        """Override the inherited ownership-verified CRUD update (generated JSON route).

        Verifies ownership BEFORE any mutation, then routes through the one event-firing
        update path (``PrinciplesCoreService.update_principle``)."""
        ownership = await self.verify_ownership(uid, user_uid)
        if ownership.is_error:
            return ownership
        return await self.core.update_principle(uid, updates)

    # ========================================================================
    # HIERARCHY DELEGATIONS
    # ========================================================================

    async def get_subprinciples(self, parent_uid: str, depth: int = 1) -> Result[list[Principle]]:
        return await self.core.get_subentities(parent_uid, depth)

    async def get_parent_principle(self, subprinciple_uid: str) -> Result[Principle | None]:
        return await self.core.get_parent_entity(subprinciple_uid)

    async def get_principle_hierarchy(self, principle_uid: str) -> Result[dict[str, Any]]:
        return await self.core.get_entity_hierarchy(principle_uid)

    async def create_subprinciple_relationship(
        self, parent_uid: str, child_uid: str
    ) -> Result[bool]:
        return await self.core.create_subprinciple_relationship(parent_uid, child_uid)

    async def remove_subprinciple_relationship(
        self, parent_uid: str, child_uid: str
    ) -> Result[bool]:
        return await self.core.remove_subprinciple_relationship(parent_uid, child_uid)

    # ========================================================================
    # QUERY LAYER
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: UserUID,
        category_filter: str = "all",
        strength_filter: str = "all",
        sort_by: str = "strength",
        status_filter: str = "all",
    ) -> Result[ListContext]:
        """Get filtered and sorted principles with pre-filter stats in a single query."""

        async def fetch_all() -> Result[list[Any]]:
            return await self.core.get_for_user_filtered(user_uid)

        def apply_filters(all_principles: list[Any]) -> list[Any]:
            return _apply_principle_filters(
                all_principles, category_filter, strength_filter, status_filter
            )

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_principle_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_principle_sort,
            sort_by=sort_by,
            compute_metadata=_compute_principle_metadata,
        )
