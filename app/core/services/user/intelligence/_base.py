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

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.filtered_context_protocols import FilteredContextProvider
    from core.services.calendar_service import CalendarService
    from core.services.report import ReportRelationshipService
    from core.services.user.unified_user_context import RichUserContext


class IntelligenceMixinBase:
    """
    Shared attribute surface for UserContextIntelligence mixins.

    Mixins inherit from this so `self.context`, `self.tasks`, etc. resolve to
    consistent types. Concrete values are assigned in
    `UserContextIntelligence.__init__` — this base contributes annotations only.

    Activity services are typed `Any` (boundary): the constructor parameter types
    are declared as concrete facades (TasksService, GoalsService, etc.) in
    `UserContextIntelligence.__init__`, so MyPy validates call sites there. The
    base class uses `Any` to avoid importing 6 concrete facades into this shared
    module, which would widen the import fan and risk cycles.
    """

    # User state
    context: RichUserContext

    # Activity Domains (6) — boundary: concrete facades at init, Any here avoids import fan
    tasks: Any
    goals: Any
    habits: Any
    events: Any
    choices: Any
    principles: Any

    # Curriculum Domains (3) — boundary: duck-typed (PsService facade / UnifiedRelationshipService / ExerciseService facade)
    ps: Any
    lp: Any
    exercises: Any  # ExerciseService facade — daily-plan exercise enrichment

    # Processing Domain (1)
    report: ReportRelationshipService

    # Temporal Domain (1)
    calendar: CalendarService

    # Optional services
    vector_search: Any  # boundary: Neo4jVectorSearchService (optional, duck-typed)
    zpd_service: Any  # boundary: ZPDOperations | None (optional, duck-typed)
    filtered_providers: dict[str, FilteredContextProvider]


__all__ = ["IntelligenceMixinBase"]
