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
- Curriculum Domains (4): ku, ps, lp, exercises
- Processing Domain (1): report
- Temporal Domain (1): calendar

**Usage:**
```python
# At bootstrap (services_bootstrap/_intelligence_hub.py)
factory = UserContextIntelligenceFactory(
    tasks=tasks_service,  # the facade, not .relationships
    goals=goals_service,
    # ... the other nine services
)
services.context_intelligence = factory

# At runtime (UserService) — the hub needs the RICH context
context_result = await user_service.get_rich_unified_context(user_uid)
if context_result.is_error:
    return Result.fail(context_result)
intelligence = factory.create(context_result.value)
plan = await intelligence.get_ready_to_work_on_today()
```
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from core.services.user.intelligence.core import UserContextIntelligence

if TYPE_CHECKING:
    from core.ports.curriculum_protocols import ExerciseOperations
    from core.ports.filtered_context_protocols import FilteredContextProvider
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.calendar_service import CalendarService
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.ku_service import KuService
    from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
    from core.services.principles_service import PrinciplesService
    from core.services.ps_service import PsService
    from core.services.relationships import UnifiedRelationshipService
    from core.services.report import ReportRelationshipService
    from core.services.tasks_service import TasksService
    from core.services.user.unified_user_context import RichUserContext


class _HubServices(TypedDict):
    """The twelve required services, keyed by `UserContextIntelligence.__init__`'s parameter names."""

    tasks: TasksService
    goals: GoalsService
    habits: HabitsService
    events: EventsService
    choices: ChoicesService
    principles: PrinciplesService
    ku: KuService
    ps: PsService
    lp: UnifiedRelationshipService
    exercises: ExerciseOperations
    report: ReportRelationshipService
    calendar: CalendarService


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
    - Curriculum Domains (4): ku, ps, lp, exercises
    - Processing Domain (1): report
    - Temporal Domain (1): calendar

    **Usage:**
    ```python
    # At bootstrap (services_bootstrap/_intelligence_hub.py)
    factory = UserContextIntelligenceFactory(
        tasks=tasks_service,  # the facade, not .relationships
        goals=goals_service,
        # ... the other nine services
    )
    services.context_intelligence = factory

    # At runtime (UserService) — the hub needs the RICH context
    context_result = await user_service.get_rich_unified_context(user_uid)
    if context_result.is_error:
        return Result.fail(context_result)
    intelligence = factory.create(context_result.value)
    plan = await intelligence.get_ready_to_work_on_today()
    ```
    """

    def __init__(
        self,
        # Activity Domains (6) - REQUIRED (concrete facade services)
        tasks: TasksService,
        goals: GoalsService,
        habits: HabitsService,
        events: EventsService,
        choices: ChoicesService,
        principles: PrinciplesService,
        # Curriculum Domains (4) - REQUIRED
        ku: KuService,
        ps: PsService,
        lp: UnifiedRelationshipService,
        exercises: ExerciseOperations,
        # Processing Domain (1) - REQUIRED
        report: ReportRelationshipService,
        # Temporal Domain (1) - REQUIRED
        calendar: CalendarService,
        # Optional: Vector search for semantic enhancements
        vector_search_service: Neo4jVectorSearchService | None = None,
        # Optional: ZPD service for curriculum-graph-aware path step ranking
        zpd_service: ZPDOperations | None = None,
        # Optional: FilteredContextProvider dict for on-demand domain-specific queries
        filtered_providers: dict[str, FilteredContextProvider] | None = None,
    ) -> None:
        """
        Initialize factory with all 12 required domain services.

        Args:
            Activity Domains (6) - Concrete facade services:
                tasks: TasksService facade
                goals: GoalsService facade
                habits: HabitsService facade
                events: EventsService facade
                choices: ChoicesService facade
                principles: PrinciplesService facade

            Curriculum Domains (4):
                ku: Ku service facade (the published titles a step carries)
                ps: PathStep service facade
                lp: Learning path relationship service
                exercises: ExerciseService facade

            Processing Domain (1):
                report: Report relationship service (pending submissions, completion rate)

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
        # a 13th service means one entry here and in `_HubServices` (plus the
        # matching __init__ param and the matching UserContextIntelligence.__init__
        # param). `_HubServices` keeps the forwarding type-checked.
        self._required_services: _HubServices = {
            # Activity Domains (6)
            "tasks": tasks,
            "goals": goals,
            "habits": habits,
            "events": events,
            "choices": choices,
            "principles": principles,
            # Curriculum Domains (4)
            "ku": ku,
            "ps": ps,
            "lp": lp,
            "exercises": exercises,
            # Processing Domain (1)
            "report": report,
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
