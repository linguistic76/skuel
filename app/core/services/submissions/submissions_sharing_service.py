"""
Submission Sharing Service
==========================

Manages submission sharing, access control, and visibility settings.

Core Responsibilities:
- Share/unshare submissions with specific users
- Set visibility levels (PRIVATE, SHARED, PUBLIC)
- Check access permissions
- Query shared Ku

Access Control Rules:
1. Owner can always view their Ku
2. PUBLIC Ku visible to all users
3. SHARED Ku visible to owner + users with SHARES_WITH relationship
4. Only completed entities can be shared (quality control)

See: /docs/patterns/SHARING_PATTERNS.md
"""

from typing import TYPE_CHECKING, Any

from core.models.enums.metadata_enums import Visibility
from core.models.submissions.submission_dto import SubmissionDTO
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.submission_protocols import SubmissionOperations

logger = get_logger("skuel.services.ku_sharing")


class SubmissionsSharingService:
    """Service for managing entity sharing and access control."""

    def __init__(self, backend: "SubmissionOperations") -> None:
        """
        Initialize the sharing service.

        Args:
            backend: Submission operations backend for database operations
        """
        self.backend = backend

    async def share_submission(
        self,
        ku_uid: str,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
    ) -> Result[bool]:
        """
        Share a submission with a specific user.

        Creates a SHARES_WITH relationship from recipient to submission.
        Only the owner can share their submission.
        Only completed entities can be shared.

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

        result = await self.backend.share_submission(ku_uid, recipient_uid, role)
        if result.is_error:
            return result

        logger.info(f"Ku {ku_uid} shared with {recipient_uid} as {role}")
        return Result.ok(True)

    async def unshare_submission(
        self,
        ku_uid: str,
        owner_uid: str,
        recipient_uid: str,
    ) -> Result[bool]:
        """
        Revoke access to a shared submission.

        Deletes the SHARES_WITH relationship.
        Only the owner can unshare their submission.

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

        result = await self.backend.unshare_submission(ku_uid, recipient_uid)
        if result.is_error:
            return result

        logger.info(f"Ku {ku_uid} unshared from {recipient_uid}")
        return Result.ok(True)

    async def get_shared_with_users(
        self,
        ku_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get list of users an entity is shared with.

        Returns user UID, role, and share timestamp.

        Args:
            ku_uid: Ku to query

        Returns:
            Result[list[dict]]: List of users with access
        """
        return await self.backend.get_shared_with_users(ku_uid)

    async def get_submissions_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[SubmissionDTO]]:
        """
        Get submissions shared with a specific user.

        Returns Ku where user has SHARES_WITH relationship.

        Args:
            user_uid: User to query for
            limit: Maximum Ku to return

        Returns:
            Result[list[SubmissionDTO]]: Shared Ku
        """
        return await self.backend.get_submissions_shared_with_me(user_uid, limit)

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

        result = await self.backend.set_visibility(ku_uid, owner_uid, visibility)
        if result.is_error:
            return result

        logger.info(f"Ku {ku_uid} visibility set to {visibility.value}")
        return Result.ok(True)

    async def check_access(
        self,
        ku_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """
        Check if a user can access an entity.

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
        return await self.backend.check_access(ku_uid, user_uid)

    # Private helper methods

    async def _verify_ownership(
        self,
        ku_uid: str,
        owner_uid: str,
    ) -> Result[bool]:
        """Verify that a user owns an entity."""
        return await self.backend.verify_ownership(ku_uid, owner_uid)

    async def _verify_shareable(
        self,
        ku_uid: str,
    ) -> Result[bool]:
        """Verify that an entity can be shared."""
        return await self.backend.verify_shareable(ku_uid)
