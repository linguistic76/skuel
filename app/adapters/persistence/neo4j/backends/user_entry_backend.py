"""
UserEntryBackend — persistence layer for the unified ``UserEntry`` domain.

Composes five mixins over ``UniversalNeo4jBackend[UserEntry]``. Each mixin
is a thin subclass of its ``_Submission*Mixin`` counterpart, rewritten to
expose entry-flavored method names and adding the two genuinely new
operations:

    _UserEntryLifecycleMixin.create_with_exercise_link   — revision on edge
    _UserEntryAssessmentMixin.get_review_queue_by_groups — SHARED_WITH_GROUP

The legacy ``SubmissionsBackend`` and its ``_Submission*Mixin`` files stay
in place through Step 13; this backend is additive.

See: /home/mike/.claude/plans/woolly-weaving-hejlsberg.md (ADR-054)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j._user_entry_assessment_mixin import (
    _UserEntryAssessmentMixin,
)
from adapters.persistence.neo4j._user_entry_content_mixin import _UserEntryContentMixin
from adapters.persistence.neo4j._user_entry_crud_mixin import _UserEntryCrudMixin
from adapters.persistence.neo4j._user_entry_lifecycle_mixin import (
    _UserEntryLifecycleMixin,
)
from adapters.persistence.neo4j._user_entry_report_query_mixin import (
    _UserEntryReportQueryMixin,
)
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.user_entry.user_entry import UserEntry

if TYPE_CHECKING:
    from typing import Any

    from neo4j import AsyncDriver


class UserEntryBackend(  # type: ignore[misc]  # Mixin MRO overrides are intentional
    _UserEntryCrudMixin,
    _UserEntryLifecycleMixin,
    _UserEntryAssessmentMixin,
    _UserEntryReportQueryMixin,
    _UserEntryContentMixin,
    UniversalNeo4jBackend[UserEntry],
):
    """Domain backend for ``UserEntry`` — the unified user-authored content type.

    Writes ``(:Entity:UserEntry)`` via multi-label CREATE. Satisfies
    ``core.ports.user_entry_protocols.UserEntryOperations`` — the composed
    backend-facing protocol consumed by ``UserEntryService`` (Step 5).
    """

    def __init__(
        self,
        driver: AsyncDriver,
        *,
        graph_intel: Any | None = None,
        prometheus_metrics: Any | None = None,
    ) -> None:
        super().__init__(
            driver=driver,
            label=NeoLabel.USER_ENTRY,
            entity_class=UserEntry,
            graph_intel=graph_intel,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
