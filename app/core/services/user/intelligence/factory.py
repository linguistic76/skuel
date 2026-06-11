"""
User Context Intelligence Factory
==================================

Factory for creating UserContextIntelligence instances.

This factory holds all 12 required domain services and creates
UserContextIntelligence instances when given a UserContext.

**Why a Factory?**
- UserContextIntelligence requires a context at construction
- The context is user-specific and built on-demand
- The 12 domain services are singletons (created once at bootstrap)
- Factory pattern separates service wiring from context binding

**Entity Types:**
- Activity Domains (6): tasks, goals, habits, events, choices, principles
- Curriculum Domains (3): ps, lp, exercises
- Processing Domains (2): report, analytics
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

from typing import TYPE_CHECKING, Any

from core.services.user.intelligence.core import UserContextIntelligence

if TYPE_CHECKING:
    from core.ports.filtered_context_protocols import FilteredContextProvider
    from core.ports.relationship_backend_protocols import AnalyticsRelationshipOperations
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.calendar_service import CalendarService
    from core.services.ps_service import PsService
    from core.services.relationships import UnifiedRelationshipService
    from core.services.report import ReportRelationshipService
    from core.services.user.unified_user_context import RichUserContext


class UserContextIntelligenceFactory:
    """
    Factory for creating UserContextIntelligence instances.

    This factory holds all 12 required domain services and creates
    UserContextIntelligence instances when given a UserContext.

    **Why a Factory?**
    - UserContextIntelligence requires a context at construction
    - The context is user-specific and built on-demand
    - The 12 domain services are singletons (created once at bootstrap)
    - Factory pattern separates service wiring from context binding

    **Entity Types:**
    - Activity Domains (6): tasks, goals, habits, events, choices, principles
    - Curriculum Domains (3): ps, lp, exercises
    - Processing Domains (2): report, analytics
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
        ps: PsService,
        lp: UnifiedRelationshipService,  # January 2026: Unified
        exercises: Any,  # ExerciseService facade — get_actionable_exercises_for_user / get_pending_revisions_for_user
        # Processing Domains (2) - REQUIRED
        report: ReportRelationshipService,
        analytics: AnalyticsRelationshipOperations,
        # Temporal Domain (1) - REQUIRED
        calendar: CalendarService,
        # Optional: Vector search for semantic enhancements
        vector_search_service: Any = None,
        # Optional: ZPD service for curriculum-graph-aware path step ranking
        zpd_service: ZPDOperations | None = None,
        # Optional: FilteredContextProvider dict for on-demand domain-specific queries
        filtered_providers: dict[str, FilteredContextProvider] | None = None,
    ) -> None:
        """
        Initialize factory with all 12 required domain services.

        Args:
            Activity Domains (6) - All UnifiedRelationshipService with domain configs:
                tasks: Tasks relationship service
                goals: Goals relationship service
                habits: Habits relationship service
                events: Events relationship service
                choices: Choices relationship service
                principles: Principles relationship service

            Curriculum Domains (3):
                ps: PathStep service facade
                lp: Learning path relationship service
                exercises: ExerciseService facade

            Processing Domains (2):
                report: Report relationship service (pending submissions, completion rate)
                analytics: Analytics relationship service (cross-domain)

            Temporal Domain (1):
                calendar: Calendar service for schedule awareness

            Optional:
                vector_search_service: Neo4jVectorSearchService for semantic/learning-aware search
                zpd_service: ZPDOperations for curriculum-graph-aware step ranking
                filtered_providers: Dict mapping domain names to FilteredContextProvider facades.
                    Enables intelligence services to call get_filtered_context() on any domain.

        Raises:
            ValueError: If any required service is None
        """
        # Single source of truth for the 12 required services. Both validation
        # and forwarding to UserContextIntelligence read from this dict — adding
        # a 14th service means one entry here (plus the matching __init__ param
        # and the matching UserContextIntelligence.__init__ param).
        self._required_services: dict[str, Any] = {
            # Activity Domains (6)
            "tasks": tasks,
            "goals": goals,
            "habits": habits,
            "events": events,
            "choices": choices,
            "principles": principles,
            # Curriculum Domains (3)
            "ps": ps,
            "lp": lp,
            "exercises": exercises,
            # Processing Domains (2)
            "report": report,
            "analytics": analytics,
            # Temporal Domain (1)
            "calendar": calendar,
        }

        missing = [name for name, service in self._required_services.items() if service is None]
        if missing:
            raise ValueError(
                f"UserContextIntelligenceFactory requires all "
                f"{len(self._required_services)} domain services. "
                f"Missing: {', '.join(missing)}"
            )

        self._vector_search = vector_search_service
        self._zpd_service = zpd_service
        self._filtered_providers = filtered_providers or {}

    def create(self, context: RichUserContext) -> UserContextIntelligence:
        """
        Create a UserContextIntelligence instance for the given context.

        Args:
            context: RichUserContext snapshot for a specific user. Must be rich —
                the intelligence mixins consume rich-only fields that the standard
                UserContext does not expose.

        Returns:
            UserContextIntelligence instance bound to the context
        """
        return UserContextIntelligence(
            context=context,
            **self._required_services,
            vector_search=self._vector_search,
            zpd_service=self._zpd_service,
            filtered_providers=self._filtered_providers,
        )


__all__ = ["UserContextIntelligenceFactory"]
