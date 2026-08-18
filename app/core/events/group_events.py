"""
Group Domain Events
====================

Events published when group operations occur.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

from dataclasses import dataclass
from typing import Any, ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID


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
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "group.created"


@dataclass(frozen=True)
class GroupMemberAdded(BaseEvent):
    """
    Published when a member is added to a group.

    Triggers:
    - Student notification
    - Group membership tracking
    """

    group_uid: str
    user_uid: UserUID
    role: str
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "group.member_added"


@dataclass(frozen=True)
class GroupMemberRemoved(BaseEvent):
    """
    Published when a member is removed from a group.

    Triggers:
    - Student notification
    - Group membership tracking
    """

    group_uid: str
    user_uid: UserUID
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "group.member_removed"
