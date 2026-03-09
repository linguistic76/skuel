"""
User Context Intelligence - Core Class
=======================================

THE CORE VALUE PROPOSITION: "What should I work on next?"

This service implements the 5+ critical methods that embody SKUEL's core
purpose - helping users understand where they are in their learning journey
and determining what to work on next.

**Architecture:**
UserContextIntelligence = UserContext + Domain Services
                        = User State + Complete Graph Intelligence

**Entity Types:**

    Activity (6): Tasks, Goals, Habits, Events, Choices, Principles
    Curriculum: Article, Ku, LearningStep, LearningPath, Exercise
    Curated Content: Resource
    Content processing: Submission, Journal, ActivityReport, SubmissionReport
    Destination: LifePath
    Cross-cutting: Calendar, Analytics, Report

**The 8 Core Methods (via mixins):**
1. get_optimal_next_learning_steps() - What should I learn next?
2. get_learning_path_critical_path() - Fastest route to life path?
3. get_knowledge_application_opportunities() - Where can I apply this?
4. get_unblocking_priority_order() - What unlocks the most?
5. get_ready_to_work_on_today() - THE FLAGSHIP - What's optimal for TODAY?
6. get_cross_domain_synergies() - Cross-domain synergy detection
7. calculate_life_path_alignment() - Life path alignment scoring
8. get_schedule_aware_recommendations() - Schedule-aware recommendations
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.services.user.intelligence.daily_planning import DailyPlanningMixin
from core.services.user.intelligence.learning_intelligence import LearningIntelligenceMixin
from core.services.user.intelligence.life_path_intelligence import LifePathIntelligenceMixin
from core.services.user.intelligence.schedule_intelligence import ScheduleIntelligenceMixin
from core.services.user.intelligence.synergy_intelligence import SynergyIntelligenceMixin
from core.services.user.intelligence.temporal_momentum import TemporalMomentumMixin

if TYPE_CHECKING:
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.analytics_relationship_service import AnalyticsRelationshipService
    from core.services.article.article_graph_service import ArticleGraphService
    from core.services.calendar_service import CalendarService

    # LpRelationshipService deleted - LP now uses UnifiedRelationshipService
    # LsRelationshipService deleted - LS now uses UnifiedRelationshipService
    from core.services.report import ReportRelationshipService
    from core.services.relationships import UnifiedRelationshipService
    from core.services.submissions import SubmissionsRelationshipService
    from core.services.user.unified_user_context import UserContext


class UserContextIntelligence(
    LearningIntelligenceMixin,
    LifePathIntelligenceMixin,
    SynergyIntelligenceMixin,
    ScheduleIntelligenceMixin,
    TemporalMomentumMixin,
    DailyPlanningMixin,
):
    """
    Learning journey intelligence = Context + 13 Domain Services.

    **Architecture:**
    This service synthesizes user state (UserContext) with graph
    intelligence (13 domain services) to answer: "What should I work on?"

    **Required Dependencies (entity types):**

    Activity Domains (6) - All use UnifiedRelationshipService with domain configs:
    - tasks: UnifiedRelationshipService - What can I do now?
    - goals: UnifiedRelationshipService - What goals need attention?
    - habits: UnifiedRelationshipService - What streaks are at risk?
    - events: UnifiedRelationshipService - What's scheduled?
    - choices: UnifiedRelationshipService - What decisions await?
    - principles: UnifiedRelationshipService - What values guide this?

    Curriculum Domains (3):
    - article: ArticleGraphService - What knowledge is ready?
    - ls: UnifiedRelationshipService - Learning step relationships (unified)
    - lp: UnifiedRelationshipService - Critical path to life path (unified)

    Processing Domains (3):
    - submissions: SubmissionsRelationshipService - Student submissions + journals
    - feedback: ReportRelationshipService - Report loop graph queries
    - analytics: AnalyticsRelationshipService - Cross-domain analytics

    Temporal Domain (1):
    - calendar: CalendarService - Schedule-aware intelligence

    **Philosophy:**
    SKUEL runs at full capacity or not at all. all entity types are REQUIRED
    because each contributes unique intelligence to the daily planning.
    The symmetric domain architecture reflects the complete educational
    support system.

    **Mixin Architecture:**
    This class composes functionality from specialized mixins:
    - LearningIntelligenceMixin: Methods 1-4 (learning steps, critical path)
    - LifePathIntelligenceMixin: Method 7 (life path alignment)
    - SynergyIntelligenceMixin: Method 6 (cross-domain synergies)
    - ScheduleIntelligenceMixin: Method 8 (schedule-aware recommendations)
    - TemporalMomentumMixin: compute_momentum_signals() (entities_rich analysis)
    - DailyPlanningMixin: Method 5 (daily work plan - THE FLAGSHIP)

    Context-based queries (get_ready_to_learn, etc.) are now accessed directly
    via UserContext methods for simplicity and "One Path Forward" alignment.
    """

    def __init__(
        self,
        context: UserContext,
        # Activity Domains (6) - REQUIRED (UnifiedRelationshipService with domain configs)
        tasks: UnifiedRelationshipService,
        goals: UnifiedRelationshipService,
        habits: UnifiedRelationshipService,
        events: UnifiedRelationshipService,
        choices: UnifiedRelationshipService,
        principles: UnifiedRelationshipService,
        # Curriculum Domains (3) - REQUIRED
        article: ArticleGraphService,
        ls: UnifiedRelationshipService,  # January 2026: Unified
        lp: UnifiedRelationshipService,  # January 2026: Unified
        # Processing Domains (3) - REQUIRED
        submissions: SubmissionsRelationshipService,
        feedback: ReportRelationshipService,
        analytics: AnalyticsRelationshipService,
        # Temporal Domain (1) - REQUIRED
        calendar: CalendarService,
        # Optional: Vector search for semantic enhancements
        vector_search: Any = None,
        # Optional: ZPD service for curriculum-graph-aware learning step ranking
        zpd_service: ZPDOperations | None = None,
    ) -> None:
        """
        Initialize with user context and all 13 required relationship services.

        Args:
            context: Complete UserContext snapshot (~240 fields)

            Activity Domains (6) - All UnifiedRelationshipService with domain configs:
                tasks: Tasks relationship service for actionable tasks
                goals: Goals relationship service for advancing goals
                habits: Habits relationship service for at-risk habits
                events: Events relationship service for upcoming events
                choices: Choices relationship service for pending decisions
                principles: Principles relationship service for value alignment

            Curriculum Domains (3):
                article: Article service for learning readiness
                ls: Learning step service for step sequencing
                lp: Learning path service for critical path analysis

            Processing Domains (3):
                submissions: Submission relationship service (student work + journals)
                feedback: Report relationship service (pending submissions, completion rate)
                analytics: Analytics relationship service (cross-domain)

            Temporal Domain (1):
                calendar: Calendar service for schedule-aware intelligence

            Optional Services:
                vector_search: Neo4jVectorSearchService for semantic/learning-aware search
                zpd_service: ZPDOperations for curriculum-graph-aware step ranking

        Raises:
            ValueError: If any required service is None
        """
        # Validate all required dependencies
        required = {
            "context": context,
            # Activity Domains (6)
            "tasks": tasks,
            "goals": goals,
            "habits": habits,
            "events": events,
            "choices": choices,
            "principles": principles,
            # Curriculum Domains (3)
            "article": article,
            "ls": ls,
            "lp": lp,
            # Processing Domains (3)
            "submissions": submissions,
            "feedback": feedback,
            "analytics": analytics,
            # Temporal Domain (1)
            "calendar": calendar,
        }

        missing = [name for name, service in required.items() if service is None]
        if missing:
            raise ValueError(
                f"UserContextIntelligence requires all 13 domain services. "
                f"Missing: {', '.join(missing)}"
            )

        # User state
        self.context = context

        # Activity domains (6)
        self.tasks = tasks
        self.goals = goals
        self.habits = habits
        self.events = events
        self.choices = choices
        self.principles = principles

        # Curriculum domains (3)
        self.article = article
        self.ls = ls
        self.lp = lp

        # Processing domains (3)
        self.submissions = submissions
        self.feedback = feedback
        self.analytics = analytics

        # Temporal domain (1)
        self.calendar = calendar

        # Optional: Vector search for semantic enhancements
        self.vector_search = vector_search

        # Optional: ZPD service for curriculum-graph-aware learning step ranking.
        # When set, get_optimal_next_learning_steps() uses ZPD proximal zone + readiness
        # scores as the primary ranking signal (fallback: activity-based algorithm).
        # See: core/services/zpd/zpd_service.py, core/ports/zpd_protocols.py
        self.zpd_service = zpd_service


__all__ = ["UserContextIntelligence"]
