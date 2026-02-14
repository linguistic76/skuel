"""
Ku Sharing Service
====================

Manages Ku sharing, access control, and visibility settings.

Core Responsibilities:
- Share/unshare Ku with specific users
- Set visibility levels (PRIVATE, SHARED, PUBLIC)
- Check access permissions
- Query shared Ku

Access Control Rules:
1. Owner can always view their Ku
2. PUBLIC Ku visible to all users
3. SHARED Ku visible to owner + users with SHARES_WITH relationship
4. Only completed Ku can be shared (quality control)

See: /docs/patterns/SHARING_PATTERNS.md
"""

from datetime import datetime
from typing import Any

from neo4j import Driver

from core.models.enums.metadata_enums import Visibility
from core.models.ku import KuDTO
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.ku_sharing")


class KuSharingService:
    """Service for managing Ku sharing and access control."""

    def __init__(self, driver: Driver) -> None:
        """
        Initialize the sharing service.

        Args:
            driver: Neo4j driver for database operations
        """
        self.driver = driver

    async def share_ku(
        self,
        ku_uid: str,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
    ) -> Result[bool]:
        """
        Share a Ku with a specific user.

        Creates a SHARES_WITH relationship from recipient to Ku.
        Only the owner can share their Ku.
        Only completed Ku can be shared.

        Args:
            ku_uid: Ku to share
            owner_uid: Ku owner (must match actual owner)
            recipient_uid: User to share with
            role: Recipient's role (e.g., "teacher", "peer", "mentor")

        Returns:
            Result[bool]: Success if shared, error if validation fails
        """
        ownership_check = await self._verify_ownership(ku_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        shareable_check = await self._verify_shareable(ku_uid)
        if shareable_check.is_error:
            return shareable_check

        query = """
        MATCH (recipient:User {uid: $recipient_uid})
        MATCH (ku:Ku {uid: $ku_uid})
        MERGE (recipient)-[r:SHARES_WITH]->(ku)
        SET r.shared_at = datetime($shared_at),
            r.role = $role
        RETURN true as success
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                recipient_uid=recipient_uid,
                ku_uid=ku_uid,
                shared_at=datetime.now().isoformat(),
                role=role,
            )

            if not records:
                return Result.fail(
                    Errors.not_found(f"User {recipient_uid} or Ku {ku_uid} not found")
                )

            logger.info(f"Ku {ku_uid} shared with {recipient_uid} as {role}")
            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error sharing Ku: {e}")
            return Result.fail(Errors.database("share_ku", str(e)))

    async def unshare_ku(
        self,
        ku_uid: str,
        owner_uid: str,
        recipient_uid: str,
    ) -> Result[bool]:
        """
        Revoke access to a shared Ku.

        Deletes the SHARES_WITH relationship.
        Only the owner can unshare their Ku.

        Args:
            ku_uid: Ku to unshare
            owner_uid: Ku owner (must match actual owner)
            recipient_uid: User to revoke access from

        Returns:
            Result[bool]: Success if unshared, error if validation fails
        """
        ownership_check = await self._verify_ownership(ku_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        query = """
        MATCH (recipient:User {uid: $recipient_uid})-[r:SHARES_WITH]->(ku:Ku {uid: $ku_uid})
        DELETE r
        RETURN count(r) as deleted_count
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                recipient_uid=recipient_uid,
                ku_uid=ku_uid,
            )

            deleted_count = records[0]["deleted_count"] if records else 0
            if deleted_count == 0:
                return Result.fail(
                    Errors.not_found(
                        f"No sharing relationship found between {recipient_uid} and {ku_uid}"
                    )
                )

            logger.info(f"Ku {ku_uid} unshared from {recipient_uid}")
            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error unsharing Ku: {e}")
            return Result.fail(Errors.database("unshare_ku", str(e)))

    async def get_shared_with_users(
        self,
        ku_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get list of users a Ku is shared with.

        Returns user UID, role, and share timestamp.

        Args:
            ku_uid: Ku to query

        Returns:
            Result[list[dict]]: List of users with access
        """
        query = """
        MATCH (user:User)-[r:SHARES_WITH]->(ku:Ku {uid: $ku_uid})
        RETURN user.uid as user_uid,
               user.name as user_name,
               r.role as role,
               r.shared_at as shared_at
        ORDER BY r.shared_at DESC
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                ku_uid=ku_uid,
            )

            users = [
                {
                    "user_uid": record["user_uid"],
                    "user_name": record["user_name"],
                    "role": record["role"],
                    "shared_at": record["shared_at"],
                }
                for record in records
            ]

            return Result.ok(users)

        except Exception as e:
            logger.error(f"Error fetching shared users: {e}")
            return Result.fail(Errors.database("get_shared_users", str(e)))

    async def get_kus_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[KuDTO]]:
        """
        Get Ku shared with a specific user.

        Returns Ku where user has SHARES_WITH relationship.

        Args:
            user_uid: User to query for
            limit: Maximum Ku to return

        Returns:
            Result[list[KuDTO]]: Shared Ku
        """
        query = """
        MATCH (user:User {uid: $user_uid})-[r:SHARES_WITH]->(ku:Ku)
        RETURN ku,
               r.role as role,
               r.shared_at as shared_at
        ORDER BY r.shared_at DESC
        LIMIT $limit
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                user_uid=user_uid,
                limit=limit,
            )

            kus = []
            for record in records:
                props = dict(record["ku"])
                dto = KuDTO.from_dict(props)
                kus.append(dto)

            return Result.ok(kus)

        except Exception as e:
            logger.error(f"Error fetching shared Ku: {e}")
            return Result.fail(Errors.database("get_kus_shared_with_me", str(e)))

    async def set_visibility(
        self,
        ku_uid: str,
        owner_uid: str,
        visibility: Visibility,
    ) -> Result[bool]:
        """
        Set Ku visibility level.

        Only the owner can change visibility.
        Only completed Ku can be made SHARED or PUBLIC.

        Args:
            ku_uid: Ku to update
            owner_uid: Ku owner (must match actual owner)
            visibility: New visibility level

        Returns:
            Result[bool]: Success if updated, error if validation fails
        """
        ownership_check = await self._verify_ownership(ku_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        if visibility in (Visibility.SHARED, Visibility.PUBLIC):
            shareable_check = await self._verify_shareable(ku_uid)
            if shareable_check.is_error:
                return shareable_check

        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        WHERE ku.user_uid = $owner_uid
        SET ku.visibility = $visibility,
            ku.updated_at = datetime()
        RETURN ku.uid as uid
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                ku_uid=ku_uid,
                owner_uid=owner_uid,
                visibility=visibility.value,
            )

            if not records:
                return Result.fail(
                    Errors.not_found(f"Ku {ku_uid} not found or not owned by {owner_uid}")
                )

            logger.info(f"Ku {ku_uid} visibility set to {visibility.value}")
            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error setting visibility: {e}")
            return Result.fail(Errors.database("set_visibility", str(e)))

    async def check_access(
        self,
        ku_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """
        Check if a user can access a Ku.

        Access is granted if:
        - User is the owner
        - Ku is PUBLIC
        - Ku is SHARED and user has SHARES_WITH relationship
        - Ku is CURRICULUM type (always public)

        Args:
            ku_uid: Ku to check
            user_uid: User requesting access

        Returns:
            Result[bool]: True if access granted, False otherwise
        """
        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        OPTIONAL MATCH (user:User {uid: $user_uid})-[:SHARES_WITH]->(ku)
        RETURN ku.user_uid as owner_uid,
               ku.visibility as visibility,
               ku.ku_type as ku_type,
               count(user) > 0 as has_share_relationship
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                ku_uid=ku_uid,
                user_uid=user_uid,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Ku {ku_uid} not found"))

            record = records[0]
            owner_uid = record["owner_uid"]
            visibility = (
                Visibility(record["visibility"]) if record["visibility"] else Visibility.PRIVATE
            )
            ku_type = record["ku_type"]
            has_share = record["has_share_relationship"]

            # CURRICULUM Ku are always accessible
            if ku_type == "curriculum":
                return Result.ok(True)
            # Owner always has access
            if user_uid == owner_uid:
                return Result.ok(True)
            if visibility == Visibility.PUBLIC:
                return Result.ok(True)
            if visibility == Visibility.SHARED and has_share:
                return Result.ok(True)

            return Result.ok(False)

        except Exception as e:
            logger.error(f"Error checking access: {e}")
            return Result.fail(Errors.database("check_access", str(e)))

    # Private helper methods

    async def _verify_ownership(
        self,
        ku_uid: str,
        owner_uid: str,
    ) -> Result[bool]:
        """Verify that a user owns a Ku."""
        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        RETURN ku.user_uid as actual_owner
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                ku_uid=ku_uid,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Ku {ku_uid} not found"))

            actual_owner = records[0]["actual_owner"]
            if actual_owner != owner_uid:
                return Result.fail(Errors.validation(f"User {owner_uid} does not own Ku {ku_uid}"))

            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error verifying ownership: {e}")
            return Result.fail(Errors.database("verify_ownership", str(e)))

    # Activity ku_types that can be shared when active (not just completed)
    _ACTIVITY_KU_TYPES = frozenset(
        {
            "task",
            "goal",
            "habit",
            "event",
            "choice",
            "principle",
        }
    )

    async def _verify_shareable(
        self,
        ku_uid: str,
    ) -> Result[bool]:
        """Verify that a Ku can be shared.

        For report/journal types: only completed Ku can be shared.
        For activity types (task, goal, etc.): active or completed Ku can be shared.
        Draft Ku can never be shared.
        """
        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        RETURN ku.status as status, ku.ku_type as ku_type
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                ku_uid=ku_uid,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Ku {ku_uid} not found"))

            status = records[0]["status"]
            ku_type = records[0]["ku_type"]

            # Activity types can be shared when active or completed
            if ku_type in self._ACTIVITY_KU_TYPES:
                if status in ("active", "completed"):
                    return Result.ok(True)
                return Result.fail(
                    Errors.validation(
                        f"Activity Ku can be shared when active or completed. Current status: {status}"
                    )
                )

            # All other types: only completed
            if status != "completed":
                return Result.fail(
                    Errors.validation(f"Only completed Ku can be shared. Current status: {status}")
                )

            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error verifying shareable: {e}")
            return Result.fail(Errors.database("verify_shareable", str(e)))
