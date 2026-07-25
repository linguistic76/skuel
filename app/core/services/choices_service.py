"""
Enhanced Choices Service - Facade Pattern
==========================================

Choices service facade that delegates to specialized sub-services.

Sub-Services:
- ChoicesCoreService: CRUD operations
- ChoicesSearchService: Search and discovery (DomainSearchOperations[Choice] protocol)
- ChoicesLearningService: Learning path guidance and integration
- UnifiedRelationshipService (CHOICES_CONFIG): Cross-domain links and semantic connections
- ChoicesIntelligenceService: Pure Cypher analytics + decision pattern analysis

Facade Mixin:
- _OptionManagementMixin: Option CRUD and decision-making
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.choice.choice import Choice
from core.models.choice.choice_dto import ChoiceDTO
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.enums import EntityStatus, Priority
from core.models.type_hints import UserUID
from core.ports.domain_protocols import ChoicesOperations
from core.services.activity_domain_config import CommonSubServices, create_common_sub_services
from core.services.base_service import BaseService

# Import sub-services
from core.services.choices import ChoicesLearningService
from core.services.choices._option_management_mixin import _OptionManagementMixin
from core.services.choices.choice_event_handler_service import ChoiceEventHandlerService
from core.services.domain_config import create_activity_domain_config
from core.services.filtered_context import build_filtered_context

# Unified relationship service
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.mixins import KnowledgeIntelligenceDelegationMixin
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_stats import compute_choice_stats
from core.utils.list_helpers import FilterConfig, SortConfig, apply_entity_filter, apply_entity_sort
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import (
    get_created_at_attr,
    get_decision_deadline,
)
from core.utils.type_converters import get_enum_attr_str

if TYPE_CHECKING:
    from datetime import date

    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.choice.choice_request import ChoiceCreateRequest
    from core.models.context_types import ContextualChoice
    from core.models.enums import Domain
    from core.models.pathways.lp_position import LpPosition
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.intelligence_protocols import KnowledgeIntelligenceOperations
    from core.ports.query_types import ListContext
    from core.ports.search_protocols import ChoicesSearchOperations
    from core.services.choices.choices_ai_service import ChoicesAIService
    from core.services.choices.choices_core_service import ChoicesCoreService
    from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
    from core.services.choices.choices_types import ChoiceImpactAnalysis, DecisionIntelligence
    from core.services.cross_domain import CrossDomainQueryService
    from core.services.user import UserContext


def _get_choice_enum_value(obj: Any, attr: str, default: str = "") -> str:
    """Extract value from attribute (handles both enum and string)."""
    return get_enum_attr_str(obj, attr, default)


def _get_choice_priority(c: Any) -> str:
    """Extract priority string for sort key (SKUEL012: named function, no lambda)."""
    return get_enum_attr_str(c, "priority", "medium")


def _compute_choice_stats(all_choices: list[Any]) -> dict[str, int | float]:
    """Dict projection of ChoiceStats for the cross-domain ListContext contract."""
    s = compute_choice_stats(all_choices)
    return {
        "total": s.total,
        "active": s.active,
        "pending": s.pending,
        "decided": s.decided,
    }


def _is_choice_pending(c: Any) -> bool:
    """Filter predicate: choice is pending."""
    return _get_choice_enum_value(c, "status") == "pending"


def _is_choice_decided(c: Any) -> bool:
    """Filter predicate: choice is decided."""
    return _get_choice_enum_value(c, "status") == "decided"


def _is_choice_implemented(c: Any) -> bool:
    """Filter predicate: choice is implemented."""
    return _get_choice_enum_value(c, "status") == "implemented"


_CHOICE_FILTER_CONFIG: FilterConfig = {
    "pending": _is_choice_pending,
    "decided": _is_choice_decided,
    "implemented": _is_choice_implemented,
}


def _get_choice_priority_order(c: Any) -> int:
    """Sort key for priority (CRITICAL first = 0, LOW last = 3)."""
    return Priority.from_value(_get_choice_priority(c)).sort_order()


_CHOICE_SORT_CONFIG: SortConfig = {
    "deadline": (get_decision_deadline, False),
    "priority": (_get_choice_priority_order, False),
    "created_at": (get_created_at_attr, True),
}


def _apply_choice_sort(choices: list[Any], sort_by: str = "deadline") -> list[Any]:
    """Sort choices using declarative config."""
    return apply_entity_sort(choices, sort_by, _CHOICE_SORT_CONFIG, "deadline")


class ChoicesService(
    _OptionManagementMixin,
    KnowledgeIntelligenceDelegationMixin,
    BaseService["ChoicesOperations", Choice, ChoiceUpdateIntent],
):
    """
    Choices service facade with specialized sub-services.

    This facade:
    1. Delegates to 7 specialized sub-services for core operations
    2. Uses explicit delegation methods (~26 methods) for sub-service access
    3. Facade mixins group related explicit methods by concern
    4. Provides clean separation of concerns

    Delegations (explicit methods):
    - Core: get_choice, get_user_choices, get_user_items_in_range
    - Learning: create_choice_with_learning_guidance, suggest_learning_aligned_choices, etc.
    - Search: get_pending_choices, get_upcoming, get_overdue, get_choices_needing_decision, etc.
    - Intelligence: get_decision_intelligence, get_decision_patterns, etc.

    Facade Mixin:
    - _OptionManagementMixin: add_option, update_option, remove_option, make_decision

    SKUEL Architecture:
    - Uses explicit delegation methods (February 2026)
    - Facade mixins decomposition (April 2026)
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=ChoiceDTO,
        model_class=Choice,
        domain_name="choices",
        date_field="decision_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    # ========================================================================
    # CLASS-LEVEL TYPE ANNOTATIONS
    # ========================================================================
    core: ChoicesCoreService
    search: ChoicesSearchOperations  # type: ignore[assignment]  # search service implements callable protocol
    learning: ChoicesLearningService
    relationships: UnifiedRelationshipService
    intelligence: ChoicesIntelligenceService
    event_handler: ChoiceEventHandlerService
    ai: ChoicesAIService | None

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_choice(self, choice_uid: str) -> Result[Choice]:
        return await self.core.get_choice(choice_uid)

    async def get_user_choices(self, user_uid: UserUID) -> Result[list[Choice]]:
        return await self.core.get_user_choices(user_uid)

    async def get_user_items_in_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
    ) -> Result[list[Choice]]:
        return await self.core.get_user_items_in_range(
            user_uid, start_date, end_date, include_completed
        )

    # Learning delegations
    async def create_choice_with_learning_guidance(
        self,
        choice_request: ChoiceCreateRequest,
        user_uid: UserUID,
        learning_position: LpPosition | None = None,
    ) -> Result[Choice]:
        return await self.learning.create_choice_with_learning_guidance(
            choice_request, user_uid, learning_position
        )

    async def get_learning_informed_guidance(
        self,
        choice_description: str,
        learning_position: LpPosition,
        choice_options: list[str] | None = None,
    ) -> Result[dict[str, Any]]:
        return await self.learning.get_learning_informed_guidance(
            choice_description, learning_position, choice_options
        )

    async def track_choice_learning_outcomes(
        self,
        choice_uid: str,
        learning_position: LpPosition,
        _outcome_data: dict[str, Any] | None = None,
    ) -> Result[dict[str, Any]]:
        return await self.learning.track_choice_learning_outcomes(
            choice_uid, learning_position, _outcome_data
        )

    async def suggest_learning_aligned_choices(
        self,
        learning_position: LpPosition,
        choice_domain: Domain | None = None,
        urgency_level: Priority | None = None,
    ) -> Result[list[dict[str, Any]]]:
        return await self.learning.suggest_learning_aligned_choices(
            learning_position, choice_domain, urgency_level
        )

    # Intelligence delegations
    async def get_decision_intelligence(
        self, choice_uid: str, min_confidence: float = 0.7, depth: int = 2
    ) -> Result[DecisionIntelligence]:
        return await self.intelligence.get_decision_intelligence(choice_uid, min_confidence, depth)

    async def analyze_choice_impact(
        self, choice_uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[ChoiceImpactAnalysis]:
        return await self.intelligence.analyze_choice_impact(choice_uid, depth, min_confidence)

    async def get_decision_patterns(
        self, user_uid: UserUID, days: int = 90
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_decision_patterns(user_uid, days)

    async def get_choice_quality_correlations(
        self, user_uid: UserUID, days: int = 90
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_choice_quality_correlations(user_uid, days)

    async def get_domain_decision_patterns(
        self, user_uid: UserUID, days: int = 90
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_domain_decision_patterns(user_uid, days)

    async def analyze_learning_patterns(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        return await self.intelligence.analyze_learning_patterns(user_uid, timeframe_days)

    # Search delegations
    async def get_pending_choices(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[Choice]]:
        return await self.search.get_pending(user_uid, limit)

    async def get_upcoming(
        self, days_ahead: int = 7, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Choice]]:
        return await self.search.get_upcoming(days_ahead, user_uid, limit)

    async def get_overdue(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Choice]]:
        return await self.search.get_overdue(user_uid, limit)

    async def get_active(self, user_uid: UserUID, limit: int = 100) -> Result[list[Choice]]:
        return await self.search.get_active(user_uid, limit)

    async def get_choices_needing_decision(
        self, user_uid: UserUID, deadline_days: int = 7
    ) -> Result[list[Choice]]:
        return await self.search.get_needing_decision(user_uid, deadline_days)

    async def get_pending_decisions_for_user(
        self,
        context: UserContext,
        limit: int = 5,
    ) -> Result[list[ContextualChoice]]:
        """Pending choices with deadline-based priority. For the daily plan P7 slot."""
        from datetime import datetime

        from core.models.context_types import ContextualChoice

        result = await self.get_pending_choices(context.user_uid, limit)
        if result.is_error:
            return Result.fail(result)
        now = datetime.now()
        contextual: list[ContextualChoice] = []
        for choice in result.value or []:
            deadline = choice.decision_deadline
            if deadline is not None:
                days_until = (deadline.replace(tzinfo=None) - now).days
                if days_until <= 2:
                    priority_level = "urgent"
                elif days_until <= 7:
                    priority_level = "high"
                else:
                    priority_level = "medium"
            else:
                priority_level = "medium"
            contextual.append(
                ContextualChoice.from_entity_and_context(
                    uid=choice.uid,
                    title=choice.title,
                    context=context,
                    priority_level=priority_level,
                )
            )
        return Result.ok(contextual)

    def __init__(
        self,
        backend: ChoicesOperations,
        graph_intel: GraphIntelligenceService,
        cross_domain_query: CrossDomainQueryService,
        event_bus: EventBusOperations | None = None,
        insight_store: Any = None,
        activity_knowledge_intelligence: KnowledgeIntelligenceOperations | None = None,
        ai_service: ChoicesAIService | None = None,
    ) -> None:
        """
        Initialize enhanced choices service with specialized sub-services.

        Args:
            backend: Protocol-based backend for choice operations
            graph_intel: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            cross_domain_query: CrossDomainQueryService for cross-domain reads (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)
            insight_store: InsightStore for persisting event-driven insights (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Choice operations trigger domain events which invalidate context.

        Migration Note (v2.1.0 - December 2025):
            Made graph_intel REQUIRED - relationship service needs it.
            Fail-fast at construction, not at method call.
        """
        super().__init__(backend, "choices")

        self.graph_intel = graph_intel
        self.cross_domain_query = cross_domain_query
        self.event_bus = event_bus
        # Optional AI service (ADR-030: AI features are optional)
        self.ai: ChoicesAIService | None = ai_service
        self.logger = get_logger("skuel.services.choices")  # type: ignore[assignment]  # structlog BoundLogger

        # Initialize core/search/relationships/event_handler/learning/
        # knowledge_intelligence via factory. Intelligence is built manually
        # because ChoicesIntelligenceService takes cross_domain_query for the
        # ZPD behavioral-signals bridge.
        common: CommonSubServices[
            ChoicesCoreService, ChoicesSearchOperations, ChoicesIntelligenceService
        ] = create_common_sub_services(
            domain="choices",
            backend=backend,
            graph_intel=graph_intel,
            event_bus=event_bus,
            insight_store=insight_store,
            skip={"intelligence"},
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        )
        assert common.core is not None  # 'core' not in skip
        assert common.search is not None  # 'search' not in skip
        assert common.relationships is not None  # 'relationships' not in skip
        self.core = common.core
        self.search = common.search
        self.relationships = common.relationships

        from core.services.choices.choices_intelligence_service import (
            ChoicesIntelligenceService as _ChoicesIntelligenceService,
        )

        self.intelligence: ChoicesIntelligenceService = _ChoicesIntelligenceService(
            backend=backend,
            cross_domain_query=cross_domain_query,
            relationship_service=self.relationships,
            graph_intel=graph_intel,
            insight_store=insight_store,
        )

        # Domain-specific sub-services from factory
        self.learning: ChoicesLearningService = common.learning
        self.event_handler: ChoiceEventHandlerService = common.event_handler

        # Knowledge intelligence (shared singleton — domain-agnostic)
        self.knowledge_intelligence = common.knowledge_intelligence  # always passed by bootstrap

        self.logger.info(
            "ChoicesService facade initialized with 7 sub-services: "
            "core, search, learning, relationships, intelligence, "
            "event_handler, knowledge_intelligence"
        )

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # ========================================================================
    # CORE CRUD OPERATIONS - Delegate to ChoicesCoreService
    # ========================================================================
    # Note: Simple delegations (get_choice, get_user_choices, get_user_items_in_range)
    # delegated via explicit methods below.

    async def create_choice(
        self, choice_request: ChoiceCreateRequest, user_uid: UserUID
    ) -> Result[Choice]:
        """Create a basic choice.

        Args:
            choice_request: Choice creation request
            user_uid: User UID (REQUIRED - fail-fast philosophy)
        """
        return await self.core.create_choice(choice_request, user_uid)

    # Update path (ADR-066 typed update contract) ----------------------------
    async def update_choice(self, choice_uid: str, intent: ChoiceUpdateIntent) -> Result[Choice]:
        """THE Choices update path (ADR-066): route the typed intent through the core
        service, which validates (decision immutability, option-count floor), writes only
        the set fields, and fires ChoiceUpdated. Choices carry no edge fields, so there is
        nothing to split off."""
        return await self.core.update_choice(choice_uid, intent)

    async def update(self, uid: str, updates: ChoiceUpdateIntent) -> Result[Choice]:
        """Override the inherited CRUD update (generated JSON route, no ownership check).

        Routes the typed intent through the one validated, event-firing update path
        (``ChoicesCoreService.update_choice``) — the inherited base ``update`` on the facade
        would skip the core's validation and events."""
        return await self.core.update_choice(uid, updates)

    async def update_for_user(
        self, uid: str, updates: ChoiceUpdateIntent, user_uid: UserUID
    ) -> Result[Choice]:
        """Override the inherited ownership-verified CRUD update (generated JSON route).

        Verifies ownership BEFORE any mutation, then routes through the one validated,
        event-firing update path (``ChoicesCoreService.update_choice``)."""
        ownership = await self.verify_ownership(uid, user_uid)
        if ownership.is_error:
            return ownership
        return await self.core.update_choice(uid, updates)

    async def delete_choice(self, choice_uid: str) -> Result[bool]:
        """Delete a choice."""
        return await self.core.delete_choice(choice_uid)

    async def find_choices(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[Choice]]:
        """Find choices with filters and pagination."""
        return await self.core.find_choices(filters, limit, offset, order_by, order_desc)

    async def count_choices(self, filters: dict[str, Any] | None = None) -> Result[int]:
        """Count choices matching filters."""
        return await self.core.count_choices(filters)

    # Note: Option management methods (add_option, update_option, remove_option, make_decision)
    # provided by _OptionManagementMixin.

    # ========================================================================
    # GRAPH RELATIONSHIPS
    # ========================================================================

    async def link_choice_to_goal(
        self, choice_uid: str, goal_uid: str, contribution_score: float = 0.5
    ) -> Result[bool]:
        """Link choice to goal it affects/advances (``AFFECTS_GOAL``)."""
        return await self.relationships.create_relationship(
            "goals", choice_uid, goal_uid, {"contribution_score": contribution_score}
        )

    async def link_choice_to_habit(
        self, choice_uid: str, habit_uid: str, reinforcement_strength: float = 0.5
    ) -> Result[bool]:
        """Link choice to habit it reinforces/weakens (``IMPACTS_HABIT``).

        Uses the ``impacted_habits`` config key — Choices has no ``"habits"`` key
        (that earlier value silently failed config validation in create_relationship).
        """
        properties = {"reinforcement_strength": reinforcement_strength}
        return await self.relationships.create_relationship(
            "impacted_habits", choice_uid, habit_uid, properties
        )

    async def link_choice_to_principle(
        self, choice_uid: str, principle_uid: str, alignment_score: float = 0.5
    ) -> Result[bool]:
        """Link choice to principle it is informed by (``INFORMED_BY_PRINCIPLE``)."""
        return await self.relationships.create_relationship(
            "principles", choice_uid, principle_uid, {"alignment_score": alignment_score}
        )

    async def create_semantic_choice_relationship(
        self,
        choice_uid: str,
        related_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create semantic relationship for choice (to principle, knowledge, or goal)."""
        return await self.relationships.create_semantic_relationship(
            choice_uid, related_uid, semantic_type, confidence, notes
        )

    async def find_choices_aligned_with_principle(
        self, principle_uid: str, min_confidence: float = 0.8
    ) -> Result[list[Choice]]:
        """Find choices aligned with specific principle."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=principle_uid, min_confidence=min_confidence, direction="incoming"
        )

    # ========================================================================
    # HIERARCHY DELEGATIONS
    # ========================================================================

    async def get_subchoices(self, parent_uid: str, depth: int = 1) -> Result[list[Choice]]:
        return await self.core.get_subentities(parent_uid, depth)

    async def get_parent_choice(self, subchoice_uid: str) -> Result[Choice | None]:
        return await self.core.get_parent_entity(subchoice_uid)

    async def get_choice_hierarchy(self, choice_uid: str) -> Result[dict[str, Any]]:
        return await self.core.get_entity_hierarchy(choice_uid)

    async def create_subchoice_relationship(self, parent_uid: str, child_uid: str) -> Result[bool]:
        return await self.core.create_subchoice_relationship(parent_uid, child_uid)

    async def remove_subchoice_relationship(self, parent_uid: str, child_uid: str) -> Result[bool]:
        return await self.core.remove_subchoice_relationship(parent_uid, child_uid)

    # ========================================================================
    # QUERY LAYER
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: UserUID,
        status_filter: str = "pending",
        sort_by: str = "deadline",
    ) -> Result[ListContext]:
        """Get filtered and sorted choices with pre-filter stats in a single query."""

        async def fetch_all() -> Result[list[Any]]:
            return await self.core.get_for_user_filtered(user_uid, "all")

        def apply_filters(all_choices: list[Any]) -> list[Any]:
            return apply_entity_filter(all_choices, status_filter, _CHOICE_FILTER_CONFIG)

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_choice_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_choice_sort,
            sort_by=sort_by,
        )

    # Note: Intelligence delegations (get_decision_intelligence,
    # analyze_choice_impact, get_decision_patterns, etc.) and Search delegations
    # (get_pending_choices, get_upcoming, get_overdue, etc.) delegated
    # via explicit methods above.
