"""
Notification Service
====================

Lightweight service for in-app notifications stored as :Notification nodes in Neo4j.

Graph pattern: (User)-[:HAS_NOTIFICATION]->(Notification)

This is infrastructure, not a domain — uses NotificationBackend for all Cypher.
Notifications are created by event handlers and consumed by the navbar badge
and /notifications page.

See: /docs/architecture/LEARNING_LOOP_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from core.models.enums.entity_enums import EntityType
from core.models.notification import Notification
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.neo4j_props import coerce_int
from core.utils.neo4j_temporal import convert_neo4j_datetime
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports.notification_protocols import NotificationBackendOperations
    from core.ports.query_types import NotificationRow

logger = get_logger("skuel.services.notifications")


class NotificationService:
    """CRUD operations for Notification nodes in Neo4j."""

    def __init__(self, backend: NotificationBackendOperations) -> None:
        self.backend = backend

    async def create_notification(
        self,
        user_uid: UserUID,
        notification_type: str,
        title: str,
        message: str,
        source_uid: str,
        source_type: EntityType,
    ) -> Result[str]:
        """
        Create a notification and link to user via HAS_NOTIFICATION.

        Args:
            user_uid: Recipient user UID
            notification_type: Type key (e.g., "feedback_received")
            title: Short display title
            message: Longer description
            source_uid: The entity UID that triggered this
            source_type: Kind of entity source_uid points at

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
                "source_type": source_type.value,
                "now": now,
            },
        )
        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.fail(Errors.not_found(f"User {user_uid} not found"))

        logger.debug(f"Created notification {uid} for user {user_uid}: {notification_type}")
        return Result.ok(uid)

    async def get_unread_count(self, user_uid: UserUID) -> Result[int]:
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
        return Result.ok(coerce_int(records[0]["count"]) if records else 0)

    async def get_notifications(
        self,
        user_uid: UserUID,
        limit: int = 20,
        include_read: bool = True,
    ) -> Result[list[Notification]]:
        """
        Get notifications for a user, unread first.

        Args:
            user_uid: User UID
            limit: Maximum number to return
            include_read: Whether to include read notifications

        Returns:
            Result containing the user's notifications, newest first within
            the unread group
        """
        result = await self.backend.get_notifications(user_uid, limit, include_read)
        if result.is_error:
            return Result.fail(result)

        notifications: list[Notification] = []
        for row in result.value:
            built = self._row_to_notification(row, user_uid)
            if built.is_error:
                return Result.fail(built)
            notifications.append(built.value)

        return Result.ok(notifications)

    def _row_to_notification(self, row: NotificationRow, user_uid: UserUID) -> Result[Notification]:
        """Build a Notification from one backend row.

        ``user_uid`` comes from the caller rather than the row: the query filters
        on ``n.user_uid = $user_uid``, so every row already belongs to that user
        and returning the column again would be redundant.

        ``source_type`` is stored as the canonical ``EntityType`` value. Only this
        service writes it, so an unresolvable one is schema drift rather than user
        data — fail at the read boundary instead of guessing (the page degrades to
        an empty list, which is visible without being fatal).

        ``created_at`` arrives as a Neo4j temporal from the graph and as an ISO
        string from any caller that round-tripped the row through JSON; both are
        normalised here so the model always carries a Python datetime.
        """
        source_type = EntityType.from_string(str(row["source_type"]))
        if source_type is None:
            return Result.fail(
                Errors.database(
                    "get_notifications",
                    f"Notification {row['uid']} carries an unknown source_type "
                    f"{row['source_type']!r}",
                )
            )

        return Result.ok(
            Notification(
                uid=row["uid"],
                user_uid=user_uid,
                notification_type=row["notification_type"],
                title=row["title"],
                message=row["message"],
                source_uid=row["source_uid"],
                source_type=source_type,
                read=row["read"],
                created_at=self._coerce_created_at(row),
            )
        )

    def _coerce_created_at(self, row: NotificationRow) -> datetime:
        """Normalise a row's ``created_at`` to a Python datetime."""
        raw = row.get("created_at")
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                logger.warning(f"Unparseable created_at on notification {row['uid']}: {raw!r}")
                return datetime.now()
        converted = convert_neo4j_datetime(raw)
        if converted is None:
            logger.warning(f"Missing created_at on notification {row['uid']}")
            return datetime.now()
        return converted

    async def mark_read(self, notification_uid: str, user_uid: UserUID) -> Result[bool]:
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

    async def mark_all_read(self, user_uid: UserUID) -> Result[int]:
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
        count = coerce_int(records[0]["count"]) if records else 0
        logger.info(f"Marked {count} notifications as read for user {user_uid}")
        return Result.ok(count)
