"""
Notification Protocols - ISP Contracts for In-App Notifications
===============================================================

Two layers, both narrow (see /docs/patterns/protocol_architecture.md):

- ``NotificationBackendOperations`` types ``NotificationService.backend``.
  Notifications are infrastructure, not domain entities — the backend is a raw
  query executor rather than a ``UniversalNeo4jBackend``, and ``Notification``
  is not a ``DomainModelProtocol``, so this is a standalone ``Protocol`` rather
  than a ``BackendOperations[T]`` subclass.
- ``NotificationOperations`` is the service-facing slice the report event
  handlers consume — one method, exactly what they call.

See: /docs/patterns/BACKEND_OPERATIONS_ISP.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.type_hints import Neo4jProperties, UserUID
    from core.ports.query_types import NotificationRow


class NotificationBackendOperations(Protocol):
    """Backend operations for :Notification nodes — the five queries the service issues.

    Implementation: NotificationBackend (backends/collab_backends.py)
    Consumer: NotificationService.__init__
    """

    async def create_notification(
        self,
        params: Neo4jProperties,
    ) -> Result[list[Neo4jProperties]]:
        """Create a notification node and link it to its recipient.

        Backend: NotificationBackend.create_notification (returns the new uid,
        or an empty row list when the recipient does not exist).
        """
        ...

    async def get_unread_count(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Count a user's unread notifications.

        Backend: NotificationBackend.get_unread_count (single ``count`` row).
        """
        ...

    async def get_notifications(
        self, user_uid: UserUID, limit: int, include_read: bool = True
    ) -> Result[list[NotificationRow]]:
        """Fetch a user's notifications, unread first, newest first within each group.

        Backend: NotificationBackend.get_notifications.
        """
        ...

    async def mark_read(
        self, notification_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Mark one owned notification read.

        Backend: NotificationBackend.mark_read (empty rows = not owned/not found).
        """
        ...

    async def mark_all_read(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Mark every unread notification read for a user.

        Backend: NotificationBackend.mark_all_read (single ``count`` row).
        """
        ...


class NotificationOperations(Protocol):
    """Service-facing slice: raising an in-app notification.

    Implementation: NotificationService
    Consumers: the four handlers in core/events/handlers/report_notification_handler.py
    """

    async def create_notification(
        self,
        user_uid: UserUID,
        notification_type: str,
        title: str,
        message: str,
        source_uid: str,
        source_type: str,
    ) -> Result[str]:
        """Raise a notification for a user; returns the new notification's uid."""
        ...
