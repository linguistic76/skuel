"""
UserEntry Lifecycle Mixin
=========================

Exercise entry processing, FULFILLS_EXERCISE linking, and revision-chain
queries.

Consolidated from the legacy ``_SubmissionLifecycleMixin`` into a single
standalone mixin (ADR-054).

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties
from core.utils.error_boundary import safe_backend_operation
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel
    from core.models.user_entry.user_entry import UserEntry

_USER_ENTRY = EntityType.USER_ENTRY.value


class _UserEntryLifecycleMixin:
    """Lifecycle operations for ``UserEntry``.

    See ``UserEntryBackend`` in ``backends/user_entry_backend.py`` for the
    composed class.
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: NeoLabel

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[list[dict[str, Any]]]: ...

        async def _create_node(
            self,
            entity: UserEntry,
            operation: str,
            match_clause: str = "",
            extra_cypher: str = "",
            params: Neo4jProperties | None = None,
            failure_message: str | None = None,
        ) -> Result[UserEntry]: ...

    # ========================================================================
    # EXERCISE CONTEXT
    # ========================================================================

    async def get_exercise_context(self, exercise_uid: str) -> Result[list[Neo4jProperties]]:
        """Get exercise scope, teacher, group info for submission processing."""
        query = """
        MATCH (exercise:Entity {uid: $exercise_uid})
        WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (teacher:User)-[:OWNS]->(exercise)
        OPTIONAL MATCH (exercise)-[:SHARED_WITH_GROUP]->(g:Group)
        OPTIONAL MATCH (exercise)-[:REVISES_EXERCISE]->(original:Entity {entity_type: 'exercise'})
        RETURN exercise.entity_type as exercise_entity_type,
               exercise.scope as scope,
               COALESCE(teacher.uid, exercise.user_uid) as teacher_uid,
               exercise.student_uid as student_uid,
               exercise.title as exercise_title,
               g.uid as group_uid,
               original.uid as original_exercise_uid
        """
        return await self.execute_query(query, {"exercise_uid": exercise_uid})

    # ========================================================================
    # OWNERSHIP & GROUP MEMBERSHIP
    # ========================================================================

    async def get_entry_owner(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Student UID who owns an entry, with the entry's turn-in snapshot title.

        ``turn_in_exercise_title`` is the root exercise's title as stamped at
        submission (null on an entry that is not a turn-in) — the one title
        every exchange reader keys on.
        """
        query = """
        MATCH (student:User)-[:OWNS]->(entry:Entity {uid: $entry_uid})
        RETURN student.uid as student_uid,
               entry.turn_in_exercise_title AS turn_in_exercise_title
        """
        return await self.execute_query(query, {"entry_uid": entry_uid})

    async def verify_student_group_membership(
        self, entry_uid: str, group_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Check student owns entry AND is member of group."""
        query = """
        MATCH (student:User)-[:OWNS]->(entry:Entity {uid: $entry_uid})
        OPTIONAL MATCH (student)-[:MEMBER_OF]->(g:Group {uid: $group_uid})
        RETURN student.uid as student_uid, g.uid as member_of_group
        """
        return await self.execute_query(query, {"entry_uid": entry_uid, "group_uid": group_uid})

    # ========================================================================
    # EXERCISE LINKING
    # ========================================================================

    @safe_backend_operation("create_with_exercise_link")
    async def create_with_exercise_link(
        self,
        entry: UserEntry,
        exercise_uid: str,
    ) -> Result[UserEntry]:
        """Create a ``UserEntry`` linked to an exercise, minting its revision.

        One statement writes the node, its owner edge and
        ``(:Entity:UserEntry)-[:FULFILLS_EXERCISE {revision}]->(:Exercise)`` —
        all of them or none. For a ``RevisedExercise`` target it additionally
        writes ``FULFILLS_REVISED_EXERCISE`` to the revision node while
        anchoring ``FULFILLS_EXERCISE`` on the root ``Exercise``.

        The revision is decided by the write: one more than the highest
        revision among the owner's entries already fulfilling the root, read
        under the root's write-lock, so two concurrent turn-ins of one
        (owner, exercise) pair never share an ordinal. It is the highest, not
        a count — a deleted entry leaves a gap, and a count would mint an
        ordinal a surviving entry already carries.

        The same statement stamps the turn-in snapshot on the entry —
        ``turn_in_exercise_uid`` = the root's uid (the ``REVISES_EXERCISE``
        original, else the revision's ``original_exercise_uid``, else the
        target itself), ``turn_in_exercise_title`` = that root's title at the
        time of the write, and ``turn_in_revision`` = the minted revision. The
        snapshot is the exchange key every GradeBook and thread read groups
        on; it outlives the exercise and its edges (Submit & Share arc R12).
        An entry handed in with an empty title is titled from the snapshot,
        "<root title> v<revision>"; a title the student typed is kept (the
        PR 7 ruling). The returned model carries the stamped values.

        A target that is not an exercise is a not-found, and nothing is written.
        """
        fulfills = RelationshipName.FULFILLS_EXERCISE.value
        fulfills_revised = RelationshipName.FULFILLS_REVISED_EXERCISE.value
        # The SET takes the root's write-lock before the prior revisions are read,
        # and every clause after it runs under that lock: a concurrent turn-in on
        # the same root waits here and then reads this one's committed edge. A
        # unique token keeps it a real property write; the sentinel is removed in
        # the same statement.
        match_clause = f"""
        MATCH (exercise:Entity {{uid: $exercise_uid}})
        WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (exercise)-[:{RelationshipName.REVISES_EXERCISE.value}]->(original:Entity {{entity_type: 'exercise'}})
        WITH exercise, original, coalesce(original, exercise) AS root
        SET root.`_turn_in_lock` = $turn_in_lock
        WITH exercise, original, root
        OPTIONAL MATCH (:User {{uid: $turn_in_owner_uid}})-[:{RelationshipName.OWNS.value}]->(prior:Entity {{entity_type: $entry_type}})-[fulfilled:{fulfills}]->(root)
        WITH exercise, original, root,
             coalesce(max(coalesce(fulfilled.revision, prior.turn_in_revision)), 0) + 1 AS revision
        REMOVE root.`_turn_in_lock`
        WITH exercise, original, revision
        """
        extra_cypher = f"""
        SET n.turn_in_exercise_uid = coalesce(original.uid, exercise.original_exercise_uid, exercise.uid),
            n.turn_in_exercise_title = coalesce(original.title, exercise.title),
            n.turn_in_revision = revision,
            n.title = CASE
              WHEN coalesce(n.title, '') = ''
              THEN coalesce(original.title, exercise.title, '') + ' v' + toString(revision)
              ELSE n.title
            END
        FOREACH (_ IN CASE WHEN original IS NOT NULL THEN [1] ELSE [] END |
          CREATE (n)-[:{fulfills} {{revision: revision}}]->(original)
          CREATE (n)-[:{fulfills_revised} {{revision: revision}}]->(exercise)
        )
        FOREACH (_ IN CASE WHEN original IS NULL THEN [1] ELSE [] END |
          CREATE (n)-[:{fulfills} {{revision: revision}}]->(exercise)
        )
        """
        created = await self._create_node(
            entry,
            "create_with_exercise_link",
            match_clause=match_clause,
            extra_cypher=extra_cypher,
            params={
                "exercise_uid": exercise_uid,
                "entry_type": _USER_ENTRY,
                "turn_in_owner_uid": entry.user_uid,
                "turn_in_lock": uuid4().hex,
            },
        )
        if created.is_ok:
            return created

        # Nothing was written. Name the missing exercise when that is why.
        exercise_check = await self.execute_query(
            """
            MATCH (exercise:Entity {uid: $exercise_uid})
            WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
            RETURN exercise.uid AS uid
            """,
            {"exercise_uid": exercise_uid},
        )
        if exercise_check.is_ok and not exercise_check.value:
            return Result.fail(Errors.not_found(resource="Exercise", identifier=exercise_uid))
        return created
