"""
Notification Service
====================

Lightweight service for in-app notifications stored as :Notification nodes in Neo4j.

Graph pattern: (User)-[:HAS_NOTIFICATION]->(Notification)

This is infrastructure, not a domain — uses raw Cypher directly (no BaseService).
Notifications are created by event handlers and consumed by the navbar badge
and /notifications page.

See: /docs/architecture/SUBMISSION_FEEDBACK_LOOP.md
"""

from datetime import datetime
from typing import Any

from neo4j import Driver

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.notifications")


class NotificationService:
    """CRUD operations for Notification nodes in Neo4j."""

    def __init__(self, driver: Driver) -> None:
        self.driver = driver

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
            source_type: Entity type (e.g., "feedback_report")

        Returns:
            Result containing the notification UID
        """
        uid = UIDGenerator.generate_uid("notif")
        now = datetime.now().isoformat()

        query = """
        MATCH (u:User {uid: $user_uid})
        CREATE (n:Notification {
            uid: $uid,
            user_uid: $user_uid,
            notification_type: $notification_type,
            title: $title,
            message: $message,
            source_uid: $source_uid,
            source_type: $source_type,
            read: false,
            created_at: datetime($now)
        })
        CREATE (u)-[:HAS_NOTIFICATION]->(n)
        RETURN n.uid as uid
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                user_uid=user_uid,
                uid=uid,
                notification_type=notification_type,
                title=title,
                message=message,
                source_uid=source_uid,
                source_type=source_type,
                now=now,
            )

            if not records:
                return Result.fail(Errors.not_found(f"User {user_uid} not found"))

            logger.debug(f"Created notification {uid} for user {user_uid}: {notification_type}")
            return Result.ok(uid)

        except Exception as e:
            logger.error(f"Error creating notification: {e}")
            return Result.fail(Errors.database("create_notification", str(e)))

    async def get_unread_count(self, user_uid: str) -> Result[int]:
        """
        Get count of unread notifications for a user.

        Args:
            user_uid: User UID

        Returns:
            Result containing unread count
        """
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_NOTIFICATION]->(n:Notification {read: false})
        RETURN count(n) as count
        """

        try:
            records, _, _ = await self.driver.execute_query(query, user_uid=user_uid)
            count = records[0]["count"] if records else 0
            return Result.ok(count)

        except Exception as e:
            logger.error(f"Error getting unread count: {e}")
            return Result.fail(Errors.database("get_unread_count", str(e)))

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
        read_filter = "" if include_read else "AND n.read = false"

        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:HAS_NOTIFICATION]->(n:Notification)
        WHERE n.user_uid = $user_uid {read_filter}
        RETURN n.uid as uid,
               n.notification_type as notification_type,
               n.title as title,
               n.message as message,
               n.source_uid as source_uid,
               n.source_type as source_type,
               n.read as read,
               n.created_at as created_at
        ORDER BY n.read ASC, n.created_at DESC
        LIMIT $limit
        """

        try:
            records, _, _ = await self.driver.execute_query(query, user_uid=user_uid, limit=limit)

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
                for record in records
            ]

            return Result.ok(items)

        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            return Result.fail(Errors.database("get_notifications", str(e)))

    async def mark_read(self, notification_uid: str, user_uid: str) -> Result[bool]:
        """
        Mark a single notification as read.

        Args:
            notification_uid: Notification UID
            user_uid: User UID (for ownership check)

        Returns:
            Result containing success boolean
        """
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_NOTIFICATION]->(n:Notification {uid: $notification_uid})
        SET n.read = true
        RETURN n.uid as uid
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query, user_uid=user_uid, notification_uid=notification_uid
            )

            if not records:
                return Result.fail(Errors.not_found(f"Notification {notification_uid} not found"))

            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            return Result.fail(Errors.database("mark_read", str(e)))

    async def mark_all_read(self, user_uid: str) -> Result[int]:
        """
        Mark all notifications as read for a user.

        Args:
            user_uid: User UID

        Returns:
            Result containing count of notifications marked as read
        """
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_NOTIFICATION]->(n:Notification {read: false})
        SET n.read = true
        RETURN count(n) as count
        """

        try:
            records, _, _ = await self.driver.execute_query(query, user_uid=user_uid)
            count = records[0]["count"] if records else 0
            logger.info(f"Marked {count} notifications as read for user {user_uid}")
            return Result.ok(count)

        except Exception as e:
            logger.error(f"Error marking all notifications as read: {e}")
            return Result.fail(Errors.database("mark_all_read", str(e)))
