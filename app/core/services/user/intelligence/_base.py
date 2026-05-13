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
    from core.services.analytics_relationship_service import AnalyticsRelationshipService
    from core.services.calendar_service import CalendarService
    from core.services.report import ReportRelationshipService
    from core.services.user.unified_user_context import RichUserContext
    from core.services.user_entry import UserEntryRelationshipService


class IntelligenceMixinBase:
    """
    Shared attribute surface for UserContextIntelligence mixins.

    Mixins inherit from this so `self.context`, `self.tasks`, etc. resolve to
    consistent types. Concrete values are assigned in
    `UserContextIntelligence.__init__` — this base contributes annotations only.

    Activity / curriculum services are typed `Any` (boundary): the wiring in
    `services_bootstrap/_intelligence_hub.py` passes `.relationships`
    (UnifiedRelationshipService), while several call sites invoke planning
    methods that live on the parent facade. The shape is duck-typed at runtime;
    tightening it would surface a separate architectural issue beyond this
    base class.
    """

    # User state
    context: RichUserContext

    # Activity Domains (6) — boundary: duck-typed facade/relationships
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

    # Processing Domains (3)
    user_entries: UserEntryRelationshipService
    report: ReportRelationshipService
    analytics: AnalyticsRelationshipService

    # Temporal Domain (1)
    calendar: CalendarService

    # Optional services
    vector_search: Any  # boundary: Neo4jVectorSearchService (optional, duck-typed)
    zpd_service: Any  # boundary: ZPDOperations | None (optional, duck-typed)
    filtered_providers: dict[str, FilteredContextProvider]


__all__ = ["IntelligenceMixinBase"]
