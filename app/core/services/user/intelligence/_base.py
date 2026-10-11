"""
Intelligence Mixin Base
========================

Single declaration site for the shared attribute surface used by every
UserContextIntelligence mixin.

Mixins inherit from this class so attribute access inside mixin methods
(`self.context`, `self.tasks`, ...) type-checks against the same shape declared
on `UserContextIntelligence.__init__` in `core.py`. Adding a new domain service
to UserContextIntelligence requires updating this one base class — mixins no
longer carry their own shadow declarations that can drift independently.

See: `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md`
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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


class IntelligenceMixinBase:
    """
    Shared attribute surface for UserContextIntelligence mixins.

    Mixins inherit from this so `self.context`, `self.tasks`, etc. resolve to
    consistent types. Concrete values are assigned in
    `UserContextIntelligence.__init__` — this base contributes annotations only.

    The services carry the types `UserContextIntelligence.__init__` takes — the
    concrete facades, and `ExerciseOperations` for the exercises service (the
    protocol the services container holds it as) — imported under `TYPE_CHECKING`
    only: no runtime import fan, and MyPy checks every mixin body against them.
    """

    # User state
    context: RichUserContext

    # Activity Domains (6)
    tasks: TasksService
    goals: GoalsService
    habits: HabitsService
    events: EventsService
    choices: ChoicesService
    principles: PrinciplesService

    # Curriculum Domains (4)
    ku: KuService
    ps: PsService
    lp: UnifiedRelationshipService
    exercises: ExerciseOperations  # ExerciseService — daily-plan exercise enrichment

    # Processing Domain (1)
    report: ReportRelationshipService

    # Temporal Domain (1)
    calendar: CalendarService

    # Optional services
    vector_search: Neo4jVectorSearchService | None
    zpd_service: ZPDOperations | None
    filtered_providers: dict[str, FilteredContextProvider]


__all__ = ["IntelligenceMixinBase"]
