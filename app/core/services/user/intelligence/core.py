"""
User Context Intelligence - Core Class
=======================================

THE CORE VALUE PROPOSITION: "What should I work on next?"

This service implements the 5+ critical methods that embody SKUEL's core
purpose - helping users understand where they are in their learning journey
and determining what to work on next.

**Architecture:**
UserContextIntelligence = UserContext + 13 Domain Services
                        = User State + Complete Graph Intelligence

**The 13 Domains (Symmetric Architecture):**

    Activity Domains (6 pairs):
    - Tasks + Events: What to do / When to do it
    - Goals + Habits: Where heading / How to sustain
    - Choices + Principles: Decisions made / Values guiding

    Curriculum Domains (3):
    - KU (KnowledgeUnits): Atomic knowledge content
    - LS (LearningSteps): Learning sequences
    - LP (LearningPaths): Complete learning journeys

    Processing Domains (2 pairs):
    - Assignments + Reports: Student submits / System reflects (like report cards)
    - Journals: The "fire in the engine" - where reflection happens

    Temporal Domain (1):
    - Calendar: When everything happens (schedule-aware intelligence)

**The 8 Core Methods (via mixins):**
1. get_optimal_next_learning_steps() - What should I learn next?
2. get_learning_path_critical_path() - Fastest route to life path?
3. get_knowledge_application_opportunities() - Where can I apply this?
4. get_unblocking_priority_order() - What unlocks the most?
5. get_ready_to_work_on_today() - THE FLAGSHIP - What's optimal for TODAY?
6. get_cross_domain_synergies() - Cross-domain synergy detection
7. calculate_life_path_alignment() - Life path alignment scoring
8. get_schedule_aware_recommendations() - Schedule-aware recommendations

Version: 4.0.0 (Refactored to mixin architecture)
Date: January 2026
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.services.user.intelligence.daily_planning import DailyPlanningMixin
from core.services.user.intelligence.learning_intelligence import LearningIntelligenceMixin
from core.services.user.intelligence.life_path_intelligence import LifePathIntelligenceMixin
from core.services.user.intelligence.schedule_intelligence import ScheduleIntelligenceMixin
from core.services.user.intelligence.synergy_intelligence import SynergyIntelligenceMixin

if TYPE_CHECKING:
    from core.services.assignments import AssignmentRelationshipService
    from core.services.calendar_service import CalendarService
    from core.services.journals import JournalRelationshipService
    from core.services.ku.ku_graph_service import KuGraphService

    # LpRelationshipService deleted - LP now uses UnifiedRelationshipService
    # LsRelationshipService deleted - LS now uses UnifiedRelationshipService
    from core.services.relationships import UnifiedRelationshipService
    from core.services.report_relationship_service import ReportRelationshipService
    from core.services.user.unified_user_context import UserContext


class UserContextIntelligence(
    LearningIntelligenceMixin,
    LifePathIntelligenceMixin,
    SynergyIntelligenceMixin,
    ScheduleIntelligenceMixin,
    DailyPlanningMixin,
):
    """
    Learning journey intelligence = Context + 13 Domain Services.

    **Architecture:**
    This service synthesizes user state (UserContext) with graph
    intelligence (13 domain services) to answer: "What should I work on?"

    **Required Dependencies (13 domains):**

    Activity Domains (6) - All use UnifiedRelationshipService with domain configs:
    - tasks: UnifiedRelationshipService - What can I do now?
    - goals: UnifiedRelationshipService - What goals need attention?
    - habits: UnifiedRelationshipService - What streaks are at risk?
    - events: UnifiedRelationshipService - What's scheduled?
    - choices: UnifiedRelationshipService - What decisions await?
    - principles: UnifiedRelationshipService - What values guide this?

    Curriculum Domains (3):
    - ku: KuGraphService - What knowledge is ready?
    - ls: UnifiedRelationshipService - Learning step relationships (unified)
    - lp: UnifiedRelationshipService - Critical path to life path (unified)

    Processing Domains (3):
    - assignments: AssignmentRelationshipService - Student submissions
    - journals: JournalRelationshipService - Reflection (fire in the engine)
    - reports: ReportRelationshipService - System feedback (report cards)

    Temporal Domain (1):
    - calendar: CalendarService - Schedule-aware intelligence

    **Philosophy:**
    SKUEL runs at full capacity or not at all. All 13 domains are REQUIRED
    because each contributes unique intelligence to the daily planning.
    The symmetric domain architecture reflects the complete educational
    support system.

    **Mixin Architecture:**
    This class composes functionality from specialized mixins:
    - LearningIntelligenceMixin: Methods 1-4 (learning steps, critical path)
    - LifePathIntelligenceMixin: Method 7 (life path alignment)
    - SynergyIntelligenceMixin: Method 6 (cross-domain synergies)
    - ScheduleIntelligenceMixin: Method 8 (schedule-aware recommendations)
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
        ku: KuGraphService,
        ls: UnifiedRelationshipService,  # January 2026: Unified
        lp: UnifiedRelationshipService,  # January 2026: Unified
        # Processing Domains (3) - REQUIRED
        assignments: AssignmentRelationshipService,
        journals: JournalRelationshipService,
        reports: ReportRelationshipService,
        # Temporal Domain (1) - REQUIRED
        calendar: CalendarService,
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
                ku: Knowledge unit service for learning readiness
                ls: Learning step service for step sequencing
                lp: Learning path service for critical path analysis

            Processing Domains (3):
                assignments: Assignment relationship service for student work
                journals: Journal relationship service (fire in the engine)
                reports: Report relationship service for report cards

            Temporal Domain (1):
                calendar: Calendar service for schedule-aware intelligence

        Raises:
            ValueError: If any required service is None
        """
        # Validate all required dependencies (12 entity domains + 1 meta-service)
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
            "ku": ku,
            "ls": ls,
            "lp": lp,
            # Processing Domains (3)
            "assignments": assignments,
            "journals": journals,
            "reports": reports,
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
        self.ku = ku
        self.ls = ls
        self.lp = lp

        # Processing domains (3)
        self.assignments = assignments
        self.journals = journals
        self.reports = reports

        # Temporal domain (1)
        self.calendar = calendar


__all__ = ["UserContextIntelligence"]
