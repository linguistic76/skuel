"""
UserEntry Content Enrichment Mixin — ADR-054 Step 4
====================================================

Wrapper over ``_SubmissionContentMixin`` exposing the method names
declared by ``UserEntryContentOperations``. The journal-flavored methods
are inherited as-is — the legacy Cypher already filters on
``entity_type = 'exercise_submission'`` for the journal context subquery;
that is the correct target for the legacy path. Post-migration cleanup
(Step 14+) will retarget those queries to ``user_entry`` + pipeline
filters.
"""

from __future__ import annotations

from adapters.persistence.neo4j._submission_content_mixin import _SubmissionContentMixin
from core.models.enums.entity_enums import EntityType
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result

_USER_ENTRY = EntityType.USER_ENTRY.value


class _UserEntryContentMixin(_SubmissionContentMixin):
    """Content enrichment wrappers for ``UserEntry``.

    Inherited unchanged from ``_SubmissionContentMixin``:
        get_journal_processing_context, get_recent_journal_entries,
        get_active_goals_for_user, get_recent_journal_topics,
        create_journal_temporal_link, create_journal_thematic_links,
        create_journal_goal_links, load_exercise_instructions,
        create_exercise_instruction_set, list_exercise_instruction_sets,
        create_goal_support_relationships

    See ``UserEntryBackend`` in ``backends/user_entry_backend.py`` for the
    composed class.
    """

    async def get_entries_for_path_step(
        self,
        user_uid: UserUID,
        ps_uid: str,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Entries for a path step via ``Interaction`` edges."""
        return await self.get_submissions_for_path_step(
            user_uid=user_uid,
            ps_uid=ps_uid,
            submission_type=_USER_ENTRY,
            limit=limit,
        )
