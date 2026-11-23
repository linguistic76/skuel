"""
User Domain Events
==================

Events published by UserService for user account changes.

The classes below are the catalog.
"""

from dataclasses import dataclass
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID

# ============================================================================
# USER ACCOUNT EVENTS
# ============================================================================


@dataclass(frozen=True)
class UserDeleted(BaseEvent):
    """
    Published when a user account is deleted.

    Two deletion modes, both covered here:
    - Soft delete: ``hard_delete=False``. User node stays, status flipped to
      DELETED, PII scrubbed. OWNS-linked entities preserved so teachers can
      still render historical submissions.
    - Hard delete: ``hard_delete=True``. Admin-only GDPR erasure. User node +
      every OWNS-linked entity deleted.

    Subscribers:
    - AuditLogService (record deletion for compliance trail)
    - SessionService (invalidate active sessions for the deleted user)
    - SearchIndex (drop user from search personalization)
    """

    user_uid: UserUID

    # False = soft delete (reversible, PII scrubbed); True = hard delete (GDPR erasure).
    hard_delete: bool = False

    # Admin UID that initiated the deletion (for hard-delete audit trail).
    # None for self-initiated soft deletes.
    deleted_by: UserUID | None = None

    # Free-form reason (required by admin UI for hard-delete; optional otherwise).
    reason: str = ""

    event_type: ClassVar[str] = "user.deleted"
