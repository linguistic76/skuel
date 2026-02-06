"""
Report Sharing Service
===========================

Manages report sharing, access control, and visibility settings.

Core Responsibilities:
- Share/unshare reports with specific users
- Set visibility levels (PRIVATE, SHARED, PUBLIC)
- Check access permissions
- Query shared reports

Access Control Rules:
1. Owner can always view their reports
2. PUBLIC reports visible to all users
3. SHARED reports visible to owner + users with SHARES_WITH relationship
4. Only completed reports can be shared (quality control)

See: /docs/patterns/SHARING_PATTERNS.md
"""

from datetime import datetime
from typing import Any

from neo4j import Driver

from core.models.report.report import ReportDTO
from core.models.enums.metadata_enums import Visibility
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.report_sharing")


class ReportSharingService:
    """Service for managing report sharing and access control."""

    def __init__(self, driver: Driver) -> None:
        """
        Initialize the sharing service.

        Args:
            driver: Neo4j driver for database operations
        """
        self.driver = driver

    async def share_report(
        self,
        report_uid: str,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
    ) -> Result[bool]:
        """
        Share a report with a specific user.

        Creates a SHARES_WITH relationship from recipient to report.
        Only the owner can share their reports.
        Only completed reports can be shared.

        Args:
            report_uid: Report to share
            owner_uid: Report owner (must match actual owner)
            recipient_uid: User to share with
            role: Recipient's role (e.g., "teacher", "peer", "mentor")

        Returns:
            Result[bool]: Success if shared, error if validation fails
        """
        # Verify ownership
        ownership_check = await self._verify_ownership(report_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        # Verify report is shareable (completed)
        shareable_check = await self._verify_shareable(report_uid)
        if shareable_check.is_error:
            return shareable_check

        # Create SHARES_WITH relationship
        query = """
        MATCH (recipient:User {uid: $recipient_uid})
        MATCH (report:Report {uid: $report_uid})
        MERGE (recipient)-[r:SHARES_WITH]->(report)
        SET r.shared_at = datetime($shared_at),
            r.role = $role
        RETURN true as success
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                recipient_uid=recipient_uid,
                report_uid=report_uid,
                shared_at=datetime.now().isoformat(),
                role=role,
            )

            if not records:
                return Result.fail(
                    Errors.not_found(f"User {recipient_uid} or Report {report_uid} not found")
                )

            logger.info(f"Report {report_uid} shared with {recipient_uid} as {role}")
            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error sharing report: {e}")
            return Result.fail(Errors.database("share_report", str(e)))

    async def unshare_report(
        self,
        report_uid: str,
        owner_uid: str,
        recipient_uid: str,
    ) -> Result[bool]:
        """
        Revoke access to a shared report.

        Deletes the SHARES_WITH relationship.
        Only the owner can unshare their reports.

        Args:
            report_uid: Report to unshare
            owner_uid: Report owner (must match actual owner)
            recipient_uid: User to revoke access from

        Returns:
            Result[bool]: Success if unshared, error if validation fails
        """
        # Verify ownership
        ownership_check = await self._verify_ownership(report_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        # Delete SHARES_WITH relationship
        query = """
        MATCH (recipient:User {uid: $recipient_uid})-[r:SHARES_WITH]->(report:Report {uid: $report_uid})
        DELETE r
        RETURN count(r) as deleted_count
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                recipient_uid=recipient_uid,
                report_uid=report_uid,
            )

            deleted_count = records[0]["deleted_count"] if records else 0
            if deleted_count == 0:
                return Result.fail(
                    Errors.not_found(
                        f"No sharing relationship found between {recipient_uid} and {report_uid}"
                    )
                )

            logger.info(f"Report {report_uid} unshared from {recipient_uid}")
            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error unsharing report: {e}")
            return Result.fail(Errors.database("unshare_report", str(e)))

    async def get_shared_with_users(
        self,
        report_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get list of users a report is shared with.

        Returns user UID, role, and share timestamp.

        Args:
            report_uid: Report to query

        Returns:
            Result[list[dict]]: List of users with access
        """
        query = """
        MATCH (user:User)-[r:SHARES_WITH]->(report:Report {uid: $report_uid})
        RETURN user.uid as user_uid,
               user.name as user_name,
               r.role as role,
               r.shared_at as shared_at
        ORDER BY r.shared_at DESC
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                report_uid=report_uid,
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

    async def get_reports_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[ReportDTO]]:
        """
        Get reports shared with a specific user.

        Returns reports where user has SHARES_WITH relationship.

        Args:
            user_uid: User to query for
            limit: Maximum reports to return

        Returns:
            Result[list[ReportDTO]]: Shared reports
        """
        query = """
        MATCH (user:User {uid: $user_uid})-[r:SHARES_WITH]->(report:Report)
        RETURN report,
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

            reports = []
            for record in records:
                props = dict(record["report"])

                # Convert to DTO (sharing metadata stored separately, not on DTO)
                dto = ReportDTO(**props)
                reports.append(dto)

            return Result.ok(reports)

        except Exception as e:
            logger.error(f"Error fetching shared reports: {e}")
            return Result.fail(Errors.database("get_shared_reports", str(e)))

    async def set_visibility(
        self,
        report_uid: str,
        owner_uid: str,
        visibility: Visibility,
    ) -> Result[bool]:
        """
        Set report visibility level.

        Only the owner can change visibility.
        Only completed reports can be made SHARED or PUBLIC.

        Args:
            report_uid: Report to update
            owner_uid: Report owner (must match actual owner)
            visibility: New visibility level

        Returns:
            Result[bool]: Success if updated, error if validation fails
        """
        # Verify ownership
        ownership_check = await self._verify_ownership(report_uid, owner_uid)
        if ownership_check.is_error:
            return ownership_check

        # If setting to SHARED or PUBLIC, verify report is shareable
        if visibility in (Visibility.SHARED, Visibility.PUBLIC):
            shareable_check = await self._verify_shareable(report_uid)
            if shareable_check.is_error:
                return shareable_check

        # Update visibility
        query = """
        MATCH (report:Report {uid: $report_uid})
        WHERE report.user_uid = $owner_uid
        SET report.visibility = $visibility,
            report.updated_at = datetime()
        RETURN report.uid as uid
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                report_uid=report_uid,
                owner_uid=owner_uid,
                visibility=visibility.value,
            )

            if not records:
                return Result.fail(
                    Errors.not_found(f"Report {report_uid} not found or not owned by {owner_uid}")
                )

            logger.info(f"Report {report_uid} visibility set to {visibility.value}")
            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error setting visibility: {e}")
            return Result.fail(Errors.database("set_visibility", str(e)))

    async def check_access(
        self,
        report_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """
        Check if a user can access a report.

        Access is granted if:
        - User is the owner
        - Report is PUBLIC
        - Report is SHARED and user has SHARES_WITH relationship

        Args:
            report_uid: Report to check
            user_uid: User requesting access

        Returns:
            Result[bool]: True if access granted, False otherwise
        """
        query = """
        MATCH (report:Report {uid: $report_uid})
        OPTIONAL MATCH (user:User {uid: $user_uid})-[:SHARES_WITH]->(report)
        RETURN report.user_uid as owner_uid,
               report.visibility as visibility,
               count(user) > 0 as has_share_relationship
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                report_uid=report_uid,
                user_uid=user_uid,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Report {report_uid} not found"))

            record = records[0]
            owner_uid = record["owner_uid"]
            visibility = Visibility(record["visibility"])
            has_share = record["has_share_relationship"]

            # Check access rules
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
        report_uid: str,
        owner_uid: str,
    ) -> Result[bool]:
        """
        Verify that a user owns a report.

        Args:
            report_uid: Report to check
            owner_uid: Claimed owner

        Returns:
            Result[bool]: Success if owner matches, error otherwise
        """
        query = """
        MATCH (report:Report {uid: $report_uid})
        RETURN report.user_uid as actual_owner
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                report_uid=report_uid,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Report {report_uid} not found"))

            actual_owner = records[0]["actual_owner"]
            if actual_owner != owner_uid:
                return Result.fail(
                    Errors.validation(f"User {owner_uid} does not own report {report_uid}")
                )

            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error verifying ownership: {e}")
            return Result.fail(Errors.database("verify_ownership", str(e)))

    async def _verify_shareable(
        self,
        report_uid: str,
    ) -> Result[bool]:
        """
        Verify that a report can be shared.

        Only completed reports can be shared (quality control).

        Args:
            report_uid: Report to check

        Returns:
            Result[bool]: Success if shareable, error otherwise
        """
        query = """
        MATCH (report:Report {uid: $report_uid})
        RETURN report.status as status
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                report_uid=report_uid,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Report {report_uid} not found"))

            status = records[0]["status"]
            if status != "completed":
                return Result.fail(
                    Errors.validation(
                        f"Only completed reports can be shared. Current status: {status}"
                    )
                )

            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error verifying shareable: {e}")
            return Result.fail(Errors.database("verify_shareable", str(e)))
