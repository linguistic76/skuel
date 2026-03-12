"""
Enhanced Askesis Service Facade - Coordination Layer
=====================================================

Facade coordinating all Askesis intelligence sub-services.

This service is part of the refactored AskesisService architecture:
- UserStateAnalyzer: State assessment and pattern detection
- ActionRecommendationEngine: Personalized recommendations
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

from core.models.relationship_names import RelationshipName
from core.models.user.conversation import ConversationContext
from core.services.askesis.action_recommendation_engine import ActionRecommendationEngine
from core.services.askesis.context_retriever import ContextRetriever
from core.services.askesis.entity_extractor import EntityExtractor
from core.services.askesis.intent_classifier import IntentClassifier
from core.services.askesis.ls_context_loader import LSContextLoader
from core.services.askesis.query_processor import QueryProcessor
from core.services.askesis.response_generator import ResponseGenerator
from core.services.askesis.socratic_engine import SocraticEngine
from core.services.askesis.user_state_analyzer import UserStateAnalyzer
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.context_types import (
        CrossDomainSynergy,
        DailyWorkPlan,
        LearningStep,
        LifePathAlignment,
        ScheduleAwareRecommendation,
    )
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.askesis.types import (
        AskesisAnalysis,
        AskesisInsight,
        AskesisRecommendation,
    )
    from core.services.user import UserContext
    from core.services.user.intelligence import UserContextIntelligenceFactory

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
    graph_intelligence_service: Any  # boundary: protocol not yet extracted
    user_service: Any
    llm_service: Any
    embeddings_service: Any
    knowledge_service: Any
    tasks_service: Any
    goals_service: Any
    habits_service: Any
    events_service: Any
    # Citation service — optional until wired in bootstrap
    citation_service: Any | None = None
    # ZPD service — enriches analyze_user_state() with curriculum graph assessment.
    # None when curriculum graph has < 3 KUs (data condition, not degradation).
    # See: core/services/zpd/zpd_service.py
    zpd_service: ZPDOperations | None = None
    # Socratic pipeline dependencies (Phase 5)
    # Optional services for LSContextLoader — None is valid when not needed
    ku_service: Any | None = None
    lp_service: Any | None = None
    principles_service: Any | None = None


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
    - Composed of 7 focused sub-services
    - All dependencies required — no degraded modes

    Delegation (February 2026):
    - All 9 simple delegations are explicit async def methods
    - Complex 13-Domain methods (8 methods) remain explicit (factory logic)
    """

    # Class-level type annotations
    state_analyzer: UserStateAnalyzer
    recommendation_engine: ActionRecommendationEngine
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

        # Store dependencies
        self.graph_intel = deps.graph_intelligence_service
        self.user_service = deps.user_service
        self.llm_service = deps.llm_service
        self.embeddings_service = deps.embeddings_service
        self.knowledge_service = deps.knowledge_service
        self.tasks_service = deps.tasks_service
        self.goals_service = deps.goals_service
        self.habits_service = deps.habits_service
        self.events_service = deps.events_service
        self.citation_service = deps.citation_service
        # ZPD service — enriches analyze_user_state() with curriculum graph assessment.
        self.zpd_service = deps.zpd_service

        # 13-domain intelligence factory for comprehensive daily planning
        # (REQUIRED - passed at construction, not post-wired)
        self.intelligence_factory = deps.intelligence_factory

        # Initialize sub-services (no circular dependency - uses pure functions)
        self.state_analyzer = UserStateAnalyzer()
        self.recommendation_engine = ActionRecommendationEngine()

        self.entity_extractor = EntityExtractor(
            knowledge_service=deps.knowledge_service,
            tasks_service=deps.tasks_service,
            goals_service=deps.goals_service,
            habits_service=deps.habits_service,
            events_service=deps.events_service,
        )

        self.context_retriever = ContextRetriever(
            graph_intelligence_service=deps.graph_intelligence_service,
            embeddings_service=deps.embeddings_service,
        )

        # January 2026: IntentClassifier and ResponseGenerator extracted from QueryProcessor
        self.intent_classifier = IntentClassifier(embeddings_service=deps.embeddings_service)
        self.response_generator = ResponseGenerator()

        # Socratic pipeline sub-services (Phase 5)
        self.socratic_engine = SocraticEngine()
        self.conversation_context = ConversationContext()
        self.ls_context_loader = LSContextLoader(
            article_service=deps.knowledge_service,
            ku_service=deps.ku_service,
            habits_service=deps.habits_service,
            tasks_service=deps.tasks_service,
            events_service=deps.events_service,
            principles_service=deps.principles_service,
            lp_service=deps.lp_service,
        )

        self.query_processor = QueryProcessor(
            intent_classifier=self.intent_classifier,
            response_generator=self.response_generator,
            entity_extractor=self.entity_extractor,
            context_retriever=self.context_retriever,
            user_service=deps.user_service,
            llm_service=deps.llm_service,
            graph_intelligence_service=deps.graph_intelligence_service,
            citation_service=deps.citation_service,
            # Socratic pipeline
            ls_context_loader=self.ls_context_loader,
            socratic_engine=self.socratic_engine,
            zpd_service=deps.zpd_service,
            conversation_context=self.conversation_context,
        )

        logger.info(
            "AskesisService initialized with 7 specialized sub-services + Socratic pipeline"
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
    # QUERY PROCESSING (3 methods → query_processor):
    # - answer_user_question(user_uid, question) → dict
    # - ask_socratic(user_uid, question, session_id) → dict
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

    async def answer_user_question(self, user_uid: str, question: str) -> Result[dict[str, Any]]:
        """Answer user question via RAG pipeline. Delegated to query_processor."""
        return await self.query_processor.answer_user_question(user_uid, question)

    async def ask_socratic(
        self, user_uid: str, question: str, session_id: str | None = None
    ) -> Result[dict[str, Any]]:
        """LS-scoped Socratic tutoring. Delegated to query_processor."""
        return await self.query_processor.process_socratic_turn(user_uid, question, session_id)

    async def process_query_with_context(
        self, user_uid: str, query_message: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """Process query with context. Delegated to query_processor."""
        return await self.query_processor.process_query_with_context(user_uid, query_message, depth)

    async def get_learning_context(self, user_uid: str, depth: int = 2) -> Result[dict[str, Any]]:
        """Get user's learning context. Delegated to context_retriever."""
        return await self.context_retriever.get_learning_context(user_uid, depth)

    async def analyze_knowledge_gaps(self, user_uid: str) -> Result[dict[str, Any]]:
        """Analyze knowledge gaps. Delegated to context_retriever."""
        return await self.context_retriever.analyze_knowledge_gaps(user_uid)

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
    # daily planning and learning step recommendations.
    #
    # Architecture:
    # UserContextIntelligence = UserContext + 13 Domain Services
    # = User State + Complete Graph Intelligence
    #
    # Entity Types:
    # Activity Domains (6): Tasks, Goals, Habits, Events, Choices, Principles
    # Curriculum Domains (3): KU, LS, LP
    # Processing Domains (3): Assignments, Journals, Reports
    # Temporal Domain (1): Calendar
    #
    # ========================================================================

    async def get_daily_work_plan(
        self,
        user_context: UserContext,
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

        **This replaces get_next_best_action() for comprehensive planning.**

        Args:
            user_context: Complete UserContext snapshot (~240 fields)
            prioritize_life_path: Weight life path alignment highly
            respect_capacity: Don't exceed available time

        Returns:
            Result[DailyWorkPlan]: Complete daily plan with:
                - Domain-specific item lists (learning, tasks, habits, events, goals, choices, principles)
                - Contextual items (enriched with relationships)
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

        # Create intelligence instance from factory with user context
        intelligence = self.intelligence_factory.create(user_context)

        # Get comprehensive daily plan
        return Result.ok(
            await intelligence.get_ready_to_work_on_today(
                prioritize_life_path=prioritize_life_path,
                respect_capacity=respect_capacity,
            )
        )

    async def get_optimal_next_learning_steps(
        self,
        user_context: UserContext,
        max_steps: int = 5,
        consider_goals: bool = True,
        consider_capacity: bool = True,
    ) -> Result[list[LearningStep]]:
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
            Result[list[LearningStep]]: Ranked list with:
                - ku_uid, title, rationale
                - prerequisites_met, aligns_with_goals
                - unlocks_count, estimated_time_minutes
                - priority_score, application_opportunities
        """
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available - cannot get learning steps",
                    operation="get_optimal_next_learning_steps",
                )
            )

        # Create intelligence instance from factory with user context
        intelligence = self.intelligence_factory.create(user_context)

        # Get optimal learning steps
        return Result.ok(
            await intelligence.get_optimal_next_learning_steps(
                max_steps=max_steps,
                consider_goals=consider_goals,
                consider_capacity=consider_capacity,
            )
        )

    async def get_learning_path_critical_path(
        self,
        user_context: UserContext,
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
        return Result.ok(await intelligence.get_learning_path_critical_path())

    async def get_knowledge_application_opportunities(
        self,
        user_context: UserContext,
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
        return Result.ok(await intelligence.get_knowledge_application_opportunities(ku_uid))

    async def get_unblocking_priority_order(
        self,
        user_context: UserContext,
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
        return Result.ok(await intelligence.get_unblocking_priority_order())

    # =========================================================================
    # PHASE 2: Cross-Domain Synergies (Habit→Goal, Task→Habit, etc.)
    # =========================================================================

    async def get_cross_domain_synergies(
        self,
        user_context: UserContext,
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
        synergies = await intelligence.get_cross_domain_synergies(
            min_synergy_score=min_synergy_score,
            include_types=include_types,
        )

        return Result.ok(synergies)

    # =========================================================================
    # PHASE 3: Life Path Alignment Scoring
    # =========================================================================

    async def calculate_life_path_alignment(
        self,
        user_context: UserContext,
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
        alignment = await intelligence.calculate_life_path_alignment()

        return Result.ok(alignment)

    # =========================================================================
    # USERCONTEXT + KNOWLEDGE INTEGRATION
    # =========================================================================
    # These methods find relevant knowledge based on the user's current
    # activities across all entity types. They bridge UserContext awareness
    # with knowledge recommendations.
    #
    # Architecture:
    # UserContext → Current activities (goals, habits, choices, etc.)
    # AskesisService → Find knowledge that supports those activities
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
        """
        Find knowledge units relevant to the user's current activities.

        This is THE bridge between UserContext and knowledge discovery.
        When a user is ready for content, this method finds knowledge that
        matches and supports their current activities across all domains.

        **Use Case:**
        ```python
        # Get user's current context
        user_context = await user_service.get_user_context(user_uid)

        # Find knowledge that matches their activities
        relevant_ku = await askesis_service.find_relevant_for_context(
            active_goals=user_context.active_goal_uids,
            current_habits=list(user_context.habit_streaks.keys()),
            recent_choices=user_context.pending_choice_uids,
        )
        ```

        **Relevance Scoring:**
        - Goal alignment: Knowledge required or useful for active goals
        - Habit support: Knowledge that reinforces habit formation
        - Choice inform: Knowledge that helps make pending decisions
        - Task enablement: Knowledge that unblocks pending tasks
        - Principle grounding: Knowledge that supports core principles
        - Event preparation: Knowledge useful for upcoming events

        Args:
            active_goals: UIDs of user's active goals
            current_habits: UIDs of habits user is tracking
            recent_choices: UIDs of pending or recent choices
            pending_tasks: UIDs of actionable tasks
            active_principles: UIDs of user's core principles
            upcoming_events: UIDs of upcoming events
            max_results: Maximum knowledge units to return
            min_relevance_score: Minimum relevance score (0.0-1.0)

        Returns:
            Result[dict[str, Any]]: {
                "knowledge_units": [...], # Relevant KU data
                "relevance_scores": {...}, # UID -> score mapping
                "relevance_reasons": {...}, # UID -> list of reasons
                "domain_coverage": {...}, # Which domains each KU helps
                "recommended_order": [...], # Optimal learning order
            }
        """
        # Use graph intelligence if available
        if not self.graph_intel:
            return Result.fail(
                Errors.system(
                    message="Graph intelligence service not available",
                    operation="find_relevant_for_context",
                )
            )

        # Aggregate all activity UIDs
        all_activity_uids: list[str] = []
        domain_sources: dict[str, str] = {}  # uid -> domain

        if active_goals:
            all_activity_uids.extend(active_goals)
            for uid in active_goals:
                domain_sources[uid] = "goal"

        if current_habits:
            all_activity_uids.extend(current_habits)
            for uid in current_habits:
                domain_sources[uid] = "habit"

        if recent_choices:
            all_activity_uids.extend(recent_choices)
            for uid in recent_choices:
                domain_sources[uid] = "choice"

        if pending_tasks:
            all_activity_uids.extend(pending_tasks)
            for uid in pending_tasks:
                domain_sources[uid] = "task"

        if active_principles:
            all_activity_uids.extend(active_principles)
            for uid in active_principles:
                domain_sources[uid] = "principle"

        if upcoming_events:
            all_activity_uids.extend(upcoming_events)
            for uid in upcoming_events:
                domain_sources[uid] = "event"

        if not all_activity_uids:
            # No activities to match against
            return Result.ok(
                {
                    "knowledge_units": [],
                    "relevance_scores": {},
                    "relevance_reasons": {},
                    "domain_coverage": {},
                    "recommended_order": [],
                }
            )

        # Query graph for knowledge connected to these activities
        relevant_knowledge: dict[str, dict[str, Any]] = {}
        relevance_reasons: dict[str, list[str]] = {}
        domain_coverage: dict[str, list[str]] = {}

        # Query knowledge for each activity type
        for activity_uid in all_activity_uids:
            domain = domain_sources[activity_uid]

            # Get knowledge connected to this activity
            ku_result = await self._find_knowledge_for_activity(
                activity_uid=activity_uid,
                activity_domain=domain,
            )

            if ku_result.is_ok and ku_result.value:
                for ku_data in ku_result.value:
                    ku_uid = ku_data.get("uid", "")
                    if not ku_uid:
                        continue

                    # Accumulate knowledge
                    if ku_uid not in relevant_knowledge:
                        relevant_knowledge[ku_uid] = ku_data
                        relevance_reasons[ku_uid] = []
                        domain_coverage[ku_uid] = []

                    # Track why it's relevant
                    reason = f"Supports {domain}: {activity_uid}"
                    if reason not in relevance_reasons[ku_uid]:
                        relevance_reasons[ku_uid].append(reason)

                    # Track domain coverage
                    if domain not in domain_coverage[ku_uid]:
                        domain_coverage[ku_uid].append(domain)

        # Calculate relevance scores
        relevance_scores: dict[str, float] = {}
        for ku_uid, reasons in relevance_reasons.items():
            # Base score from number of connections
            base_score = min(1.0, len(reasons) * 0.2)

            # Bonus for multi-domain coverage
            domain_bonus = len(domain_coverage[ku_uid]) * 0.15

            # Calculate final score
            score = min(1.0, base_score + domain_bonus)
            relevance_scores[ku_uid] = score

        # Filter by minimum score
        filtered_knowledge = {
            uid: data
            for uid, data in relevant_knowledge.items()
            if relevance_scores.get(uid, 0) >= min_relevance_score
        }

        # Sort by relevance score
        from core.utils.sort_functions import make_dict_score_getter

        sort_by_relevance = make_dict_score_getter(relevance_scores, default=0.0)
        sorted_uids = sorted(
            filtered_knowledge.keys(),
            key=sort_by_relevance,
            reverse=True,
        )[:max_results]

        # Build recommended order (consider prerequisites)
        recommended_order = await self._order_by_prerequisites(sorted_uids)

        return Result.ok(
            {
                "knowledge_units": [filtered_knowledge[uid] for uid in sorted_uids],
                "relevance_scores": {uid: relevance_scores[uid] for uid in sorted_uids},
                "relevance_reasons": {uid: relevance_reasons[uid] for uid in sorted_uids},
                "domain_coverage": {uid: domain_coverage[uid] for uid in sorted_uids},
                "recommended_order": recommended_order,
            }
        )

    async def find_relevant_from_user_context(
        self,
        user_context: UserContext,
        max_results: int = 10,
        min_relevance_score: float = 0.5,
    ) -> Result[dict[str, Any]]:
        """
        Convenience method that extracts activity UIDs from UserContext.

        This is the primary method for the UserContext + Askesis integration.

        **Usage:**
        ```python
        # Get user context
        result = await user_service.get_user_context(user_uid)
        if result.is_error:
            return result

        user_context = result.value

        # Find relevant knowledge
        relevant = await askesis_service.find_relevant_from_user_context(
            user_context,
            max_results=10,
        )
        ```

        Args:
            user_context: Complete UserContext snapshot
            max_results: Maximum knowledge units to return
            min_relevance_score: Minimum relevance score (0.0-1.0)

        Returns:
            Result[dict[str, Any]]: Same as find_relevant_for_context()
        """
        return await self.find_relevant_for_context(
            active_goals=user_context.active_goal_uids,
            current_habits=list(user_context.habit_streaks.keys()),
            recent_choices=user_context.pending_choice_uids,
            pending_tasks=user_context.active_task_uids,
            active_principles=user_context.core_principle_uids,
            upcoming_events=user_context.upcoming_event_uids,
            max_results=max_results,
            min_relevance_score=min_relevance_score,
        )

    async def _find_knowledge_for_activity(
        self,
        activity_uid: str,
        activity_domain: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Find knowledge units connected to a specific activity.

        Uses graph traversal to find:
        - Knowledge REQUIRED by the activity
        - Knowledge that APPLIES to the activity
        - Knowledge that ENABLES the activity
        """
        if not self.graph_intel:
            return Result.ok([])

        # Map domain to relationship types
        relationship_map = {
            "goal": [
                RelationshipName.REQUIRES_KNOWLEDGE.value,
                RelationshipName.GUIDED_BY_KNOWLEDGE.value,
            ],
            "habit": [
                RelationshipName.APPLIES_KNOWLEDGE.value,
                RelationshipName.REINFORCED_BY_KNOWLEDGE.value,
            ],
            "task": [
                RelationshipName.APPLIES_KNOWLEDGE.value,
                RelationshipName.BLOCKED_BY_KNOWLEDGE.value,
            ],
            "choice": [RelationshipName.INFORMED_BY_KNOWLEDGE.value],
            "principle": [RelationshipName.GROUNDED_IN_KNOWLEDGE.value],
            "event": [RelationshipName.PRACTICES_KNOWLEDGE.value],
        }

        relationship_map.get(activity_domain, [RelationshipName.APPLIES_KNOWLEDGE.value])

        # Query graph for connected knowledge
        try:
            # Use graph intelligence for semantic context
            context_result = await self.graph_intel.get_semantic_context(
                entity_uid=activity_uid,
                depth=2,
            )

            if context_result.is_error:
                return Result.ok([])

            context = context_result.value or {}

            # Extract knowledge nodes from context
            knowledge_units = []
            nodes = context.get("nodes", [])

            for node in nodes:
                if node.get("label") in ["Entity", "KnowledgeUnit"]:
                    knowledge_units.append(
                        {
                            "uid": node.get("uid", ""),
                            "title": node.get("title", node.get("name", "")),
                            "domain": node.get("domain", ""),
                            "complexity": node.get("complexity", 0.5),
                        }
                    )

            return Result.ok(knowledge_units)

        except Exception as e:
            logger.warning(f"Failed to find knowledge for {activity_uid}: {e}")
            return Result.ok([])

    async def _order_by_prerequisites(
        self,
        ku_uids: list[str],
    ) -> list[str]:
        """
        Order knowledge units by prerequisite dependencies using topological sort.

        Returns UIDs in order that respects prerequisites
        (learn A before B if B requires A).

        Uses Kahn's algorithm for topological sorting with cycle detection.
        """
        if not ku_uids or not self.graph_intel:
            return ku_uids

        try:
            # Step 1: Build dependency graph from Neo4j
            query = """
            UNWIND $ku_uids AS ku_uid
            MATCH (ku:Entity {uid: ku_uid})
            OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
            WHERE prereq.uid IN $ku_uids
            RETURN ku.uid AS uid, collect(prereq.uid) AS prerequisites
            """

            result = await self.graph_intel.execute_query(query, parameters={"ku_uids": ku_uids})

            if result.is_error or not result.value:
                return ku_uids

            # Step 2: Build adjacency map (ku -> its prerequisites)
            prereq_map: dict[str, list[str]] = {uid: [] for uid in ku_uids}
            for record in result.value:
                uid = record.get("uid", "")
                prerequisites = record.get("prerequisites", [])
                if uid in prereq_map:
                    prereq_map[uid] = [p for p in prerequisites if p]

            # Step 3: Topological sort (Kahn's algorithm)
            # in_degree counts how many things depend on each uid
            in_degree: dict[str, int] = {uid: 0 for uid in ku_uids}
            for prereqs in prereq_map.values():
                for prereq in prereqs:
                    if prereq in in_degree:
                        in_degree[prereq] += 1

            # Start with nodes that nothing depends on (leaves in dependency tree)
            # These are the "foundational" knowledge that should be learned first
            queue = [uid for uid, degree in in_degree.items() if degree == 0]
            sorted_uids: list[str] = []

            while queue:
                current = queue.pop(0)
                sorted_uids.append(current)

                # Reduce in-degree for things that had current as prerequisite
                for uid, prereqs in prereq_map.items():
                    if current in prereqs:
                        in_degree[uid] -= 1
                        if in_degree[uid] == 0 and uid not in sorted_uids:
                            queue.append(uid)

            # Add any remaining nodes (handles cycles gracefully)
            remaining = [uid for uid in ku_uids if uid not in sorted_uids]
            sorted_uids.extend(remaining)

            return sorted_uids

        except Exception as e:
            logger.warning("Prerequisite ordering failed, returning original order: %s", e)
            return ku_uids

    # =========================================================================
    # PHASE 4: Schedule-Aware Recommendations
    # =========================================================================

    async def get_schedule_aware_recommendations(
        self,
        user_context: UserContext,
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
