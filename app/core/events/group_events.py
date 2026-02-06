"""
Group Domain Events
====================

Events published when group operations occur.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class GroupCreated(BaseEvent):
    """
    Published when a teacher creates a new group.

    Triggers:
    - System tracking for group creation
    """

    group_uid: str
    teacher_uid: str
    group_name: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "group.created"


@dataclass(frozen=True)
class GroupMemberAdded(BaseEvent):
    """
    Published when a member is added to a group.

    Triggers:
    - Student notification
    - Group membership tracking
    """

    group_uid: str
    user_uid: str
    role: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "group.member_added"


@dataclass(frozen=True)
class GroupMemberRemoved(BaseEvent):
    """
    Published when a member is removed from a group.

    Triggers:
    - Student notification
    - Group membership tracking
    """

    group_uid: str
    user_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "group.member_removed"
