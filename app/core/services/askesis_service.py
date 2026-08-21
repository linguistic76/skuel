"""
Enhanced Askesis Service Facade - Coordination Layer
=====================================================

Facade coordinating all Askesis intelligence sub-services.

This service is part of the refactored AskesisService architecture:
- UserStateAnalyzer: State assessment and pattern detection
- ActionRecommendationEngine: Personalized recommendations
- ContextRelevanceEngine: UserContext → relevant-knowledge discovery
- QueryProcessor: Natural language query processing (orchestration)
- IntentClassifier: Query intent classification via embeddings
- ResponseGenerator: Action and context generation
- EntityExtractor: Entity extraction from queries
- ContextRetriever: Domain context retrieval
- AskesisService: Facade coordinating all sub-services (THIS FILE)

Architecture:
- Delegates all operations to appropriate sub-services
- Maintains backward compatibility with original AskesisService
- Acts as single entry point for Askesis operations
- Zero business logic (pure delegation)

January 2026: QueryProcessor decomposed into IntentClassifier + ResponseGenerator
for single responsibility and reduced complexity (962 → ~500 lines).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.models.user.conversation import ConversationContext
from core.services.askesis.action_recommendation_engine import ActionRecommendationEngine
from core.services.askesis.context_relevance_engine import ContextRelevanceEngine
from core.services.askesis.context_retriever import ContextRetriever
from core.services.askesis.entity_extractor import EntityExtractor
from core.services.askesis.intent_classifier import IntentClassifier
from core.services.askesis.query_processor import QueryProcessor
from core.services.askesis.response_generator import ResponseGenerator
from core.services.askesis.types import AskesisContext
from core.services.askesis.user_state_analyzer import UserStateAnalyzer
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.context_types import (
        CrossDomainSynergy,
        DailyWorkPlan,
        LifePathAlignment,
        PathStep,
        ScheduleAwareRecommendation,
    )
    from core.models.enums import GuidanceMode
    from core.models.search_request import SearchRequest
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.askesis.types import (
        AskesisAnalysis,
        AskesisInsight,
        AskesisRecommendation,
    )
    from core.services.askesis_citation_service import AskesisCitationService
    from core.services.canon import CanonRetrievalService
    from core.services.user import UserContext
    from core.services.user.intelligence import UserContextIntelligenceFactory
    from core.services.user.unified_user_context import RichUserContext

logger = get_logger(__name__)


@dataclass(frozen=True)
class AskesisDeps:
    """Typed dependency container for AskesisService.

    All services are required — Askesis is only created in FULL intelligence tier.
    No graceful degradation: it works or it doesn't.

    March 2026: Made all deps required (was optional per ADR-043, but Askesis
    is now gated at bootstrap — only created when INTELLIGENCE_TIER=FULL).
    """

    intelligence_factory: UserContextIntelligenceFactory
    graph_intel: Any  # boundary: protocol not yet extracted
    user_service: Any
    askesis_core_service: Any  # AskesisCoreOperations — CRUD for Askesis instances
    llm_service: Any
    embeddings_service: Any
    knowledge_service: Any
    tasks_service: Any
    goals_service: Any
    habits_service: Any
    events_service: Any
    # ZPD service — required for Askesis guided pipeline.
    # LP enrollment gate ensures curriculum data exists; ZPD assesses readiness.
    # See: core/services/zpd/zpd_service.py
    zpd_service: ZPDOperations
    # PS engagement service — required for engagement-aware bundle loading.
    # Askesis is gated on FULL tier; ps_engagement is core-tier (always wired).
    # See: core/services/ps_engagement/ps_engagement_service.py
    ps_engagement_service: Any  # boundary: PsEngagementService
    # Citation service — formats graph citations for Askesis responses
    citation_service: AskesisCitationService | None = None
    # Canon retrieval — PS-scoped readings grounding for the guided pipeline
    # (ADR-077). FULL-tier: None when embeddings are absent; Askesis is
    # FULL-tier only, so in practice non-None wherever Askesis exists.
    canon_service: CanonRetrievalService | None = None
    # PS bundle dependencies for ContextRetriever — None is valid when not available
    ku_service: Any | None = None
    lp_service: Any | None = None
    principles_service: Any | None = None
    # Backends for ContextRetriever graph queries (migrated from inline Cypher)
    ku_backend: Any | None = None  # boundary: KuBackend
    ps_backend: Any | None = None  # boundary: PsBackend


class AskesisService:
    """
    Facade coordinating all Askesis intelligence sub-services.

    This service provides a unified interface for Askesis operations
    while delegating to specialized sub-services:
    - UserStateAnalyzer: State analysis and pattern detection
    - ActionRecommendationEngine: Recommendations and optimizations
    - QueryProcessor: Natural language query processing (orchestration)
    - IntentClassifier: Query intent classification via embeddings
    - ResponseGenerator: Action and context generation
    - EntityExtractor: Entity extraction from queries
    - ContextRetriever: Domain context retrieval

    Architecture:
    - Zero business logic (pure explicit delegation)
    - Single entry point for Askesis intelligence
    - Composed of 8 focused sub-services
    - All dependencies required — no degraded modes
    - Socratic pipeline absorbed into main RAG pipeline (March 2026)

    Delegation (February 2026):
    - All 9 simple delegations are explicit async def methods
    - Complex 13-Domain methods (8 methods) remain explicit (factory logic)
    """

    # Class-level type annotations
    state_analyzer: UserStateAnalyzer
    recommendation_engine: ActionRecommendationEngine
    relevance_engine: ContextRelevanceEngine
    query_processor: QueryProcessor
    entity_extractor: EntityExtractor
    context_retriever: ContextRetriever
    intent_classifier: IntentClassifier
    response_generator: ResponseGenerator

    def __init__(self, deps: AskesisDeps) -> None:
        """
        Initialize facade with all sub-services.

        Args:
            deps: Typed AskesisDeps container — all services required.
                  Askesis is only created when INTELLIGENCE_TIER=FULL.
        """
        # Fail-fast: intelligence_factory is REQUIRED (January 2026 architecture evolution)
        if deps.intelligence_factory is None:
            raise ValueError(
                "intelligence_factory is REQUIRED for AskesisService. "
                "Askesis cannot synthesize across entity types without it."
            )

        # Store the dependencies THIS facade calls. The rest reach their
        # consumers straight off `deps` in the sub-service construction below —
        # copying them onto `self` as well built a second, read-only surface
        # that nothing used. Nine such copies were deleted 2026-08-20
        # (graph_intel, embeddings_service, knowledge_service, tasks_service,
        # goals_service, habits_service, events_service, citation_service,
        # ps_engagement_service). Add a field here only when this class calls it.
        self.user_service = deps.user_service
        self.askesis_core_service = deps.askesis_core_service
        self.llm_service = deps.llm_service
        # ZPD service — required for guided pipeline (readiness assessment).
        self.zpd_service = deps.zpd_service

        # 13-domain intelligence factory for comprehensive daily planning
        # (REQUIRED - passed at construction, not post-wired)
        self.intelligence_factory = deps.intelligence_factory

        # Initialize sub-services (no circular dependency - uses pure functions)
        self.state_analyzer = UserStateAnalyzer()
        self.recommendation_engine = ActionRecommendationEngine()
        self.relevance_engine = ContextRelevanceEngine(graph_intel=deps.graph_intel)

        self.entity_extractor = EntityExtractor(
            knowledge_service=deps.knowledge_service,
            tasks_service=deps.tasks_service,
            goals_service=deps.goals_service,
            habits_service=deps.habits_service,
            events_service=deps.events_service,
        )

        self.context_retriever = ContextRetriever(
            graph_intel=deps.graph_intel,
            # search_router is post-wired in compose (built after Askesis)
            # PS bundle dependencies
            ps_service=deps.knowledge_service,
            ku_service=deps.ku_service,
            habits_service=deps.habits_service,
            tasks_service=deps.tasks_service,
            events_service=deps.events_service,
            principles_service=deps.principles_service,
            lp_service=deps.lp_service,
            # Backends for graph queries (migrated from inline Cypher)
            ku_backend=deps.ku_backend,
            ps_backend=deps.ps_backend,
            # Engagement service for lifecycle-aware bundle loading
            ps_engagement_service=deps.ps_engagement_service,
        )

        # January 2026: IntentClassifier and ResponseGenerator extracted from QueryProcessor
        self.intent_classifier = IntentClassifier(embeddings_service=deps.embeddings_service)
        self.response_generator = ResponseGenerator()

        # Conversation session manager — in-memory, shared across all queries
        self.conversation_context = ConversationContext()

        self.query_processor = QueryProcessor(
            intent_classifier=self.intent_classifier,
            response_generator=self.response_generator,
            entity_extractor=self.entity_extractor,
            context_retriever=self.context_retriever,
            user_service=deps.user_service,
            llm_service=deps.llm_service,
            graph_intel=deps.graph_intel,
            zpd_service=deps.zpd_service,
            citation_service=deps.citation_service,
            canon_service=deps.canon_service,
            conversation_context=self.conversation_context,
        )

        logger.info("AskesisService initialized with 8 specialized sub-services")

    # ========================================================================
    # CONTEXT LOADING (orchestration previously in route layer)
    # ========================================================================

    async def load_askesis_context(self, askesis_uid: str) -> Result[AskesisContext]:
        """Load an Askesis instance and its owner's rich UserContext.

        Centralises the get_askesis → get_rich_unified_context orchestration
        used by intelligence API routes. Both services are required deps
        (guaranteed non-None at construction).

        Args:
            askesis_uid: UID of the Askesis instance to load.

        Returns:
            Result[AskesisContext] with askesis, user_uid, and user_context.
        """
        askesis_result = await self.askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return Result.fail(askesis_result)

        askesis = askesis_result.value

        context_result = await self.user_service.get_rich_unified_context(askesis.user_uid)
        if context_result.is_error:
            return Result.fail(context_result)

        return Result.ok(
            AskesisContext(
                askesis=askesis,
                user_uid=askesis.user_uid,
                user_context=context_result.value,
            )
        )

    # ========================================================================
    # EXPLICIT DELEGATIONS
    # ========================================================================
    #
    # STATE ANALYSIS (2 methods → state_analyzer):
    # - identify_patterns(user_context) → list[AskesisInsight]
    # - calculate_system_health(user_context) → dict[str, float]
    #
    # RECOMMENDATIONS (3 methods → recommendation_engine):
    # - get_next_best_action(user_context) → AskesisRecommendation
    # - optimize_workflow(user_context) → list[dict]
    # - predict_future_state(user_context, days_ahead) → dict
    #
    # QUERY PROCESSING (2 methods → query_processor):
    # - answer_user_question(user_uid, question, session_id=None) → dict
    # - process_query_with_context(user_uid, query_message, depth) → dict
    #
    # CONTEXT RETRIEVAL (2 methods → context_retriever):
    # - get_learning_context(user_uid, depth) → dict
    # - analyze_knowledge_gaps(user_uid) → dict
    #
    # ========================================================================

    async def identify_patterns(self, user_context: UserContext) -> Result[list[AskesisInsight]]:
        """Identify patterns in user's behavior. Delegated to state_analyzer."""
        return await self.state_analyzer.identify_patterns(user_context)

    def calculate_system_health(self, user_context: UserContext) -> dict[str, float]:
        """Calculate system health metrics. Delegated to state_analyzer."""
        return self.state_analyzer.calculate_system_health(user_context)

    async def get_next_best_action(
        self, user_context: UserContext
    ) -> Result[AskesisRecommendation]:
        """Get next best action recommendation. Delegated to recommendation_engine."""
        return await self.recommendation_engine.get_next_best_action(user_context)

    async def optimize_workflow(self, user_context: UserContext) -> Result[list[dict[str, Any]]]:
        """Suggest workflow optimizations. Delegated to recommendation_engine."""
        return await self.recommendation_engine.optimize_workflow(user_context)

    async def predict_future_state(
        self, user_context: UserContext, days_ahead: int = 7
    ) -> Result[dict[str, Any]]:
        """Predict future state. Delegated to recommendation_engine."""
        return await self.recommendation_engine.predict_future_state(user_context, days_ahead)

    async def answer_user_question(
        self,
        user_uid: UserUID,
        question: str,
        session_id: str | None = None,
        preferred_mode: "GuidanceMode | None" = None,
        scope: "SearchRequest | None" = None,
        model: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Answer user question via RAG pipeline. Delegated to query_processor.

        ``scope`` carries an optional facet (e.g. a ``nous`` topic from the
        Askesis composer) that narrows the retrieved passages to that topic.
        ``model`` is the per-conversation switcher choice, gated OpenAI-safe
        downstream.
        """
        return await self.query_processor.answer_user_question(
            user_uid, question, session_id, preferred_mode, scope, model
        )

    def available_chat_models(self) -> list[tuple[str, str]]:
        """Headline chat models the wired caller can serve — the switcher's options.

        Availability comes from the multi-provider caller (see
        ``core.services.chat.available_chat_models``): a dev env with no Anthropic
        adapter offers only the OpenAI models. Empty when no caller is wired
        (MOCK/CORE) so the surface renders no picker.
        """
        from core.services.chat import available_chat_models

        if self.llm_service is None or self.llm_service.caller is None:
            return []
        return available_chat_models(self.llm_service.caller)

    async def process_query_with_context(
        self, user_uid: UserUID, query_message: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """Process query with context. Delegated to query_processor."""
        return await self.query_processor.process_query_with_context(user_uid, query_message, depth)

    async def get_learning_context(
        self, user_uid: UserUID, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """Get user's learning context. Fetches rich UserContext, then delegates."""
        context_result = await self.user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result)
        return await self.context_retriever.get_learning_context(context_result.value, depth)

    async def analyze_knowledge_gaps(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Analyze knowledge gaps. Fetches rich UserContext, then delegates."""
        context_result = await self.user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result)
        return await self.context_retriever.analyze_knowledge_gaps(context_result.value)

    # ========================================================================
    # EXPLICIT ORCHESTRATION METHODS
    # ========================================================================

    async def analyze_user_state(
        self,
        user_context: UserContext,
        focus_areas: list[str] | None = None,
    ) -> Result[AskesisAnalysis]:
        """
        Perform comprehensive analysis of user's state using full context.

        Orchestrates the full analysis flow:
        1. Generate insights (UserStateAnalyzer)
        2. Generate recommendations based on insights (ActionRecommendationEngine)
        3. Generate optimizations (ActionRecommendationEngine)
        4. Combine into comprehensive AskesisAnalysis

        Args:
            user_context: Complete user context
            focus_areas: Optional specific areas to focus on

        Returns:
            Result[AskesisAnalysis]: Comprehensive analysis with insights,
                recommendations, health metrics, and optimization opportunities

        Note:
            January 2026: This method is now explicit (not delegated) to orchestrate
            the full analysis flow without circular dependencies between sub-services.
        """
        # Step 1: Get insights from state analyzer
        insights_result = await self.state_analyzer.identify_patterns(user_context)
        insights = insights_result.value if insights_result.is_ok else []

        # Step 2: Generate recommendations based on insights
        recommendations_result = await self.recommendation_engine.generate_recommendations(
            user_context, insights
        )
        recommendations = recommendations_result.value if recommendations_result.is_ok else []

        # Step 3: Generate optimizations
        optimizations_result = await self.recommendation_engine.optimize_workflow(user_context)
        optimizations = optimizations_result.value if optimizations_result.is_ok else []

        # Step 4: ZPD snapshot — enriches the analysis with curriculum graph assessment.
        # None when ZPDService is not wired or curriculum graph has < 3 KUs.
        zpd_assessment = None
        if self.zpd_service is not None:
            zpd_result = await self.zpd_service.assess_zone(user_context.user_uid)
            if not zpd_result.is_error:
                zpd_assessment = zpd_result.value

        # Step 5: Combine into comprehensive analysis
        return await self.state_analyzer.analyze_user_state(
            user_context,
            focus_areas=focus_areas,
            recommendations=recommendations,
            optimizations=optimizations,
            zpd_assessment=zpd_assessment,
        )

    # ========================================================================
    # 13-DOMAIN INTELLIGENCE (Explicit - factory logic required)
    # ========================================================================
    #
    # These methods leverage the full 13-domain architecture for comprehensive
    # daily planning and path step recommendations.
    #
    # Architecture:
    # UserContextIntelligence = UserContext + 13 Domain Services
    # = User State + Complete Graph Intelligence
    #
    # Entity Types:
    # Activity Domains (6): Tasks, Goals, Habits, Events, Choices, Principles
    # Curriculum Domains (3): KU, PS, LP
    # Processing Domains (3): Assignments, Journals, Reports
    # Temporal Domain (1): Calendar
    #
    # ========================================================================

    async def get_daily_work_plan(
        self,
        user_context: RichUserContext,
        prioritize_life_path: bool = True,
        respect_capacity: bool = True,
    ) -> Result[DailyWorkPlan]:
        """
        🎯 THE FLAGSHIP METHOD - What should the user focus on TODAY?

        Synthesizes all entity types to create a comprehensive daily plan:
        - At-risk habits (maintain streaks - highest priority)
        - Today's events (can't reschedule)
        - Overdue and actionable tasks
        - Daily habits (consistency)
        - Learning (if capacity allows)
        - Advancing goals
        - Pending decisions (high priority only)
        - Aligned principles (for focus)

        Engagement-aware bucketing (ADR-059) lives inside
        ``UserContextIntelligence.get_ready_to_work_on_today()`` — the plan
        returned here already has ``engaged_ps_groups`` and
        ``available_to_start`` populated when ``user_context.active_ps_engagements``
        is set by the builder.

        Args:
            user_context: Complete UserContext snapshot (~240 fields)
            prioritize_life_path: Weight life path alignment highly
            respect_capacity: Don't exceed available time

        Returns:
            Result[DailyWorkPlan]: Complete daily plan with:
                - Domain-specific item lists (learning, tasks, habits, events, goals, choices, principles)
                - Contextual items (enriched with relationships)
                - Engagement-aware buckets (engaged_ps_groups, available_to_start)
                - Estimated time and capacity utilization
                - Rationale and warnings
        """
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available - cannot create daily work plan",
                    operation="get_daily_work_plan",
                )
            )

        intelligence = self.intelligence_factory.create(user_context)
        return await intelligence.get_ready_to_work_on_today(
            prioritize_life_path=prioritize_life_path,
            respect_capacity=respect_capacity,
        )

    async def get_optimal_next_path_steps(
        self,
        user_context: RichUserContext,
        max_steps: int = 5,
        consider_goals: bool = True,
        consider_capacity: bool = True,
    ) -> Result[list[PathStep]]:
        """
        Determine what to learn next based on ALL factors.

        **Synthesizes:**
        - KU service: get_ready_to_learn_for_user() - Prerequisites met
        - Goals service: Goal alignment
        - Tasks service: Knowledge application opportunities
        - Context: Capacity, energy, life path alignment

        **Ranking Factors:**
        - Prerequisites met (ready to learn)
        - Goal alignment (helps achieve goals)
        - User capacity (fits available time)
        - Life path alignment (flows toward ultimate path)
        - Unblocking potential (unlocks other items)

        Args:
            user_context: Complete UserContext snapshot
            max_steps: Maximum number of steps to return
            consider_goals: Weight by goal alignment
            consider_capacity: Respect user capacity limits

        Returns:
            Result[list[PathStep]]: Ranked list with:
                - ku_uid, title, rationale
                - prerequisites_met, aligns_with_goals
                - unlocks_count, estimated_time_minutes
                - priority_score, application_opportunities
        """
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available - cannot get path steps",
                    operation="get_optimal_next_path_steps",
                )
            )

        # Create intelligence instance from factory with user context
        intelligence = self.intelligence_factory.create(user_context)

        # Get optimal path steps
        return await intelligence.get_optimal_next_path_steps(
            max_steps=max_steps,
            consider_goals=consider_goals,
            consider_capacity=consider_capacity,
        )

    async def get_learning_path_critical_path(
        self,
        user_context: RichUserContext,
    ) -> Result[list[str]]:
        """
        What's the fastest route to life path alignment?

        **Synthesizes:**
        - LP service: Learning path structure
        - KU service: Prerequisite chains
        - Context: Current mastery levels

        Args:
            user_context: Complete UserContext snapshot

        Returns:
            Result[list[str]]: Ordered list of KU UIDs representing critical path
        """
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available - cannot get critical path",
                    operation="get_learning_path_critical_path",
                )
            )

        # Create intelligence instance from factory with user context
        intelligence = self.intelligence_factory.create(user_context)

        # Get critical path
        return await intelligence.get_learning_path_critical_path()

    async def get_knowledge_application_opportunities(
        self,
        user_context: RichUserContext,
        ku_uid: str,
    ) -> Result[dict[str, list[str]]]:
        """
        Where can I apply this knowledge in my life?

        **Synthesizes ALL 6 activity domains:**
        - Tasks: Tasks that require this knowledge
        - Habits: Habits that would benefit from this understanding
        - Goals: Goals that align with this knowledge
        - Events: Events where I could practice
        - Choices: Decisions informed by this knowledge
        - Principles: Values this knowledge supports

        Args:
            user_context: Complete UserContext snapshot
            ku_uid: Knowledge unit UID

        Returns:
            Result[dict[str, list[str]]]: Dict of {domain: [uid_list]}
        """
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available - cannot get application opportunities",
                    operation="get_knowledge_application_opportunities",
                )
            )

        # Create intelligence instance from factory with user context
        intelligence = self.intelligence_factory.create(user_context)

        # Get application opportunities
        return await intelligence.get_knowledge_application_opportunities(ku_uid)

    async def get_unblocking_priority_order(
        self,
        user_context: RichUserContext,
    ) -> Result[list[tuple[str, int]]]:
        """
        What should I learn first to unlock the most items?

        **Synthesizes:**
        - Context: prerequisites_needed mapping
        - KU service: Readiness status
        - Tasks service: Blocked task counts

        Args:
            user_context: Complete UserContext snapshot

        Returns:
            Result[list[tuple[str, int]]]: List of (ku_uid, blocked_count) sorted by impact
        """
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available - cannot get unblocking order",
                    operation="get_unblocking_priority_order",
                )
            )

        # Create intelligence instance from factory with user context
        intelligence = self.intelligence_factory.create(user_context)

        # Get unblocking priority order
        return await intelligence.get_unblocking_priority_order()

    # =========================================================================
    # PHASE 2: Cross-Domain Synergies (Habit→Goal, Task→Habit, etc.)
    # =========================================================================

    async def get_cross_domain_synergies(
        self,
        user_context: RichUserContext,
        min_synergy_score: float = 0.3,
        include_types: list[str] | None = None,
    ) -> Result[list[CrossDomainSynergy]]:
        """
        Detect synergies between entities across different domains.

        Cross-domain correlation for habit→goal synergies
        and other high-leverage connections.

        **Synergy Types Detected:**
        1. Habit→Goal: Habits supporting multiple goals (high leverage)
        2. Task→Habit: Tasks that build habits (behavior change)
        3. Knowledge→Task: Knowledge enabling tasks (skill application)
        4. Principle→Goal: Principles guiding goal pursuit (value alignment)
        5. Goal→Learning: Goals requiring specific knowledge (learning gaps)

        **Use Cases:**
        - "Which habits give me the most bang for my buck?"
        - "What should I focus on to advance multiple goals?"
        - "How do my daily actions connect to my life path?"

        Args:
            user_context: Complete UserContext snapshot
            min_synergy_score: Minimum score to include (0.0-1.0)
            include_types: Filter to specific types ["habit_goal", "task_habit", etc.]

        Returns:
            Result[list[CrossDomainSynergy]]: Synergies sorted by score (highest first)
        """
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available - cannot detect cross-domain synergies",
                    operation="get_cross_domain_synergies",
                )
            )

        # Create intelligence instance from factory with user context
        intelligence = self.intelligence_factory.create(user_context)

        # Get cross-domain synergies
        return await intelligence.get_cross_domain_synergies(
            min_synergy_score=min_synergy_score,
            include_types=include_types,
        )

    # =========================================================================
    # PHASE 3: Life Path Alignment Scoring
    # =========================================================================

    async def calculate_life_path_alignment(
        self,
        user_context: RichUserContext,
    ) -> Result[LifePathAlignment]:
        """
        Calculate comprehensive life path alignment.

        Multi-dimensional life path alignment scoring.

        **Philosophy:** "Everything flows toward the life path"

        **Alignment Dimensions (5):**
        1. Knowledge Alignment (25%): Mastery of life path knowledge
        2. Activity Alignment (25%): Tasks/habits supporting life path
        3. Goal Alignment (20%): Active goals contributing to life path
        4. Principle Alignment (15%): Values supporting life path direction
        5. Momentum (15%): Recent activity trend toward life path

        **Use Cases:**
        - "Am I living in alignment with my life purpose?"
        - "Where am I drifting from my path?"
        - "What should I prioritize to get back on track?"

        Args:
            user_context: Complete UserContext snapshot

        Returns:
            Result[LifePathAlignment]: Alignment with scores, insights, recommendations
        """
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available - cannot calculate life path alignment",
                    operation="calculate_life_path_alignment",
                )
            )

        # Create intelligence instance from factory with user context
        intelligence = self.intelligence_factory.create(user_context)

        # Calculate life path alignment
        return await intelligence.calculate_life_path_alignment()

    # =========================================================================
    # USERCONTEXT + KNOWLEDGE INTEGRATION
    # =========================================================================
    # Thin delegations to ContextRelevanceEngine (extracted Tier 6) — the
    # engine finds knowledge relevant to the user's current activities.
    #
    # =========================================================================

    async def find_relevant_for_context(
        self,
        active_goals: list[str] | None = None,
        current_habits: list[str] | None = None,
        recent_choices: list[str] | None = None,
        pending_tasks: list[str] | None = None,
        active_principles: list[str] | None = None,
        upcoming_events: list[str] | None = None,
        max_results: int = 10,
        min_relevance_score: float = 0.5,
    ) -> Result[dict[str, Any]]:
        """Find knowledge relevant to current activities. Delegated to relevance_engine."""
        return await self.relevance_engine.find_relevant_for_context(
            active_goals=active_goals,
            current_habits=current_habits,
            recent_choices=recent_choices,
            pending_tasks=pending_tasks,
            active_principles=active_principles,
            upcoming_events=upcoming_events,
            max_results=max_results,
            min_relevance_score=min_relevance_score,
        )

    async def find_relevant_from_user_context(
        self,
        user_context: UserContext,
        max_results: int = 10,
        min_relevance_score: float = 0.5,
    ) -> Result[dict[str, Any]]:
        """Find relevant knowledge from UserContext. Delegated to relevance_engine."""
        return await self.relevance_engine.find_relevant_from_user_context(
            user_context, max_results=max_results, min_relevance_score=min_relevance_score
        )

    # =========================================================================
    # PHASE 4: Schedule-Aware Recommendations
    # =========================================================================

    async def get_schedule_aware_recommendations(
        self,
        user_context: RichUserContext,
        max_recommendations: int = 5,
        time_horizon_hours: int = 8,
        respect_energy: bool = True,
    ) -> Result[list[ScheduleAwareRecommendation]]:
        """
        Get recommendations that consider the user's schedule and capacity.

        Schedule-aware intelligence that considers:
        - Current events and scheduled activities
        - Energy levels and preferred times
        - Available time slots and capacity
        - Priority and urgency across all domains
        - Conflict detection and avoidance

        **Philosophy:** "Right action at the right time"

        **Recommendation Types:**
        - "learn": Knowledge unit to study
        - "task": Task to complete
        - "habit": Habit to maintain
        - "goal": Goal to advance
        - "rest": Rest recommendation (capacity exceeded)
        - "reschedule": Reschedule suggestion for conflicts

        **Use Cases:**
        - "What should I do RIGHT NOW given my schedule?"
        - "What fits my current energy level?"
        - "What's most important given my available time?"

        Args:
            user_context: Complete UserContext snapshot
            max_recommendations: Maximum number of recommendations (default 5)
            time_horizon_hours: How far ahead to look (default 8)
            respect_energy: Whether to consider energy levels (default True)

        Returns:
            Result[list[ScheduleAwareRecommendation]]: Ranked recommendations
        """
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available - cannot get schedule-aware recommendations",
                    operation="get_schedule_aware_recommendations",
                )
            )

        # Create intelligence instance from factory with user context
        intelligence = self.intelligence_factory.create(user_context)

        # Get schedule-aware recommendations
        recommendations = await intelligence.get_schedule_aware_recommendations(
            max_recommendations=max_recommendations,
            time_horizon_hours=time_horizon_hours,
            respect_energy=respect_energy,
        )

        return Result.ok(recommendations)
