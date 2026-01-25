"""
User Context Intelligence Factory
==================================

Factory for creating UserContextIntelligence instances.

This factory holds all 13 required domain services and creates
UserContextIntelligence instances when given a UserContext.

**Why a Factory?**
- UserContextIntelligence requires a context at construction
- The context is user-specific and built on-demand
- The 13 domain services are singletons (created once at bootstrap)
- Factory pattern separates service wiring from context binding

**The 13 Domains:**
- Activity Domains (6): tasks, goals, habits, events, choices, principles
- Curriculum Domains (3): ku, ls, lp
- Processing Domains (3): assignments, journals, reports
- Temporal Domain (1): calendar

**Usage:**
```python
# At bootstrap (services_bootstrap.py)
factory = UserContextIntelligenceFactory(
    tasks=tasks_service.relationships,
    goals=goals_service.relationships,
    # ... 11 more services
)
services.context_intelligence = factory

# At runtime (UserService)
context = await user_service.get_user_context(user_uid)
intelligence = factory.create(context)
plan = await intelligence.get_ready_to_work_on_today()
```
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.services.user.intelligence.core import UserContextIntelligence

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


class UserContextIntelligenceFactory:
    """
    Factory for creating UserContextIntelligence instances.

    This factory holds all 13 required domain services and creates
    UserContextIntelligence instances when given a UserContext.

    **Why a Factory?**
    - UserContextIntelligence requires a context at construction
    - The context is user-specific and built on-demand
    - The 13 domain services are singletons (created once at bootstrap)
    - Factory pattern separates service wiring from context binding

    **The 13 Domains:**
    - Activity Domains (6): tasks, goals, habits, events, choices, principles
    - Curriculum Domains (3): ku, ls, lp
    - Processing Domains (3): assignments, journals, reports
    - Temporal Domain (1): calendar

    **Usage:**
    ```python
    # At bootstrap (services_bootstrap.py)
    factory = UserContextIntelligenceFactory(
        tasks=tasks_service.relationships,
        goals=goals_service.relationships,
        # ... 11 more services
    )
    services.context_intelligence = factory

    # At runtime (UserService)
    context = await user_service.get_user_context(user_uid)
    intelligence = factory.create(context)
    plan = await intelligence.get_ready_to_work_on_today()
    ```
    """

    def __init__(
        self,
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
        Initialize factory with all 13 required domain services.

        Args:
            Activity Domains (6) - All UnifiedRelationshipService with domain configs:
                tasks: Tasks relationship service
                goals: Goals relationship service
                habits: Habits relationship service
                events: Events relationship service
                choices: Choices relationship service
                principles: Principles relationship service

            Curriculum Domains (3):
                ku: Knowledge unit graph service
                ls: Learning step relationship service
                lp: Learning path relationship service

            Processing Domains (3):
                assignments: Assignment relationship service
                journals: Journal relationship service (fire in the engine)
                reports: Report relationship service (report cards)

            Temporal Domain (1):
                calendar: Calendar service for schedule awareness

        Raises:
            ValueError: If any required service is None
        """
        required = {
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
                f"UserContextIntelligenceFactory requires all 13 domain services. "
                f"Missing: {', '.join(missing)}"
            )

        # Store services for creating intelligence instances
        # Activity domains (6)
        self._tasks = tasks
        self._goals = goals
        self._habits = habits
        self._events = events
        self._choices = choices
        self._principles = principles
        # Curriculum domains (3)
        self._ku = ku
        self._ls = ls
        self._lp = lp
        # Processing domains (3)
        self._assignments = assignments
        self._journals = journals
        self._reports = reports
        # Temporal domain (1)
        self._calendar = calendar

    def create(self, context: UserContext) -> UserContextIntelligence:
        """
        Create a UserContextIntelligence instance for the given context.

        Args:
            context: UserContext snapshot for a specific user

        Returns:
            UserContextIntelligence instance bound to the context
        """
        return UserContextIntelligence(
            context=context,
            # Activity domains (6)
            tasks=self._tasks,
            goals=self._goals,
            habits=self._habits,
            events=self._events,
            choices=self._choices,
            principles=self._principles,
            # Curriculum domains (3)
            ku=self._ku,
            ls=self._ls,
            lp=self._lp,
            # Processing domains (3)
            assignments=self._assignments,
            journals=self._journals,
            reports=self._reports,
            # Temporal domain (1)
            calendar=self._calendar,
        )


__all__ = ["UserContextIntelligenceFactory"]
