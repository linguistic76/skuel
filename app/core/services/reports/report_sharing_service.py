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
from typing import TYPE_CHECKING, Any

from core.models.enums.metadata_enums import Visibility
from core.models.reports.submission_dto import SubmissionDTO
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor

logger = get_logger("skuel.services.ku_sharing")


class ReportsSharingService:
    """Service for managing Ku sharing and access control."""

    def __init__(self, executor: "QueryExecutor") -> None:
        """
        Initialize the sharing service.

        Args:
            executor: Query executor for database operations
        """
        self.executor = executor

    async def share_report(
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
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (recipient)-[r:SHARES_WITH]->(ku)
        SET r.shared_at = datetime($shared_at),
            r.role = $role
        RETURN true as success
        """

        result = await self.executor.execute_query(
            query,
            {
                "recipient_uid": recipient_uid,
                "ku_uid": ku_uid,
                "shared_at": datetime.now().isoformat(),
                "role": role,
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.fail(Errors.not_found(f"User {recipient_uid} or Ku {ku_uid} not found"))

        logger.info(f"Ku {ku_uid} shared with {recipient_uid} as {role}")
        return Result.ok(True)

    async def unshare_report(
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
        MATCH (recipient:User {uid: $recipient_uid})-[r:SHARES_WITH]->(ku:Entity {uid: $ku_uid})
        DELETE r
        RETURN count(r) as deleted_count
        """

        result = await self.executor.execute_query(
            query,
            {"recipient_uid": recipient_uid, "ku_uid": ku_uid},
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        deleted_count = records[0]["deleted_count"] if records else 0
        if deleted_count == 0:
            return Result.fail(
                Errors.not_found(
                    f"No sharing relationship found between {recipient_uid} and {ku_uid}"
                )
            )

        logger.info(f"Ku {ku_uid} unshared from {recipient_uid}")
        return Result.ok(True)

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
        MATCH (user:User)-[r:SHARES_WITH]->(ku:Entity {uid: $ku_uid})
        RETURN user.uid as user_uid,
               user.name as user_name,
               r.role as role,
               r.shared_at as shared_at
        ORDER BY r.shared_at DESC
        """

        result = await self.executor.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        users = [
            {
                "user_uid": record["user_uid"],
                "user_name": record["user_name"],
                "role": record["role"],
                "shared_at": record["shared_at"],
            }
            for record in result.value
        ]

        return Result.ok(users)

    async def get_reports_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[SubmissionDTO]]:
        """
        Get Ku shared with a specific user.

        Returns Ku where user has SHARES_WITH relationship.

        Args:
            user_uid: User to query for
            limit: Maximum Ku to return

        Returns:
            Result[list[SubmissionDTO]]: Shared Ku
        """
        query = """
        MATCH (user:User {uid: $user_uid})-[r:SHARES_WITH]->(ku:Entity)
        RETURN ku,
               r.role as role,
               r.shared_at as shared_at
        ORDER BY r.shared_at DESC
        LIMIT $limit
        """

        result = await self.executor.execute_query(
            query,
            {"user_uid": user_uid, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        reports = []
        for record in result.value:
            props = record["ku"]
            dto = SubmissionDTO.from_dict(props)
            reports.append(dto)

        return Result.ok(reports)

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
        MATCH (ku:Entity {uid: $ku_uid})
        WHERE ku.user_uid = $owner_uid
        SET ku.visibility = $visibility,
            ku.updated_at = datetime()
        RETURN ku.uid as uid
        """

        result = await self.executor.execute_query(
            query,
            {
                "ku_uid": ku_uid,
                "owner_uid": owner_uid,
                "visibility": visibility.value,
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.fail(
                Errors.not_found(f"Ku {ku_uid} not found or not owned by {owner_uid}")
            )

        logger.info(f"Ku {ku_uid} visibility set to {visibility.value}")
        return Result.ok(True)

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
        MATCH (ku:Entity {uid: $ku_uid})
        OPTIONAL MATCH (user:User {uid: $user_uid})-[:SHARES_WITH]->(ku)
        RETURN ku.user_uid as owner_uid,
               ku.visibility as visibility,
               ku.ku_type as ku_type,
               count(user) > 0 as has_share_relationship
        """

        result = await self.executor.execute_query(
            query,
            {"ku_uid": ku_uid, "user_uid": user_uid},
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
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

    # Private helper methods

    async def _verify_ownership(
        self,
        ku_uid: str,
        owner_uid: str,
    ) -> Result[bool]:
        """Verify that a user owns a Ku."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        RETURN ku.user_uid as actual_owner
        """

        result = await self.executor.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        if not records:
            return Result.fail(Errors.not_found(f"Ku {ku_uid} not found"))

        actual_owner = records[0]["actual_owner"]
        if actual_owner != owner_uid:
            return Result.fail(Errors.validation(f"User {owner_uid} does not own Ku {ku_uid}"))

        return Result.ok(True)

    # Activity ku_types that can be shared when active (not just completed)
    _ACTIVITY_ENTITY_TYPES = frozenset(
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
        MATCH (ku:Entity {uid: $ku_uid})
        RETURN ku.status as status, ku.ku_type as ku_type
        """

        result = await self.executor.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        if not records:
            return Result.fail(Errors.not_found(f"Ku {ku_uid} not found"))

        status = records[0]["status"]
        ku_type = records[0]["ku_type"]

        # Activity types can be shared when active or completed
        if ku_type in self._ACTIVITY_ENTITY_TYPES:
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
