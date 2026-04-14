"""
UserEntry Report Query Mixin — ADR-054 Step 4
==============================================

Wrapper over ``_SubmissionReportQueryMixin`` exposing the method names
declared by ``UserEntryReportQueryOperations``. Filters on
``EntityType.USER_ENTRY`` instead of the legacy ``exercise_submission``
string, so post-migration loop chain queries find only the new type.
"""

from __future__ import annotations

from adapters.persistence.neo4j._submission_report_query_mixin import (
    _SubmissionReportQueryMixin,
)
from core.models.enums.entity_enums import EntityType
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result

_USER_ENTRY = EntityType.USER_ENTRY.value


class _UserEntryReportQueryMixin(_SubmissionReportQueryMixin):
    """Report-relationship cross-joins for ``UserEntry``.

    Inherited unchanged from ``_SubmissionReportQueryMixin``:
        get_unsubmitted_exercises_raw, get_learning_loop_chain_raw,
        get_submission_chain_raw, get_admin_uid

    See ``UserEntryBackend`` in ``backends/user_entry_backend.py`` for the
    composed class.
    """

    async def get_pending_entries_raw(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Entries without an incoming ``REPORT_FOR`` relationship."""
        return await self.get_pending_submissions_raw(
            user_uid=user_uid,
            submission_types=[_USER_ENTRY],
        )

    async def get_entry_report_summary_raw(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Aggregate report completion counts across user's entries."""
        return await self.get_report_summary_raw(
            user_uid=user_uid,
            submission_types=[_USER_ENTRY],
        )

    async def get_entry_chain_raw(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Loop chain rooted at a specific entry."""
        return await self.get_submission_chain_raw(submission_uid=entry_uid)
