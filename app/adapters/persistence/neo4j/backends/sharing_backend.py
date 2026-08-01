"""SharingBackend — cross-entity sharing relationships."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.entity import Entity
from core.models.type_hints import EntityUID, Neo4jProperties, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.report_schedule import ReportSchedule  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401


class SharingBackend(UniversalNeo4jBackend[Entity]):
    """
    Domain backend for cross-domain sharing operations.

    All sharing queries target :Entity nodes by UID — there are no domain-specific
    predicates. Typed to Entity (the base class) since sharing spans all entity types.

    Moves sharing Cypher from the service layer into the persistence boundary,
    following the same pattern as PsBackend (ORGANIZES), LpBackend (progress),
    and ExerciseBackend (curriculum linking).

    See: /docs/patterns/SHARING_PATTERNS.md
    """

    async def create_share(
        self,
        entity_uid: EntityUID,
        recipient_uid: str,
        role: str,
        share_version: str,
        shared_at: str,
    ) -> Result[list[Neo4jProperties]]:
        """Create SHARES_WITH relationship from recipient to entity."""
        result = await self.execute_query(
            """
            MATCH (recipient:User {uid: $recipient_uid})
            MATCH (ku:Entity {uid: $entity_uid})
            MERGE (recipient)-[r:SHARES_WITH]->(ku)
            SET r.shared_at = datetime($shared_at),
                r.role = $role,
                r.share_version = $share_version
            RETURN true as success
            """,
            {
                "recipient_uid": recipient_uid,
                "entity_uid": entity_uid,
                "shared_at": shared_at,
                "role": role,
                "share_version": share_version,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def delete_share(
        self,
        entity_uid: EntityUID,
        recipient_uid: str,
    ) -> Result[list[Neo4jProperties]]:
        """Delete SHARES_WITH relationship between recipient and entity."""
        result = await self.execute_query(
            """
            MATCH (recipient:User {uid: $recipient_uid})-[r:SHARES_WITH]->(ku:Entity {uid: $entity_uid})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"recipient_uid": recipient_uid, "entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def update_visibility(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        visibility: str,
    ) -> Result[list[Neo4jProperties]]:
        """Set visibility property on an owned entity."""
        result = await self.execute_query(
            """
            MATCH (ku:Entity {uid: $entity_uid})
            WHERE ku.user_uid = $owner_uid
            SET ku.visibility = $visibility,
                ku.updated_at = datetime()
            RETURN ku.uid as uid
            """,
            {
                "entity_uid": entity_uid,
                "owner_uid": owner_uid,
                "visibility": visibility,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_access(
        self,
        entity_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[list[Neo4jProperties]]:
        """Query ownership, visibility, and share relationships for access check."""
        result = await self.execute_query(
            """
            MATCH (ku:Entity {uid: $entity_uid})
            OPTIONAL MATCH (viewer:User {uid: $user_uid})-[:SHARES_WITH]->(ku)
            OPTIONAL MATCH (viewer2:User {uid: $user_uid})-[:MEMBER_OF]->(g:Group)<-[:SHARED_WITH_GROUP]-(ku)
            RETURN ku.user_uid as owner_uid,
                   ku.visibility as visibility,
                   ku.entity_type as entity_type,
                   count(viewer) > 0 as has_direct_share,
                   count(viewer2) > 0 as has_group_share
            """,
            {"entity_uid": entity_uid, "user_uid": user_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_shareable_status(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]:
        """Query status and entity_type for shareability check."""
        result = await self.execute_query(
            """
            MATCH (ku:Entity {uid: $entity_uid})
            RETURN ku.status as status, ku.entity_type as entity_type
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_ownership_and_status(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]:
        """Query ownership and status for combined ownership + shareable check.

        Ownership lives in two shapes: user-owned domains stamp a ``user_uid``
        property; curriculum entities (e.g. Exercise) stamp ``owner_uid`` and
        dual-write the canonical ``:OWNS`` edge (edge write is warn-only, so
        property-without-edge can exist). Resolve user_uid → owner_uid → edge,
        mirroring ``verify_ownership`` in crud_operations_mixin — the two
        layers must agree on who owns a node. Neither → unowned, unshareable.
        """
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})
            OPTIONAL MATCH (owner:User)-[:OWNS]->(entity)
            RETURN coalesce(entity.user_uid, entity.owner_uid, owner.uid) as actual_owner,
                   entity.status as status,
                   entity.entity_type as entity_type
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_shared_with_users(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]:
        """Get users an entity is shared with."""
        result = await self.execute_query(
            """
            MATCH (user:User)-[r:SHARES_WITH]->(ku:Entity {uid: $entity_uid})
            RETURN user.uid as user_uid,
                   user.name as user_name,
                   r.role as role,
                   r.share_version as share_version,
                   r.shared_at as shared_at
            ORDER BY r.shared_at DESC
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_shared_with_me(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Get entities shared with a user via direct SHARES_WITH, with subject context.

        ``shared_by`` resolves the entity creator's display name — the sharer
        is not recorded on the edge, but every current writer (ADR-040
        auto-share, form-submission share) shares the entity its creator made.
        ``toString`` normalizes ``shared_at`` (temporal on all writers) to an
        ISO string.

        The ``subject_*`` columns resolve what the shared item is about (C4,
        feedback-loop UX arc): an EntryReport's subject exercise via its
        submission (``REPORT_FOR`` → ``FULFILLS_EXERCISE``), a
        RevisedExercise's original via ``REVISES_EXERCISE``, and the PathStep
        anchoring that exercise via ``HAS_EXERCISE``. Pattern comprehensions —
        an item with no subject yields ``null`` columns, never a dropped or
        duplicated row.
        """
        result = await self.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[r:SHARES_WITH]->(entity:Entity)
            OPTIONAL MATCH (sharer:User {uid: entity.created_by})
            WITH entity, r, sharer,
                 coalesce(
                     head([(entity)-[:REPORT_FOR]->(:Entity)-[:FULFILLS_EXERCISE]->(ex:Entity) | ex]),
                     head([(entity)-[:REVISES_EXERCISE]->(ex:Entity) | ex])
                 ) AS subject_ex
            WITH entity, r, sharer, subject_ex,
                 head([(ps:Entity)-[:HAS_EXERCISE]->(subject_ex) | ps]) AS subject_ps
            RETURN entity,
                   r.role as role,
                   toString(r.shared_at) as shared_at,
                   r.share_version as share_version,
                   coalesce(sharer.display_name, sharer.title, entity.created_by) as shared_by,
                   subject_ex.uid as subject_exercise_uid,
                   subject_ex.title as subject_exercise_title,
                   subject_ps.uid as subject_ps_uid,
                   subject_ps.title as subject_ps_title
            ORDER BY r.shared_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def create_group_share(
        self,
        entity_uid: EntityUID,
        owner_uid: UserUID,
        group_uid: str,
        share_version: str,
        shared_at: str,
    ) -> Result[list[Neo4jProperties]]:
        """Create SHARED_WITH_GROUP relationship, guarded by owner relationship.

        The sharer must either OWN the target group (teacher sharing curriculum
        with their own class) or be MEMBER_OF it (student sharing a
        UserEntry with a group they belong to). Without either edge the
        ``OPTIONAL MATCH`` collapses and the ``WHERE`` predicate rejects the
        row — callers translate the empty result into a forbidden error,
        preventing users from sharing to groups they have no relationship to.
        """
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})
            MATCH (group:Group {uid: $group_uid})
            WHERE coalesce(group.is_active, true) = true
            OPTIONAL MATCH (owner:User {uid: $owner_uid})-[:MEMBER_OF]->(group)
              WHERE coalesce(owner.is_active, true) = true
            OPTIONAL MATCH (owner2:User {uid: $owner_uid})-[:OWNS]->(group)
              WHERE coalesce(owner2.is_active, true) = true
            WITH entity, group, owner, owner2
            WHERE owner IS NOT NULL OR owner2 IS NOT NULL
            MERGE (entity)-[r:SHARED_WITH_GROUP]->(group)
              ON CREATE SET r.shared_at = datetime($shared_at),
                            r.share_version = $share_version
            RETURN true as success
            """,
            {
                "entity_uid": entity_uid,
                "owner_uid": owner_uid,
                "group_uid": group_uid,
                "shared_at": shared_at,
                "share_version": share_version,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_exercise_groups_for_member(
        self,
        exercise_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[list[Neo4jProperties]]:
        """Return the groups the exercise is shared with AND the user belongs to.

        Used for auto-share scoping: when a submission fulfills an exercise
        that was assigned to multiple groups, only fan out to the ones the
        submitter is actually in.
        """
        result = await self.execute_query(
            """
            MATCH (ex:Entity {uid: $exercise_uid})-[:SHARED_WITH_GROUP]->(g:Group)
            WHERE coalesce(g.is_active, true) = true
            MATCH (u:User {uid: $user_uid})-[:MEMBER_OF]->(g)
            WHERE coalesce(u.is_active, true) = true
            RETURN g.uid AS group_uid
            """,
            {"exercise_uid": exercise_uid, "user_uid": user_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_default_groups_for_curriculum_submission(
        self,
        exercise_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[list[Neo4jProperties]]:
        """Fallback review route for CURRICULUM exercises: the submitter's default group(s).

        Curriculum exercises are vault-authored and never ASSIGNED to a group,
        so the assignment-intersection auto-share resolves to nothing and a
        teacher_review submission would dissolve unseen. Ruled 2026-07-04:
        such submissions share with the submitter's default group (the
        ``group_default_{admin_uid}`` group every enrolled student auto-joins,
        owned by the default teacher). Scope-gated in Cypher: a non-curriculum
        exercise returns zero rows, so PERSONAL submissions can never leak to
        the default group through this path.
        """
        result = await self.execute_query(
            """
            MATCH (ex:Entity {uid: $exercise_uid})
            WHERE ex.entity_type = 'exercise' AND ex.scope = 'curriculum'
            MATCH (u:User {uid: $user_uid})-[:MEMBER_OF]->(g:Group)
            WHERE g.uid STARTS WITH 'group_default_'
              AND coalesce(g.is_active, true) = true
            RETURN g.uid AS group_uid
            """,
            {"exercise_uid": exercise_uid, "user_uid": user_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_user_can_use_exercise(
        self,
        exercise_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[bool]:
        """Verify the user has a legitimate relationship to an exercise.

        True if any hold:
          - user owns the exercise (teacher previewing their own)
          - exercise is SHARED_WITH_GROUP with a group the user is a member of
          - exercise is linked to a PathStep the user is currently in progress on

        Prevents YAML uploads from smuggling ``fulfills_exercise_uid`` values
        for exercises the uploader has no legitimate tie to.
        """
        result = await self.execute_query(
            """
            MATCH (ex:Entity {uid: $exercise_uid})
            OPTIONAL MATCH (ex)-[:SHARED_WITH_GROUP]->(g:Group)<-[:MEMBER_OF]-(:User {uid: $user_uid})
            OPTIONAL MATCH (:User {uid: $user_uid})-[:IN_PROGRESS]->(ps:Entity)-[:HAS_EXERCISE]->(ex)
            WITH ex.user_uid = $user_uid AS is_owner,
                 count(g) > 0 AS via_group,
                 count(ps) > 0 AS via_progress
            RETURN (is_owner OR via_group OR via_progress) AS allowed
            """,
            {"exercise_uid": exercise_uid, "user_uid": user_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(False)
        return Result.ok(bool(records[0].get("allowed")))

    async def query_entity_owner(
        self,
        entity_uid: EntityUID,
    ) -> Result[str | None]:
        """Return the ``user_uid`` of an entity's owner, or None if missing."""
        result = await self.execute_query(
            """
            MATCH (e:Entity {uid: $entity_uid})
            RETURN e.user_uid AS owner_uid
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        owner = records[0].get("owner_uid")
        return Result.ok(str(owner) if owner is not None else None)

    async def delete_group_share(
        self,
        entity_uid: EntityUID,
        group_uid: str,
    ) -> Result[list[Neo4jProperties]]:
        """Delete SHARED_WITH_GROUP relationship."""
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})-[r:SHARED_WITH_GROUP]->(group:Group {uid: $group_uid})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"entity_uid": entity_uid, "group_uid": group_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_groups_shared_with(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]:
        """Get groups an entity is shared with."""
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})-[r:SHARED_WITH_GROUP]->(group:Group)
            RETURN group.uid as group_uid,
                   group.name as group_name,
                   r.share_version as share_version,
                   r.shared_at as shared_at
            ORDER BY r.shared_at DESC
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_shared_with_me_via_groups(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Get entities shared with a user through group membership."""
        result = await self.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:MEMBER_OF]->(group:Group)
            MATCH (entity:Entity)-[r:SHARED_WITH_GROUP]->(group)
            WHERE entity.user_uid <> $user_uid
            RETURN entity,
                   group.uid as group_uid,
                   group.name as group_name,
                   r.share_version as share_version,
                   r.shared_at as shared_at
            ORDER BY entity.created_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_user_entries_shared_with_group(
        self,
        user_uid: UserUID,
        group_uid: str,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Get UserEntries shared with a specific group the user belongs to.

        The first MATCH is also the membership guard — if the user is not in
        the group, no rows are returned (empty result, not an error). Own
        entries are excluded so students see peer work, not their own. The
        `group.is_active = true` predicate keeps deactivated groups from
        leaking peer content to a still-MEMBER_OF viewer who URL-types the
        old group UID.
        """
        result = await self.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:MEMBER_OF]->(group:Group {uid: $group_uid})
            WHERE group.is_active = true
            MATCH (entry:UserEntry)-[r:SHARED_WITH_GROUP]->(group)
            WHERE entry.user_uid <> $user_uid
            OPTIONAL MATCH (author:User {uid: entry.user_uid})
            RETURN entry,
                   coalesce(author.display_name, author.title) AS author_name,
                   r.share_version as share_version,
                   r.shared_at as shared_at
            ORDER BY r.shared_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "group_uid": group_uid, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_user_entry_shared_with_group(
        self,
        user_uid: UserUID,
        group_uid: str,
        entry_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]:
        """Fetch a single peer UserEntry iff the viewer can see it via this group.

        Access is granted only when all three hold:
        - viewer is MEMBER_OF the group
        - entry is SHARED_WITH_GROUP with the group
        - viewer is not the entry's owner (this is the peer-view surface;
          owners read their own entries via /gradebook/{uid})

        Any mismatch returns an empty list — no partial data, no oracle for
        UID enumeration.
        """
        result = await self.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:MEMBER_OF]->(group:Group {uid: $group_uid})
            WHERE group.is_active = true
            MATCH (entry:UserEntry {uid: $entry_uid})-[r:SHARED_WITH_GROUP]->(group)
            WHERE entry.user_uid <> $user_uid
            OPTIONAL MATCH (author:User {uid: entry.user_uid})
            RETURN entry,
                   group.name AS group_name,
                   coalesce(author.display_name, author.title) AS author_name,
                   r.share_version AS share_version,
                   r.shared_at AS shared_at
            LIMIT 1
            """,
            {
                "user_uid": user_uid,
                "group_uid": group_uid,
                "entry_uid": entry_uid,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])
