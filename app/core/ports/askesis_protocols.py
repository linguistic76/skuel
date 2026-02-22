"""
Askesis Cross-Cutting Intelligence Protocols
=============================================

Protocol interfaces for SKUEL's Askesis service - the life context synthesis
and action recommendation system.

Askesis is a CROSS-CUTTING SYSTEM (not a standard domain) that synthesizes
all 14 domains to answer: "What should I work on next?"

Unlike domain protocols that inherit from BackendOperations[T], Askesis protocols
define high-level intelligence operations that span multiple domains.

Protocol Categories
-------------------
- AskesisOperations: Main intelligence interface (14 methods)
- AskesisStateAnalysisOperations: State assessment methods
- AskesisRecommendationOperations: Action recommendation methods
- AskesisQueryOperations: Natural language query processing

Usage
-----
    from core.ports import AskesisOperations

    def get_recommendations(askesis: AskesisOperations) -> Result[...]:
        return await askesis.get_next_best_action(user_context)

Architecture Note (January 2026)
--------------------------------
AskesisOperations is intentionally different from domain protocols:
- Does NOT inherit from BackendOperations (no entity CRUD)
- REQUIRES UserContextIntelligenceFactory (13-domain synthesis)
- Returns complex analysis/recommendation types (not entities)

See Also:
    /core/services/askesis_service.py - Main implementation
    /core/services/askesis/ - Sub-service implementations
    /docs/intelligence/ASKESIS_INTELLIGENCE.md - Full documentation
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.models.context_types import (
        CrossDomainSynergy,
        DailyWorkPlan,
        LearningStep,
        LifePathAlignment,
        ScheduleAwareRecommendation,
    )
    from core.services.askesis.types import (
        AskesisAnalysis,
        AskesisInsight,
        AskesisRecommendation,
    )
    from core.services.user import UserContext
    from core.utils.result_simplified import Result


@runtime_checkable
class AskesisStateAnalysisOperations(Protocol):
    """State analysis operations for user context assessment.

    These methods analyze the current state across all domains to identify
    patterns, health metrics, and areas needing attention.
    """

    async def analyze_user_state(
        self, user_context: UserContext, focus_areas: list[str] | None = None
    ) -> Result[AskesisAnalysis]:
        """Perform comprehensive analysis of user's state across all domains.

        Args:
            user_context: Complete user context (~240 fields)
            focus_areas: Optional specific areas to focus on

        Returns:
            Result[AskesisAnalysis]: Comprehensive analysis with insights,
                recommendations, and health metrics
        """
        ...

    async def identify_patterns(self, user_context: UserContext) -> Result[list[AskesisInsight]]:
        """Identify patterns in user's behavior and progress.

        Detects:
        - Productivity patterns (time of day, day of week)
        - Learning patterns (concept clusters, prerequisite chains)
        - Behavioral patterns (habit formation, streak maintenance)

        Args:
            user_context: User's complete context

        Returns:
            Result[list[AskesisInsight]]: Detected patterns with confidence scores
        """
        ...

    def calculate_system_health(self, user_context: UserContext) -> dict[str, float]:
        """Calculate health metrics for each domain.

        Returns scores (0.0-1.0) for:
        - tasks_health: Task completion rate, blocker ratio
        - habits_health: Streak maintenance, at-risk habits
        - goals_health: Progress toward milestones
        - knowledge_health: Learning velocity, mastery rate
        - life_path_alignment: Overall alignment with life path

        Args:
            user_context: User's complete context

        Returns:
            Dict of domain names to health scores (0.0-1.0)
        """
        ...


@runtime_checkable
class AskesisRecommendationOperations(Protocol):
    """Action recommendation operations for next-best-action guidance.

    These methods generate prioritized recommendations based on the user's
    current state, goals, and cross-domain synthesis.
    """

    async def get_next_best_action(
        self, user_context: UserContext
    ) -> Result[AskesisRecommendation]:
        """Get THE single best action to take right now.

        Priority hierarchy:
        1. At-risk habits (prevent streak loss)
        2. Unblocking (if stuck on tasks/learning)
        3. Goal advancement (milestone progress)
        4. Foundation building (knowledge acquisition)

        Args:
            user_context: User's complete context

        Returns:
            Result[AskesisRecommendation]: Single best action with reasoning
        """
        ...

    async def optimize_workflow(self, user_context: UserContext) -> Result[list[dict[str, Any]]]:
        """Generate workflow optimization suggestions.

        Analyzes current workflow and suggests improvements:
        - Task batching opportunities
        - Habit stacking suggestions
        - Knowledge application opportunities
        - Schedule optimization

        Args:
            user_context: User's complete context

        Returns:
            Result[list[dict]]: Workflow optimization suggestions
        """
        ...

    async def predict_future_state(
        self, user_context: UserContext, days_ahead: int = 7
    ) -> Result[dict[str, Any]]:
        """Predict user's state trajectory.

        Projects:
        - Goal completion likelihood
        - Habit streak projections
        - Learning path progress
        - Potential blockers

        Args:
            user_context: User's complete context
            days_ahead: Number of days to project (default: 7)

        Returns:
            Result[dict]: State predictions with confidence intervals
        """
        ...


@runtime_checkable
class AskesisQueryOperations(Protocol):
    """Natural language query processing operations.

    These methods handle RAG-based query answering with entity extraction
    and context-aware response generation.
    """

    async def answer_user_question(self, user_uid: str, question: str) -> Result[dict[str, Any]]:
        """Answer a natural language question about user's state.

        Full RAG pipeline:
        1. Intent classification (learning, tasks, goals, etc.)
        2. Entity extraction (specific items mentioned)
        3. Context retrieval (relevant domain data)
        4. Response generation (LLM-powered answer)

        Args:
            user_uid: User's unique identifier
            question: Natural language question

        Returns:
            Result[dict]: Answer with entities, sources, and confidence
        """
        ...

    async def process_query_with_context(
        self, user_uid: str, query_message: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """Process query with full user context.

        Combines UserContext with graph traversal for comprehensive answers.

        Args:
            user_uid: User's unique identifier
            query_message: Natural language query
            depth: Graph traversal depth (default: 2)

        Returns:
            Result[dict]: Context-aware response with graph enrichment
        """
        ...


@runtime_checkable
class AskesisDomainSynthesisOperations(Protocol):
    """13-Domain synthesis operations for cross-cutting intelligence.

    These are THE flagship methods that synthesize all 14 domains to provide
    comprehensive life context intelligence.

    Requires: UserContextIntelligenceFactory (wired at construction)
    """

    async def get_daily_work_plan(
        self,
        user_context: UserContext,
        prioritize_life_path: bool = True,
        respect_capacity: bool = True,
    ) -> Result[DailyWorkPlan]:
        """Get THE optimal work plan for TODAY.

        THE FLAGSHIP METHOD - synthesizes all 14 domains to answer:
        "What should I focus on today?"

        Considers:
        - At-risk habits (critical priority)
        - Scheduled events (immovable)
        - High-priority tasks (contextual)
        - Learning opportunities (life path aligned)
        - Goal milestones (progress-driven)
        - Principle alignment (value-guided)

        Args:
            user_context: Complete user context (~240 fields)
            prioritize_life_path: Weight life path alignment (default: True)
            respect_capacity: Limit recommendations to capacity (default: True)

        Returns:
            Result[DailyWorkPlan]: Prioritized daily work plan
        """
        ...

    async def get_optimal_next_learning_steps(
        self,
        user_context: UserContext,
        max_steps: int = 5,
        consider_goals: bool = True,
        consider_capacity: bool = True,
    ) -> Result[list[LearningStep]]:
        """Get optimal next learning steps based on prerequisites and goals.

        Analyzes:
        - Prerequisite completion status
        - Goal-aligned learning opportunities
        - Capacity constraints
        - Life path alignment

        Args:
            user_context: Complete user context
            max_steps: Maximum steps to return (default: 5)
            consider_goals: Include goal alignment (default: True)
            consider_capacity: Respect learning capacity (default: True)

        Returns:
            Result[list[LearningStep]]: Prioritized learning steps
        """
        ...

    async def get_learning_path_critical_path(self, user_context: UserContext) -> Result[list[str]]:
        """Get the critical path to life path alignment.

        Calculates the shortest sequence of learning steps that maximizes
        life path alignment, considering current mastery state.

        Args:
            user_context: Complete user context

        Returns:
            Result[list[str]]: Ordered list of KU UIDs on critical path
        """
        ...

    async def get_knowledge_application_opportunities(
        self, user_context: UserContext, ku_uid: str
    ) -> Result[dict[str, list[str]]]:
        """Find where knowledge can be applied across Activity Domains.

        Maps KU to opportunities in:
        - Tasks (APPLIES_KNOWLEDGE)
        - Goals (REQUIRES_KNOWLEDGE)
        - Habits (REINFORCES_KNOWLEDGE)
        - Events (PRACTICES_KNOWLEDGE)
        - Choices (INFORMED_BY_KNOWLEDGE)
        - Principles (GROUNDED_IN_KNOWLEDGE)

        Args:
            user_context: Complete user context
            ku_uid: Knowledge Unit to find applications for

        Returns:
            Result[dict]: Domain → list of entity UIDs that can apply this KU
        """
        ...

    async def get_unblocking_priority_order(
        self, user_context: UserContext
    ) -> Result[list[tuple[str, int]]]:
        """Get learning order that unlocks the most downstream items.

        Calculates which KUs to learn first based on how many tasks, goals,
        and other items they unblock.

        Args:
            user_context: Complete user context

        Returns:
            Result[list[tuple]]: (ku_uid, unlock_count) ordered by impact
        """
        ...

    async def get_cross_domain_synergies(
        self,
        user_context: UserContext,
        min_synergy_score: float = 0.3,
        include_types: list[str] | None = None,
    ) -> Result[list[CrossDomainSynergy]]:
        """Detect synergies across domains.

        Identifies powerful combinations:
        - Habit → Goal alignment
        - Task → Habit stacking
        - Knowledge → Task application
        - Principle → Goal guidance

        Args:
            user_context: Complete user context
            min_synergy_score: Minimum score to include (default: 0.3)
            include_types: Filter to specific synergy types

        Returns:
            Result[list[CrossDomainSynergy]]: Detected synergies with scores
        """
        ...

    async def calculate_life_path_alignment(
        self, user_context: UserContext
    ) -> Result[LifePathAlignment]:
        """Calculate comprehensive life path alignment score.

        5-dimension scoring:
        - Knowledge alignment (25%): Is learning on-track for life path?
        - Activity alignment (25%): Are tasks/habits serving life path?
        - Goal alignment (20%): Are goals life path-connected?
        - Principle alignment (15%): Are values life path-congruent?
        - Momentum (15%): Is progress accelerating or stalling?

        Args:
            user_context: Complete user context

        Returns:
            Result[LifePathAlignment]: Alignment score with dimension breakdown
        """
        ...

    async def get_schedule_aware_recommendations(
        self,
        user_context: UserContext,
        max_recommendations: int = 5,
        time_horizon_hours: int = 8,
        respect_energy: bool = True,
    ) -> Result[list[ScheduleAwareRecommendation]]:
        """Get recommendations that respect schedule and energy.

        The right action at the right time:
        - Considers upcoming events
        - Respects energy patterns
        - Accounts for task duration
        - Avoids scheduling conflicts

        Args:
            user_context: Complete user context
            max_recommendations: Maximum to return (default: 5)
            time_horizon_hours: Look-ahead window (default: 8)
            respect_energy: Consider energy patterns (default: True)

        Returns:
            Result[list[ScheduleAwareRecommendation]]: Time-appropriate recommendations
        """
        ...


@runtime_checkable
class AskesisOperations(
    AskesisStateAnalysisOperations,
    AskesisRecommendationOperations,
    AskesisQueryOperations,
    AskesisDomainSynthesisOperations,
    Protocol,
):
    """Complete Askesis intelligence operations protocol.

    Composes all Askesis sub-protocols:
    - AskesisStateAnalysisOperations (3 methods)
    - AskesisRecommendationOperations (3 methods)
    - AskesisQueryOperations (2 methods)
    - AskesisDomainSynthesisOperations (8 methods)

    Total: 16 methods for comprehensive life context intelligence.

    Implementation: AskesisService (facade with 5 sub-services)

    Example:
        def recommend_actions(askesis: AskesisOperations) -> Result[...]:
            # State analysis
            analysis = await askesis.analyze_user_state(context)

            # Get THE best action
            action = await askesis.get_next_best_action(context)

            # 13-domain synthesis
            plan = await askesis.get_daily_work_plan(context)

            return Result.ok(plan)
    """

    pass


@runtime_checkable
class AskesisCoreOperations(Protocol):
    """CRUD operations for Askesis instances.

    Separate from AskesisOperations (intelligence) — this handles the
    lifecycle management of Askesis entities.

    Implementation: AskesisCoreService
    """

    async def get_or_create_for_user(self, user_uid: str) -> Result[Any]: ...

    async def create_askesis(self, user_uid: str, create_request: Any) -> Result[Any]: ...

    async def get_askesis(self, askesis_uid: str) -> Result[Any]: ...

    async def update_askesis(self, askesis_uid: str, update_request: Any) -> Result[Any]: ...

    async def record_conversation(self, askesis_uid: str) -> Result[Any]: ...


# Convenience aliases for focused dependencies (ISP)
StateAnalysis = AskesisStateAnalysisOperations
Recommendations = AskesisRecommendationOperations
QueryProcessing = AskesisQueryOperations
DomainSynthesis = AskesisDomainSynthesisOperations
