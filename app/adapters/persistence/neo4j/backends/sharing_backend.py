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
        """Query ownership and status for combined ownership + shareable check."""
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})
            RETURN entity.user_uid as actual_owner,
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
        """Get entities shared with a user via direct SHARES_WITH."""
        result = await self.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[r:SHARES_WITH]->(ku:Entity)
            RETURN ku,
                   r.role as role,
                   r.shared_at as shared_at,
                   r.share_version as share_version
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
        group_uid: str,
        share_version: str,
        shared_at: str,
    ) -> Result[list[Neo4jProperties]]:
        """Create SHARED_WITH_GROUP relationship from entity to group."""
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})
            MATCH (group:Group {uid: $group_uid})
            MERGE (entity)-[r:SHARED_WITH_GROUP]->(group)
            SET r.shared_at = datetime($shared_at),
                r.share_version = $share_version
            RETURN true as success
            """,
            {
                "entity_uid": entity_uid,
                "group_uid": group_uid,
                "shared_at": shared_at,
                "share_version": share_version,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

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
                   coalesce(author.display_name, author.username) AS author_name,
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
                   coalesce(author.display_name, author.username) AS author_name,
                   r.share_version AS share_version,
                   r.shared_at AS shared_at
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
