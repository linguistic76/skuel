"""
UserEntry Lifecycle Mixin — ADR-054 Step 4
===========================================

Thin wrapper over ``_SubmissionLifecycleMixin`` exposing the method names
declared by ``UserEntryLifecycleOperations``. Adds
``create_with_exercise_link`` — a new method that carries ``revision`` on
the ``FULFILLS_EXERCISE`` edge (the old design stored ``revision_number``
on the submission node).

Additive through Step 13 — the legacy lifecycle mixin and its
``link_to_exercise`` (no-revision) method stay in place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j._submission_lifecycle_mixin import (
    _SubmissionLifecycleMixin,
)
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.user_entry.user_entry import UserEntry

_USER_ENTRY = EntityType.USER_ENTRY.value


class _UserEntryLifecycleMixin(_SubmissionLifecycleMixin):
    """Lifecycle wrappers for ``UserEntry``.

    Inherited from ``_SubmissionLifecycleMixin``:
        get_exercise_context, verify_student_group_membership,
        create_temporal_relationship, create_thematic_relationships,
        get_submission_relationship_summary, get_related_submission_uids,
        get_supported_goal_uids, get_submission_owner

    See ``UserEntryBackend`` in ``backends/user_entry_backend.py`` for the
    composed class.
    """

    if TYPE_CHECKING:

        async def create(self, entity: Any) -> Result[Any]:  # from UniversalNeo4jBackend
            ...

    # ------------------------------------------------------------------
    # Wrapper renames (submission -> entry terminology)
    # ------------------------------------------------------------------

    async def get_entry_owner(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Student UID who owns an entry."""
        return await self.get_submission_owner(submission_uid=entry_uid)

    async def get_related_entry_uids(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """UIDs of entries related via RELATED_TO."""
        return await self.get_related_submission_uids(ku_uid=entry_uid)

    async def get_entry_relationship_summary(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Per-entry relationship counts (related, goals, follows)."""
        return await self.get_submission_relationship_summary(ku_uid=entry_uid)

    # ------------------------------------------------------------------
    # NEW — atomic create + FULFILLS_EXERCISE with revision on the edge
    # ------------------------------------------------------------------

    async def create_with_exercise_link(
        self,
        entry: UserEntry,
        exercise_uid: str,
        revision: int,
    ) -> Result[UserEntry]:
        """Create a ``UserEntry`` and link it to an exercise atomically.

        Writes ``(:Entity:UserEntry)-[:FULFILLS_EXERCISE {revision}]->(:Exercise)``.
        For a ``RevisedExercise`` target, additionally writes
        ``FULFILLS_REVISED_EXERCISE`` to the revision node while anchoring
        ``FULFILLS_EXERCISE`` on the root ``Exercise``.

        The node is persisted first (via ``UniversalNeo4jBackend.create``),
        then the edge is MERGEd with the revision property. This matches
        the pattern used by ``SubmissionsService.process_exercise_submission``
        pre-migration and preserves the invariant that ``FULFILLS_EXERCISE``
        always points to the root exercise.
        """
        create_result = await self.create(entry)
        if create_result.is_error:
            return Result.fail(create_result)
        created: UserEntry = create_result.value  # type: ignore[assignment]

        link_query = f"""
        MATCH (entry:Entity {{uid: $entry_uid, entity_type: $entry_type}})
        MATCH (exercise:Entity {{uid: $exercise_uid}})
        WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (exercise)-[:{RelationshipName.REVISES_EXERCISE.value}]->(original:Entity {{entity_type: 'exercise'}})
        WITH entry, exercise, original
        FOREACH (_ IN CASE WHEN original IS NOT NULL THEN [1] ELSE [] END |
          MERGE (entry)-[r1:{RelationshipName.FULFILLS_EXERCISE.value}]->(original)
            ON CREATE SET r1.revision = $revision
            ON MATCH SET r1.revision = $revision
          MERGE (entry)-[r2:{RelationshipName.FULFILLS_REVISED_EXERCISE.value}]->(exercise)
            ON CREATE SET r2.revision = $revision
            ON MATCH SET r2.revision = $revision
        )
        FOREACH (_ IN CASE WHEN original IS NULL THEN [1] ELSE [] END |
          MERGE (entry)-[r3:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise)
            ON CREATE SET r3.revision = $revision
            ON MATCH SET r3.revision = $revision
        )
        RETURN true AS success
        """
        link_result = await self.execute_query(
            link_query,
            {
                "entry_uid": created.uid,
                "entry_type": _USER_ENTRY,
                "exercise_uid": exercise_uid,
                "revision": revision,
            },
        )
        if link_result.is_error:
            return Result.fail(link_result)
        if not link_result.value:
            return Result.fail(
                Errors.not_found(
                    resource="Exercise",
                    identifier=exercise_uid,
                )
            )
        return Result.ok(created)

    async def create_entry_temporal_link(
        self, entry_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Create FOLLOWS to the previous user entry by this user.

        Named distinctly from the inherited ``create_temporal_relationship``
        (3-arg) to avoid an LSP conflict.
        """
        return await self.create_temporal_relationship(
            ku_uid=entry_uid,
            user_uid=user_uid,
            entity_type=_USER_ENTRY,
        )

    async def create_entry_thematic_links(
        self,
        entry_uid: str,
        user_uid: UserUID,
        themes: list[str],
        shared_topics_str: str,
    ) -> Result[list[Neo4jProperties]]:
        """Create RELATED_TO edges for entries sharing topics."""
        return await self.create_thematic_relationships(
            ku_uid=entry_uid,
            user_uid=user_uid,
            themes=themes,
            shared_topics_str=shared_topics_str,
        )
