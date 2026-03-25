"""
Notification Service
====================

Lightweight service for in-app notifications stored as :Notification nodes in Neo4j.

Graph pattern: (User)-[:HAS_NOTIFICATION]->(Notification)

This is infrastructure, not a domain — uses NotificationBackend for all Cypher.
Notifications are created by event handlers and consumed by the navbar badge
and /notifications page.

See: /docs/architecture/FOUR_PHASED_LEARNING_LOOP.md
"""

from datetime import datetime
from typing import Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.notifications")


class NotificationService:
    """CRUD operations for Notification nodes in Neo4j."""

    def __init__(self, executor: Any) -> None:
        self.backend = executor

    async def create_notification(
        self,
        user_uid: str,
        notification_type: str,
        title: str,
        message: str,
        source_uid: str,
        source_type: str,
    ) -> Result[str]:
        """
        Create a notification and link to user via HAS_NOTIFICATION.

        Args:
            user_uid: Recipient user UID
            notification_type: Type key (e.g., "feedback_received")
            title: Short display title
            message: Longer description
            source_uid: The entity UID that triggered this
            source_type: Entity type (e.g., "submission_report")

        Returns:
            Result containing the notification UID
        """
        uid = UIDGenerator.generate_uid("notif")
        now = datetime.now().isoformat()

        result = await self.backend.create_notification(
            {
                "user_uid": user_uid,
                "uid": uid,
                "notification_type": notification_type,
                "title": title,
                "message": message,
                "source_uid": source_uid,
                "source_type": source_type,
                "now": now,
            },
        )
        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.fail(Errors.not_found(f"User {user_uid} not found"))

        logger.debug(f"Created notification {uid} for user {user_uid}: {notification_type}")
        return Result.ok(uid)

    async def get_unread_count(self, user_uid: str) -> Result[int]:
        """
        Get count of unread notifications for a user.

        Args:
            user_uid: User UID

        Returns:
            Result containing unread count
        """
        result = await self.backend.get_unread_count(user_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value
        count = records[0]["count"] if records else 0
        return Result.ok(count)

    async def get_notifications(
        self,
        user_uid: str,
        limit: int = 20,
        include_read: bool = True,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get notifications for a user, unread first.

        Args:
            user_uid: User UID
            limit: Maximum number to return
            include_read: Whether to include read notifications

        Returns:
            Result containing list of notification dicts
        """
        result = await self.backend.get_notifications(user_uid, limit, include_read)
        if result.is_error:
            return Result.fail(result)

        items = [
            {
                "uid": record["uid"],
                "notification_type": record["notification_type"],
                "title": record["title"],
                "message": record["message"],
                "source_uid": record["source_uid"],
                "source_type": record["source_type"],
                "read": record["read"],
                "created_at": record["created_at"],
            }
            for record in result.value
        ]

        return Result.ok(items)

    async def mark_read(self, notification_uid: str, user_uid: str) -> Result[bool]:
        """
        Mark a single notification as read.

        Args:
            notification_uid: Notification UID
            user_uid: User UID (for ownership check)

        Returns:
            Result containing success boolean
        """
        result = await self.backend.mark_read(notification_uid, user_uid)
        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.fail(Errors.not_found(f"Notification {notification_uid} not found"))

        return Result.ok(True)

    async def mark_all_read(self, user_uid: str) -> Result[int]:
        """
        Mark all notifications as read for a user.

        Args:
            user_uid: User UID

        Returns:
            Result containing count of notifications marked as read
        """
        result = await self.backend.mark_all_read(user_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value
        count = records[0]["count"] if records else 0
        logger.info(f"Marked {count} notifications as read for user {user_uid}")
        return Result.ok(count)
