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

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties
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

        async def create(self, entity: Any) -> Result[Any]: ...

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
        every exchange reader keys on, so the linker's retitle reads it too.
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

        The same statement stamps the turn-in snapshot on the entry —
        ``turn_in_exercise_uid`` = the root's uid (the ``REVISES_EXERCISE``
        original, else the revision's ``original_exercise_uid``, else the
        target itself) and ``turn_in_exercise_title`` = that root's title
        as it reads now. The snapshot is the exchange key every GradeBook
        and thread read groups on; it outlives the exercise and its edges
        (Submit & Share arc R12). The returned model carries both values.
        """
        create_result = await self.create(entry)
        if create_result.is_error:
            return Result.fail(create_result)
        created: UserEntry = create_result.value

        link_query = f"""
        MATCH (entry:Entity {{uid: $entry_uid, entity_type: $entry_type}})
        MATCH (exercise:Entity {{uid: $exercise_uid}})
        WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (exercise)-[:{RelationshipName.REVISES_EXERCISE.value}]->(original:Entity {{entity_type: 'exercise'}})
        WITH entry, exercise, original
        SET entry.turn_in_exercise_uid = coalesce(original.uid, exercise.original_exercise_uid, exercise.uid),
            entry.turn_in_exercise_title = coalesce(original.title, exercise.title)
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
        RETURN entry.turn_in_exercise_uid AS turn_in_exercise_uid,
               entry.turn_in_exercise_title AS turn_in_exercise_title
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
        stamped = link_result.value[0]
        return Result.ok(
            replace(
                created,
                turn_in_exercise_uid=stamped.get("turn_in_exercise_uid"),
                turn_in_exercise_title=stamped.get("turn_in_exercise_title"),
            )
        )
