"""
Enhanced Principles Service - Facade Pattern
=============================================

Principles service facade that delegates to specialized sub-services.
Uses Entity model with EntityType.PRINCIPLE discrimination.

Sub-Services:
- PrinciplesCoreService: CRUD operations for principles
- PrinciplesSearchService: Search and discovery (DomainSearchOperations[Entity] protocol)
- PrinciplesAlignmentService: Alignment assessment and motivational intelligence
- PrinciplesLearningService: Learning path integration and framing
- UnifiedRelationshipService (PRINCIPLES_CONFIG): Cross-domain links and integrity calculation
- PrinciplesIntelligenceService: Pure Cypher analytics
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.principle_enums import PrincipleCategory, PrincipleStrength
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.ports.domain_protocols import (
    GoalsOperations,
    HabitsOperations,
    PrinciplesOperations,
)
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config

# Import sub-services and their types
from core.services.principles import (
    PrinciplesAlignmentService,
    PrinciplesLearningService,
    PrinciplesPlanningService,
    PrinciplesReflectionService,
)
from core.services.principles.principles_ai_service import PrinciplesAIService

# Unified relationship service (replaces PrinciplesRelationshipService)
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_domain_config import CommonSubServices, create_common_sub_services
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_created_at_attr, get_title_or_name_lower
from core.utils.type_converters import normalize_enum_str

if TYPE_CHECKING:
    from core.ports.query_types import ListContext
    from core.ports.search_protocols import PrinciplesSearchOperations
    from core.services.principles.principles_alignment_service import (
        AlignmentAssessment,
    )
    from core.services.principles.principles_intelligence_service import (
        PrinciplesIntelligenceService,
    )


# NOTE: AlignmentAssessment and MotivationalProfile are now imported from
# principles_alignment_service to avoid type duplication issues


def _by_assessed_date(item: dict[str, Any]) -> str:
    """Sort key for alignment history by assessed_date (SKUEL012: no lambdas)."""
    return item.get("assessed_date", "")


_PRINCIPLE_STRENGTH_ORDER: dict[PrincipleStrength, int] = {
    PrincipleStrength.CORE: 5,
    PrincipleStrength.STRONG: 4,
    PrincipleStrength.MODERATE: 3,
    PrincipleStrength.DEVELOPING: 2,
    PrincipleStrength.EXPLORING: 1,
}


def _get_principle_strength_value(p: Any) -> int:
    """Get numeric strength value for sorting/filtering."""
    s = getattr(p, "strength", PrincipleStrength.MODERATE)
    if isinstance(s, PrincipleStrength):
        return _PRINCIPLE_STRENGTH_ORDER.get(s, 3)
    if isinstance(s, str):
        s_upper = s.upper()
        for enum_val in PrincipleStrength:
            if enum_val.value == s or enum_val.name == s_upper:
                return _PRINCIPLE_STRENGTH_ORDER.get(enum_val, 3)
    return 3


def _apply_principle_filters(
    principles: list[Any],
    category_filter: str = "all",
    strength_filter: str = "all",
) -> list[Any]:
    """Apply category and strength filters to principle list."""
    if category_filter != "all":
        principles = [
            p
            for p in principles
            if normalize_enum_str(getattr(p, "category", None)) == category_filter.lower()
        ]

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


def _apply_principle_sort(principles: list[Any], sort_by: str = "strength") -> list[Any]:
    """Sort principles by specified field."""
    if sort_by == "strength":
        return sorted(principles, key=_by_strength, reverse=True)
    elif sort_by == "title":
        return sorted(principles, key=get_title_or_name_lower)
    elif sort_by == "created_at":
        return sorted(principles, key=get_created_at_attr, reverse=True)
    return sorted(principles, key=_by_strength, reverse=True)


class PrinciplesService(BaseService[PrinciplesOperations, Principle]):
    """
    Principles service facade with specialized sub-services.

    This facade:
    1. Delegates to 6 specialized sub-services for core operations
    2. Uses explicit delegation methods (~35 methods) for sub-service access
    3. Retains explicit methods for complex operations
    4. Provides clean separation of concerns

    Delegations (explicit methods):
    - Core: get_principle, get_user_principles, get_user_items_in_range
    - Alignment: assess_goal_alignment, assess_habit_alignment, get_motivational_profile, etc.
    - Learning: frame_principle_practice_with_learning, assess_principle_learning_alignment, etc.
    - Intelligence: get_principle_with_context, assess_principle_alignment, etc.
    - Search: list_principle_categories, get_principles_by_status, etc.

    Explicit Methods (custom logic):
    - create_principle (many parameters)
    - Relationship methods: create_user_principle_relationship, get_user_principle_portfolio
    - search_principles (has post-filtering logic)
    - Expression CRUD: create_principle_expression, get_principle_expressions
    - Alignment history: get_principle_alignment_history
    - Principle links: create_principle_link, get_principle_links

    SKUEL Architecture:
    - Uses explicit delegation methods (February 2026)
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=PrincipleDTO,
        model_class=Principle,
        domain_name="principles",
        date_field="created_at",
        completed_statuses=(),  # Principles don't have completion status
    )

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_principle(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_principle(*args, **kwargs)

    async def get_user_principles(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_user_principles(*args, **kwargs)

    async def get_user_items_in_range(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_user_items_in_range(*args, **kwargs)

    # Alignment delegations
    async def assess_goal_alignment(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.alignment.assess_goal_alignment(*args, **kwargs)

    async def assess_habit_alignment(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.alignment.assess_habit_alignment(*args, **kwargs)

    async def get_motivational_profile(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.alignment.get_motivational_profile(*args, **kwargs)

    async def make_principle_based_decision(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.alignment.make_principle_based_decision(*args, **kwargs)

    # Learning delegations
    async def frame_principle_practice_with_learning(
        self, *args: Any, **kwargs: Any
    ) -> Result[Any]:
        return await self.learning.frame_principle_practice_with_learning(*args, **kwargs)

    async def assess_principle_learning_alignment(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.assess_principle_learning_alignment(*args, **kwargs)

    async def suggest_learning_supported_principles(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.suggest_learning_supported_principles(*args, **kwargs)

    async def track_principle_learning_development(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.track_principle_learning_development(*args, **kwargs)

    # Relationship delegations
    async def get_principle_cross_domain_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.relationships.get_cross_domain_context(*args, **kwargs)

    # Intelligence delegations
    async def get_principle_with_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_principle_with_context(*args, **kwargs)

    async def assess_principle_alignment(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.assess_principle_alignment(*args, **kwargs)

    async def get_principle_adherence_trends(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_principle_adherence_trends(*args, **kwargs)

    async def get_principle_conflict_analysis(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_principle_conflict_analysis(*args, **kwargs)

    # Search delegations
    async def list_principle_categories(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.list_user_categories(*args, **kwargs)

    async def list_all_principle_categories(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.list_all_categories(*args, **kwargs)

    async def get_related_principles(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_related_principles(*args, **kwargs)

    async def get_principles_by_status(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_by_status(*args, **kwargs)

    async def get_principles_by_strength(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_by_strength(*args, **kwargs)

    async def get_principles_by_category(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_by_category(*args, **kwargs)

    async def get_principles_needing_review(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_needing_review(*args, **kwargs)

    async def get_principles_for_goal(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_for_goal(*args, **kwargs)

    async def get_principles_for_choice(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_for_choice(*args, **kwargs)

    # Reflection delegations
    async def save_reflection(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.reflection.save_reflection(*args, **kwargs)

    async def get_reflections_for_principle(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.reflection.get_reflections_for_principle(*args, **kwargs)

    async def get_recent_reflections(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.reflection.get_recent_reflections(*args, **kwargs)

    async def get_alignment_trend(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.reflection.calculate_alignment_trend(*args, **kwargs)

    async def get_cross_domain_insights(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.reflection.get_cross_domain_insights(*args, **kwargs)

    async def get_reflection_frequency(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.reflection.get_reflection_frequency(*args, **kwargs)

    async def get_conflict_analysis(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.reflection.get_conflict_analysis(*args, **kwargs)

    # Planning delegations
    async def get_principles_needing_attention_for_user(
        self, *args: Any, **kwargs: Any
    ) -> Result[Any]:
        return await self.planning.get_principles_needing_attention_for_user(*args, **kwargs)

    async def get_contextual_principles_for_user(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.planning.get_contextual_principles_for_user(*args, **kwargs)

    async def get_principle_practice_opportunities_for_user(
        self, *args: Any, **kwargs: Any
    ) -> Result[Any]:
        return await self.planning.get_principle_practice_opportunities_for_user(*args, **kwargs)

    def __init__(
        self,
        backend: PrinciplesOperations,
        graph_intelligence_service: Any,
        goals_backend: GoalsOperations | None = None,
        habits_backend: HabitsOperations | None = None,
        reflection_backend: Any | None = None,
        event_bus: Any = None,
        ai_service: PrinciplesAIService | None = None,
        insight_store: Any = None,
    ) -> None:
        """
        Initialize enhanced principles service with specialized sub-services.

        Args:
            backend: Protocol-based backend for principle operations
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            goals_backend: Backend for goal queries (cross-domain alignment)
            habits_backend: Backend for habit queries (cross-domain alignment)
            reflection_backend: Backend for reflection persistence (optional, uses backend if not provided)
            event_bus: Event bus for publishing domain events (optional)
            insight_store: InsightStore for persisting event-driven insights (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Principle events trigger user_service.invalidate_context() in bootstrap.

        Migration Note (v3.2.0 - December 2025):
            Made graph_intelligence_service REQUIRED - relationship service needs it.
            Fail-fast at construction, not at method call.
        """
        super().__init__(backend, "principles")

        self.graph_intel = graph_intelligence_service
        self.event_bus = event_bus
        self.ai: PrinciplesAIService | None = ai_service
        self.logger = get_logger("skuel.services.principles")
        self.alignment_cache: dict[str, AlignmentAssessment] = {}

        # Initialize 4 common sub-services via factory (eliminates ~30 lines of repetitive code)
        common: CommonSubServices[PrinciplesIntelligenceService] = create_common_sub_services(
            domain="principles",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
            insight_store=insight_store,
        )
        self.core = common.core
        self.search: PrinciplesSearchOperations = common.search
        self.relationships: UnifiedRelationshipService = common.relationships
        self.intelligence: PrinciplesIntelligenceService = common.intelligence

        # Domain-specific sub-services (not common to all facades)
        self.alignment = PrinciplesAlignmentService(
            backend=backend,
            goals_backend=goals_backend,
            habits_backend=habits_backend,
            event_bus=event_bus,
        )
        self.learning = PrinciplesLearningService(backend=backend)

        # Reflection sub-service (January 2026 - graph-connected reflections)
        self.reflection = PrinciplesReflectionService(
            backend=reflection_backend or backend,
            event_bus=event_bus,
        )

        # Planning sub-service (January 2026 - context-aware recommendations)
        self.planning = PrinciplesPlanningService(
            backend=backend,
            relationship_service=self.relationships,
        )

        self.logger.info(
            "PrinciplesService facade initialized with 8 sub-services: "
            "core, search, alignment, learning, relationships, intelligence, reflection, planning"
        )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Principle entities."""
        return "Principle"

    # ========================================================================
    # CORE CRUD OPERATIONS - Delegate to PrinciplesCoreService
    # ========================================================================
    # Note: Simple delegations (get_principle, get_user_principles, get_user_items_in_range,
    # alignment assessment, motivational intelligence, learning path integration)
    # delegated via explicit methods below.

    async def create_principle(
        self,
        label: str,
        description: str,
        category: PrincipleCategory,
        why_matters: str,
        **kwargs: Any,
    ) -> Result[Principle]:
        """Create a new principle."""
        return await self.core.create_principle(label, description, category, why_matters, **kwargs)

    # ========================================================================
    # CROSS-DOMAIN RELATIONSHIPS - Delegate to UnifiedRelationshipService
    # ========================================================================

    async def create_user_principle_relationship(
        self,
        user_uid: str,
        principle_uid: str,
        strength: str = "core",
        adoption_date: str | None = None,
    ) -> Result[bool]:
        """Create User→Principle relationship in graph."""
        properties: dict[str, str] = {"strength": strength}
        if adoption_date:
            properties["adoption_date"] = adoption_date
        return await self.relationships.create_user_relationship(
            user_uid, principle_uid, properties if properties else None
        )

    async def link_principle_to_knowledge(
        self, principle_uid: str, knowledge_uid: str, relevance: str = "fundamental"
    ) -> Result[bool]:
        """Link principle to knowledge it's based on."""
        return await self.relationships.link_to_knowledge(
            principle_uid, knowledge_uid, relevance=relevance
        )

    # Note: get_principle_cross_domain_context delegated via explicit methods below.

    async def get_user_principle_portfolio(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get user's complete principle portfolio with integrity analysis."""
        # Get all principles for the user
        principles_result = await self.backend.list(filters={"user_uid": user_uid}, limit=100)
        if principles_result.is_error:
            return Result.fail(principles_result)
        # list() returns tuple[list[Principle], int]
        principles, total = principles_result.value
        return Result.ok(
            {
                "user_uid": user_uid,
                "principles": principles,
                "count": len(principles),
            }
        )

    async def calculate_principle_integrity(
        self, user_uid: str, principle_uid: str
    ) -> Result[dict[str, Any]]:
        """Calculate how well user's actions align with stated principle."""
        # Get the principle and its cross-domain context
        context_result = await self.relationships.get_cross_domain_context(principle_uid)
        if context_result.is_error:
            return context_result
        return Result.ok(
            {
                "principle_uid": principle_uid,
                "user_uid": user_uid,
                "context": context_result.value,
                "integrity_score": 0.5,  # Placeholder - would need actual calculation
            }
        )

    # ========================================================================
    # SEARCH AND FILTERING - Delegate to PrinciplesSearchService
    # ========================================================================
    # Note: Intelligence delegations (get_principle_with_context, assess_principle_alignment,
    # get_principle_adherence_trends, get_principle_conflict_analysis)
    # delegated via explicit methods below.

    async def search_principles(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        user_uid: str | None = None,
    ) -> Result[list[Principle]]:
        """
        Search principles by text query. Delegates to PrinciplesSearchService.

        Args:
            query: Search query string
            filters: Optional additional filters (category, strength, etc.)
            limit: Maximum results to return
            user_uid: Optional user UID to scope results to owner

        Returns:
            Result with list of matching principles
        """
        # Basic text search via search sub-service
        result = await self.search.search(query, limit=limit, user_uid=user_uid)

        if result.is_error:
            return result  # type: ignore[return-value]

        matching = result.value

        # Apply additional filters if provided
        if filters:
            if "category" in filters:
                matching = [
                    p
                    for p in matching
                    if isinstance(p, Principle) and p.category and p.category == filters["category"]
                ]
            if "strength" in filters:
                matching = [
                    p
                    for p in matching
                    if isinstance(p, Principle)
                    and p.strength
                    and p.strength.value == filters["strength"]
                ]

        return Result.ok(matching)

    # Note: Simple search delegations (get_principle_categories, list_all_principle_categories,
    # get_related_principles, get_principles_by_status, get_principles_by_strength,
    # get_principles_by_category, get_principles_needing_review, get_principles_for_goal,
    # get_principles_for_choice) delegated via explicit methods below.

    async def get_principle_sources(self) -> Result[list[str]]:
        """
        List all principle sources (where principles come from).

        Returns:
            Result with list of unique sources
        """
        from core.models.enums.principle_enums import PrincipleSource

        # Return all PrincipleSource enum values
        sources = [s.value for s in PrincipleSource]
        return Result.ok(sources)

    async def get_prioritized_principles(
        self, user_uid: str, limit: int = 10
    ) -> Result[list[Principle]]:
        """
        Get principles prioritized for user context. Delegates to PrinciplesSearchService.

        Args:
            user_uid: User UID
            limit: Maximum results to return

        Returns:
            Result containing prioritized principles
        """
        from core.services.user import UserContext

        # Build minimal context for prioritization
        user_context = UserContext(user_uid=user_uid, username="")
        return await self.search.get_prioritized(user_context, limit=limit)  # type: ignore[return-value]

    # ========================================================================
    # PRINCIPLE EXPRESSIONS — Inline list on Principle entity
    # ========================================================================

    async def create_principle_expression(
        self,
        dto: Any,
    ) -> Result[dict[str, Any]]:
        """
        Create a principle expression (how principle was lived out).

        Stores expression on principle's inline expressions list via PrincipleDTO.

        Args:
            dto: Dict with principle_uid, context, behavior, and optional example

        Returns:
            Result with the created expression dict
        """
        from core.models.principle.principle_types import PrincipleExpression

        principle_uid = (
            dto.get("principle_uid")
            if isinstance(dto, dict)
            else getattr(dto, "principle_uid", None)
        )
        if not principle_uid:
            return Result.fail(
                Errors.validation(message="principle_uid is required", field="principle_uid")
            )

        context = dto.get("context") if isinstance(dto, dict) else getattr(dto, "context", None)
        behavior = dto.get("behavior") if isinstance(dto, dict) else getattr(dto, "behavior", None)
        if not context or not behavior:
            return Result.fail(
                Errors.validation(message="context and behavior are required", field="context")
            )

        example = dto.get("example") if isinstance(dto, dict) else getattr(dto, "example", None)

        # Get current principle
        principle_result = await self.core.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result.expect_error())

        principle_data = principle_result.value
        if isinstance(principle_data, Principle):
            ku_dto = principle_data.to_dto()
        elif isinstance(principle_data, dict):
            ku_dto = PrincipleDTO.from_dict(principle_data)
        else:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))

        # Create and append expression
        expression = PrincipleExpression(context=context, behavior=behavior, example=example)
        ku_dto.expressions.append(expression)

        # Save
        await self.core.backend.update(principle_uid, ku_dto.to_dict())
        self.logger.info("Created expression for principle %s", principle_uid)

        return Result.ok({"context": context, "behavior": behavior, "example": example})

    async def get_principle_expressions(
        self,
        principle_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get expressions of a principle (instances where it was lived out).

        Reads from the principle's inline expressions list.

        Args:
            principle_uid: Principle UID

        Returns:
            Result with list of expression dicts
        """
        principle_result = await self.core.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result.expect_error())

        principle_data = principle_result.value
        if isinstance(principle_data, Principle):
            ku_dto = principle_data.to_dto()
        elif isinstance(principle_data, dict):
            ku_dto = PrincipleDTO.from_dict(principle_data)
        else:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))

        return Result.ok(
            [
                {
                    "context": e.get("context"),
                    "behavior": e.get("behavior"),
                    "example": e.get("example"),
                }
                for e in ku_dto.expressions
            ]
        )

    # ========================================================================
    # ALIGNMENT HISTORY — Inline list on Principle entity
    # ========================================================================

    async def get_principle_alignment_history(
        self,
        principle_uid: str,
        limit: int = 50,
        days: int = 90,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get historical alignment assessments for a principle.

        Reads from the principle's inline alignment_history list, filtered
        by recency (days) and capped by limit.

        Args:
            principle_uid: Principle UID
            limit: Maximum records
            days: Lookback period in days

        Returns:
            Result with list of alignment assessment dicts
        """
        from datetime import date, timedelta

        principle_result = await self.core.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result.expect_error())

        principle_data = principle_result.value
        if isinstance(principle_data, Principle):
            ku_dto = principle_data.to_dto()
        elif isinstance(principle_data, dict):
            ku_dto = PrincipleDTO.from_dict(principle_data)
        else:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))

        cutoff = date.today() - timedelta(days=days)
        history = [
            {
                "assessed_date": str(a.get("assessed_date")),
                "alignment_level": a.get("alignment_level"),
                "evidence": a.get("evidence"),
                "reflection": a.get("reflection"),
            }
            for a in ku_dto.alignment_history
            if (assessed_date := a.get("assessed_date")) and assessed_date >= cutoff
        ]

        # Most recent first, then cap
        history.sort(key=_by_assessed_date, reverse=True)
        return Result.ok(history[:limit])

    # ========================================================================
    # PRINCIPLE LINKS — Neo4j relationships via UnifiedRelationshipService
    # ========================================================================

    async def create_principle_link(
        self,
        dto: Any,
    ) -> Result[dict[str, Any]]:
        """
        Create a link between a principle and another entity.

        Maps link_type to the appropriate relationship config key in PRINCIPLES_CONFIG
        and delegates to UnifiedRelationshipService.

        Args:
            dto: Dict with principle_uid, target_uid, link_type (goal/habit/knowledge/principle),
                 and optional properties

        Returns:
            Result with the created link info
        """
        principle_uid = (
            dto.get("principle_uid")
            if isinstance(dto, dict)
            else getattr(dto, "principle_uid", None)
        )
        target_uid = (
            dto.get("target_uid") if isinstance(dto, dict) else getattr(dto, "target_uid", None)
        )
        link_type = (
            dto.get("link_type") if isinstance(dto, dict) else getattr(dto, "link_type", None)
        )

        if not principle_uid or not target_uid or not link_type:
            return Result.fail(
                Errors.validation(
                    message="principle_uid, target_uid, and link_type are required",
                    field="link_type",
                )
            )

        # Map link_type to PRINCIPLES_CONFIG relationship config key
        link_type_map = {
            "goal": "guided_goals",
            "habit": "inspired_habits",
            "knowledge": "grounding_knowledge",
            "principle": "supporting_principles",
            "choice": "guided_choices",
        }

        config_key = link_type_map.get(link_type)
        if not config_key:
            return Result.fail(
                Errors.validation(
                    message=f"Unknown link_type: {link_type}. Valid: {', '.join(link_type_map)}",
                    field="link_type",
                )
            )

        properties = (
            dto.get("properties") if isinstance(dto, dict) else getattr(dto, "properties", None)
        )
        result = await self.relationships.create_relationship(
            config_key, principle_uid, target_uid, properties
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        self.logger.info(
            "Created %s link from principle %s to %s", link_type, principle_uid, target_uid
        )
        return Result.ok(
            {
                "principle_uid": principle_uid,
                "target_uid": target_uid,
                "link_type": link_type,
            }
        )

    async def get_principle_links(
        self,
        principle_uid: str,
        link_type: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get links for a principle (relationships to goals, habits, knowledge, principles).

        Queries via UnifiedRelationshipService cross-domain context and filters
        by link_type if provided.

        Args:
            principle_uid: Principle UID
            link_type: Optional filter (goal/habit/knowledge/principle/choice)

        Returns:
            Result with list of link dicts containing target info
        """
        # Map link_type to config keys
        link_type_map = {
            "goal": "guided_goals",
            "habit": "inspired_habits",
            "knowledge": "grounding_knowledge",
            "principle": "supporting_principles",
            "choice": "guided_choices",
        }

        if link_type:
            config_key = link_type_map.get(link_type)
            if not config_key:
                return Result.fail(
                    Errors.validation(
                        message=f"Unknown link_type: {link_type}. Valid: {', '.join(link_type_map)}",
                        field="link_type",
                    )
                )
            uids_result = await self.relationships.get_related_uids(config_key, principle_uid)
            if uids_result.is_error:
                return Result.fail(uids_result.expect_error())
            return Result.ok(
                [{"target_uid": uid, "link_type": link_type} for uid in uids_result.value]
            )

        # No filter — get all link types
        all_links: list[dict[str, Any]] = []
        for lt, config_key in link_type_map.items():
            uids_result = await self.relationships.get_related_uids(config_key, principle_uid)
            if uids_result.is_error:
                continue  # Skip failed queries, return what we can
            all_links.extend({"target_uid": uid, "link_type": lt} for uid in uids_result.value)

        return Result.ok(all_links)

    # ========================================================================
    # QUERY LAYER
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: str,
        category_filter: str = "all",
        strength_filter: str = "all",
        sort_by: str = "strength",
    ) -> Result[ListContext]:
        """Get filtered and sorted principles with pre-filter stats.

        Stats via Cypher COUNT (no entity deserialization).
        Category/strength filtering stays Python-side (numeric threshold logic).
        """
        import asyncio

        stats_result, entities_result = await asyncio.gather(
            self.core.get_stats_for_user(user_uid),
            self.core.get_for_user_filtered(user_uid),
        )
        if stats_result.is_error:
            return Result.fail(stats_result)
        if entities_result.is_error:
            return Result.fail(entities_result)
        filtered = _apply_principle_filters(entities_result.value, category_filter, strength_filter)
        sorted_principles = _apply_principle_sort(filtered, sort_by)
        return Result.ok({"entities": sorted_principles, "stats": stats_result.value})
