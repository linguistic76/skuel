"""
Unified Sharing Service
=======================

Entity-agnostic sharing service. Any domain can share entities — SHARES_WITH
relationships and visibility levels work identically regardless of EntityType.

The sharing Cypher queries against :Entity nodes by uid — there are no
submission-specific predicates, so this service can share Tasks, Goals,
Submissions, ActivityReports, or any future entity type.

Constructor receives the Neo4j driver directly rather than a typed backend,
because sharing crosses domain boundaries and there is no single "correct"
backend to inject.

Access Control Rules
---------------------
1. Owner always has access
2. PUBLIC entities visible to all users
3. SHARED entities visible to owner + users with SHARES_WITH relationship
4. KU entities (curriculum) always accessible (shared content)
5. Only active or completed entities can be shared

See: /docs/patterns/SHARING_PATTERNS.md
See: /docs/decisions/ADR-042-privacy-as-first-class-citizen.md
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.submissions.submission_dto import SubmissionDTO
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = get_logger("skuel.services.sharing")

# Entity types that can be shared while active (not just completed)
_ACTIVITY_ENTITY_TYPES = frozenset({"task", "goal", "habit", "event", "choice", "principle"})


class UnifiedSharingService:
    """Entity-agnostic sharing and access control service.

    Manages SHARES_WITH relationships and visibility levels across all domains.
    Accepts a Neo4j driver directly to avoid binding to any single domain backend.

    See: /docs/patterns/SHARING_PATTERNS.md
    """

    def __init__(self, driver: "AsyncDriver") -> None:
        """
        Initialize the unified sharing service.

        Args:
            driver: Neo4j async driver for executing sharing queries
        """
        self.driver = driver

    # =========================================================================
    # SHARE / UNSHARE
    # =========================================================================

    async def share(
        self,
        entity_uid: str,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
        share_version: str = "original",
    ) -> Result[bool]:
        """
        Share an entity with a specific user.

        Creates a SHARES_WITH relationship from recipient to entity.
        Only the owner can share their entity.
        Only active or completed entities can be shared.

        Args:
            entity_uid: Entity to share
            owner_uid: Entity owner (must match actual owner)
            recipient_uid: User to share with
            role: Recipient's role (teacher, peer, mentor, viewer)
            share_version: Version label (original, revised)

        Returns:
            Result[bool]: True if shared, error if validation fails
        """
        ownership_check = await self._verify_ownership(entity_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        shareable_check = await self.verify_shareable(entity_uid)
        if shareable_check.is_error:
            return shareable_check

        query = """
        MATCH (recipient:User {uid: $recipient_uid})
        MATCH (ku:Entity {uid: $entity_uid})
        MERGE (recipient)-[r:SHARES_WITH]->(ku)
        SET r.shared_at = datetime($shared_at),
            r.role = $role,
            r.share_version = $share_version
        RETURN true as success
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "recipient_uid": recipient_uid,
                        "entity_uid": entity_uid,
                        "shared_at": datetime.now().isoformat(),
                        "role": role,
                        "share_version": share_version,
                    },
                )
                records = await result.data()
            if not records:
                return Result.fail(
                    Errors.not_found(f"User {recipient_uid} or Entity {entity_uid} not found")
                )
            logger.info(f"Entity {entity_uid} shared with {recipient_uid} as {role}")
            return Result.ok(True)
        except Exception as e:
            logger.error(f"Failed share {entity_uid} with {recipient_uid}: {e}")
            return Result.fail(Errors.database(operation="share", message=str(e)))

    async def unshare(
        self,
        entity_uid: str,
        owner_uid: str,
        recipient_uid: str,
    ) -> Result[bool]:
        """
        Revoke a user's access to a shared entity.

        Deletes the SHARES_WITH relationship.
        Only the owner can revoke access.

        Args:
            entity_uid: Entity to unshare
            owner_uid: Entity owner (must match actual owner)
            recipient_uid: User to revoke access from

        Returns:
            Result[bool]: True if unshared, error if validation fails
        """
        ownership_check = await self._verify_ownership(entity_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        query = """
        MATCH (recipient:User {uid: $recipient_uid})-[r:SHARES_WITH]->(ku:Entity {uid: $entity_uid})
        DELETE r
        RETURN count(r) as deleted_count
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query, {"recipient_uid": recipient_uid, "entity_uid": entity_uid}
                )
                records = await result.data()
            deleted_count = records[0]["deleted_count"] if records else 0
            if deleted_count == 0:
                return Result.fail(
                    Errors.not_found(
                        f"No sharing relationship found between {recipient_uid} and {entity_uid}"
                    )
                )
            logger.info(f"Entity {entity_uid} unshared from {recipient_uid}")
            return Result.ok(True)
        except Exception as e:
            logger.error(f"Failed unshare {entity_uid} from {recipient_uid}: {e}")
            return Result.fail(Errors.database(operation="unshare", message=str(e)))

    # =========================================================================
    # VISIBILITY
    # =========================================================================

    async def set_visibility(
        self,
        entity_uid: str,
        owner_uid: str,
        visibility: Visibility,
    ) -> Result[bool]:
        """
        Set entity visibility level.

        Only the owner can change visibility.
        Only active or completed entities can be made SHARED or PUBLIC.

        Args:
            entity_uid: Entity to update
            owner_uid: Entity owner (must match actual owner)
            visibility: New visibility level

        Returns:
            Result[bool]: True if updated, error if validation fails
        """
        ownership_check = await self._verify_ownership(entity_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        if visibility in (Visibility.SHARED, Visibility.PUBLIC):
            shareable_check = await self.verify_shareable(entity_uid)
            if shareable_check.is_error:
                return shareable_check

        query = """
        MATCH (ku:Entity {uid: $entity_uid})
        WHERE ku.user_uid = $owner_uid
        SET ku.visibility = $visibility,
            ku.updated_at = datetime()
        RETURN ku.uid as uid
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "entity_uid": entity_uid,
                        "owner_uid": owner_uid,
                        "visibility": visibility.value,
                    },
                )
                records = await result.data()
            if not records:
                return Result.fail(
                    Errors.not_found(f"Entity {entity_uid} not found or not owned by {owner_uid}")
                )
            logger.info(f"Entity {entity_uid} visibility set to {visibility.value}")
            return Result.ok(True)
        except Exception as e:
            logger.error(f"Failed set_visibility for {entity_uid}: {e}")
            return Result.fail(Errors.database(operation="set_visibility", message=str(e)))

    # =========================================================================
    # ACCESS CHECKING
    # =========================================================================

    async def check_access(
        self,
        entity_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """
        Check if a user can access an entity.

        Access granted if:
        - User is the owner
        - Entity is PUBLIC
        - Entity is SHARED and user has SHARES_WITH relationship
        - Entity is SHARED and user is a member of a group with SHARED_WITH_GROUP
        - Entity is KU type (curriculum — always accessible)

        Args:
            entity_uid: Entity to check
            user_uid: User requesting access

        Returns:
            Result[bool]: True if access granted, False otherwise
        """
        query = """
        MATCH (ku:Entity {uid: $entity_uid})
        OPTIONAL MATCH (viewer:User {uid: $user_uid})-[:SHARES_WITH]->(ku)
        OPTIONAL MATCH (viewer2:User {uid: $user_uid})-[:MEMBER_OF]->(g:Group)<-[:SHARED_WITH_GROUP]-(ku)
        RETURN ku.user_uid as owner_uid,
               ku.visibility as visibility,
               ku.ku_type as ku_type,
               count(viewer) > 0 as has_direct_share,
               count(viewer2) > 0 as has_group_share
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"entity_uid": entity_uid, "user_uid": user_uid})
                records = await result.data()
            if not records:
                return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))
            record = records[0]
            owner_uid_val = record["owner_uid"]
            visibility = (
                Visibility(record["visibility"]) if record["visibility"] else Visibility.PRIVATE
            )
            ku_type = record["ku_type"]
            has_share = record["has_direct_share"] or record["has_group_share"]
            # KU entities are always accessible (shared curriculum content)
            if ku_type == EntityType.KU.value:
                return Result.ok(True)
            if user_uid == owner_uid_val:
                return Result.ok(True)
            if visibility == Visibility.PUBLIC:
                return Result.ok(True)
            if visibility == Visibility.SHARED and has_share:
                return Result.ok(True)
            return Result.ok(False)
        except Exception as e:
            logger.error(f"Failed check_access for {entity_uid}: {e}")
            return Result.fail(Errors.database(operation="check_access", message=str(e)))

    async def verify_shareable(
        self,
        entity_uid: str,
    ) -> Result[bool]:
        """
        Verify an entity can be shared based on status and type.

        Activity entities (task, goal, habit, event, choice, principle)
        can be shared when active or completed. All other entities require
        completed status.

        Args:
            entity_uid: Entity to check

        Returns:
            Result[bool]: True if shareable, error with reason otherwise
        """
        query = """
        MATCH (ku:Entity {uid: $entity_uid})
        RETURN ku.status as status, ku.ku_type as ku_type
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"entity_uid": entity_uid})
                records = await result.data()
            if not records:
                return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))
            status = records[0]["status"]
            ku_type = records[0]["ku_type"]
            if ku_type in _ACTIVITY_ENTITY_TYPES:
                if status in ("active", "completed"):
                    return Result.ok(True)
                return Result.fail(
                    Errors.validation(
                        f"Activity Ku can be shared when active or completed. Current status: {status}"
                    )
                )
            if status != "completed":
                return Result.fail(
                    Errors.validation(f"Only completed Ku can be shared. Current status: {status}")
                )
            return Result.ok(True)
        except Exception as e:
            logger.error(f"Failed verify_shareable for {entity_uid}: {e}")
            return Result.fail(Errors.database(operation="verify_shareable", message=str(e)))

    # =========================================================================
    # QUERY
    # =========================================================================

    async def get_shared_with(
        self,
        entity_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get list of users an entity is shared with.

        Returns user UID, role, share_version, and share timestamp.

        Args:
            entity_uid: Entity to query

        Returns:
            Result[list[dict]]: List of users with access
        """
        query = """
        MATCH (user:User)-[r:SHARES_WITH]->(ku:Entity {uid: $entity_uid})
        RETURN user.uid as user_uid,
               user.name as user_name,
               r.role as role,
               r.share_version as share_version,
               r.shared_at as shared_at
        ORDER BY r.shared_at DESC
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"entity_uid": entity_uid})
                records = await result.data()
            users = [
                {
                    "user_uid": r["user_uid"],
                    "user_name": r["user_name"],
                    "role": r["role"],
                    "share_version": r["share_version"],
                    "shared_at": r["shared_at"],
                }
                for r in records
            ]
            return Result.ok(users)
        except Exception as e:
            logger.error(f"Failed get_shared_with for {entity_uid}: {e}")
            return Result.fail(Errors.database(operation="get_shared_with", message=str(e)))

    async def get_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[SubmissionDTO]]:
        """
        Get entities shared with a specific user.

        Returns entities where user has SHARES_WITH relationship.

        Args:
            user_uid: User to query for
            limit: Maximum entities to return

        Returns:
            Result[list[SubmissionDTO]]: Entities shared with the user
        """
        query = """
        MATCH (user:User {uid: $user_uid})-[r:SHARES_WITH]->(ku:Entity)
        RETURN ku,
               r.role as role,
               r.shared_at as shared_at,
               r.share_version as share_version
        ORDER BY r.shared_at DESC
        LIMIT $limit
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "limit": limit})
                records = await result.data()
            entities = [SubmissionDTO.from_dict(record["ku"]) for record in records]
            return Result.ok(entities)
        except Exception as e:
            logger.error(f"Failed get_shared_with_me for {user_uid}: {e}")
            return Result.fail(Errors.database(operation="get_shared_with_me", message=str(e)))

    # =========================================================================
    # GROUP SHARING
    # =========================================================================

    async def share_with_group(
        self,
        entity_uid: str,
        owner_uid: str,
        group_uid: str,
        share_version: str = "original",
    ) -> Result[bool]:
        """
        Share an entity with all members of a group.

        Creates a SHARED_WITH_GROUP relationship from entity to group.
        All current and future members of the group gain access when the
        entity visibility is SHARED.

        Args:
            entity_uid: Entity to share
            owner_uid: Entity owner (must match actual owner)
            group_uid: Group to share with
            share_version: Version label (original, revised)

        Returns:
            Result[bool]: True if shared, error if validation fails
        """
        ownership_check = await self._verify_ownership(entity_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        shareable_check = await self.verify_shareable(entity_uid)
        if shareable_check.is_error:
            return shareable_check

        query = """
        MATCH (entity:Entity {uid: $entity_uid})
        MATCH (group:Group {uid: $group_uid})
        MERGE (entity)-[r:SHARED_WITH_GROUP]->(group)
        SET r.shared_at = datetime($shared_at),
            r.share_version = $share_version
        RETURN true as success
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "entity_uid": entity_uid,
                        "group_uid": group_uid,
                        "shared_at": datetime.now().isoformat(),
                        "share_version": share_version,
                    },
                )
                records = await result.data()
            if not records:
                return Result.fail(
                    Errors.not_found(f"Entity {entity_uid} or Group {group_uid} not found")
                )
            logger.info(f"Entity {entity_uid} shared with group {group_uid}")
            return Result.ok(True)
        except Exception as e:
            logger.error(f"Failed share_with_group {entity_uid} → {group_uid}: {e}")
            return Result.fail(Errors.database(operation="share_with_group", message=str(e)))

    async def unshare_from_group(
        self,
        entity_uid: str,
        owner_uid: str,
        group_uid: str,
    ) -> Result[bool]:
        """
        Revoke group-level access to an entity.

        Deletes the SHARED_WITH_GROUP relationship. Existing direct
        SHARES_WITH relationships are not affected.

        Args:
            entity_uid: Entity to unshare
            owner_uid: Entity owner (must match actual owner)
            group_uid: Group to remove access from

        Returns:
            Result[bool]: True if unshared, error if validation fails
        """
        ownership_check = await self._verify_ownership(entity_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        query = """
        MATCH (entity:Entity {uid: $entity_uid})-[r:SHARED_WITH_GROUP]->(group:Group {uid: $group_uid})
        DELETE r
        RETURN count(r) as deleted_count
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query, {"entity_uid": entity_uid, "group_uid": group_uid}
                )
                records = await result.data()
            deleted_count = records[0]["deleted_count"] if records else 0
            if deleted_count == 0:
                return Result.fail(
                    Errors.not_found(
                        f"No group sharing relationship found between {entity_uid} and {group_uid}"
                    )
                )
            logger.info(f"Entity {entity_uid} unshared from group {group_uid}")
            return Result.ok(True)
        except Exception as e:
            logger.error(f"Failed unshare_from_group {entity_uid} ← {group_uid}: {e}")
            return Result.fail(Errors.database(operation="unshare_from_group", message=str(e)))

    async def get_groups_shared_with(
        self,
        entity_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get groups an entity is shared with.

        Returns group UID, name, share_version, and share timestamp.

        Args:
            entity_uid: Entity to query

        Returns:
            Result[list[dict]]: List of groups with access
        """
        query = """
        MATCH (entity:Entity {uid: $entity_uid})-[r:SHARED_WITH_GROUP]->(group:Group)
        RETURN group.uid as group_uid,
               group.name as group_name,
               r.share_version as share_version,
               r.shared_at as shared_at
        ORDER BY r.shared_at DESC
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"entity_uid": entity_uid})
                records = await result.data()
            groups = [
                {
                    "group_uid": r["group_uid"],
                    "group_name": r["group_name"],
                    "share_version": r["share_version"],
                    "shared_at": r["shared_at"],
                }
                for r in records
            ]
            return Result.ok(groups)
        except Exception as e:
            logger.error(f"Failed get_groups_shared_with for {entity_uid}: {e}")
            return Result.fail(Errors.database(operation="get_groups_shared_with", message=str(e)))

    async def get_shared_with_me_via_groups(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get entities shared with a user through group membership.

        Returns entities where the user is a member of a group that
        the entity is shared with (SHARED_WITH_GROUP relationship).
        Excludes entities the user owns.

        Args:
            user_uid: User to query for
            limit: Maximum entities to return

        Returns:
            Result[list[dict]]: Entities accessible via group membership
        """
        query = """
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
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "limit": limit})
                records = await result.data()
            entities = [
                {
                    "entity": dict(r["entity"]),
                    "group_uid": r["group_uid"],
                    "group_name": r["group_name"],
                    "share_version": r["share_version"],
                    "shared_at": r["shared_at"],
                }
                for r in records
            ]
            return Result.ok(entities)
        except Exception as e:
            logger.error(f"Failed get_shared_with_me_via_groups for {user_uid}: {e}")
            return Result.fail(
                Errors.database(operation="get_shared_with_me_via_groups", message=str(e))
            )

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _verify_ownership(
        self,
        entity_uid: str,
        owner_uid: str,
    ) -> Result[bool]:
        """Verify that a user owns an entity."""
        query = """
        MATCH (entity:Entity {uid: $entity_uid})
        RETURN entity.user_uid as actual_owner
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"entity_uid": entity_uid})
                records = await result.data()
            if not records:
                return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))
            actual_owner = records[0]["actual_owner"]
            if actual_owner != owner_uid:
                # Return not_found (not validation) to prevent UID enumeration
                return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))
            return Result.ok(True)
        except Exception as e:
            logger.error(f"Failed _verify_ownership for {entity_uid}: {e}")
            return Result.fail(Errors.database(operation="verify_ownership", message=str(e)))
