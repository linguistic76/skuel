"""
Group Domain Protocols
=======================

Route-facing protocol for Group management (CRUD + membership).
ISP-compliant: captures only the methods called from routes.

TeacherReviewOperations lives in feedback_protocols.py — the teacher review
workflow is Phase 4 of the learning loop (Feedback), not Group infrastructure.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class GroupOperations(Protocol):
    """Group CRUD and membership management operations.

    Route consumer: groups_api.py (primary), groups_ui.py
    Implementation: GroupService
    """

    async def create_group(
        self,
        teacher_uid: str,
        name: str,
        description: str | None = None,
        max_members: int | None = None,
    ) -> Result[Any]:
        """Create a new group. Returns Result[Group]."""
        ...

    async def get_group(self, uid: str) -> Result[Any | None]:
        """Get group by UID. Returns Result[Group | None]."""
        ...

    async def list_teacher_groups(self, teacher_uid: str) -> Result[list[Any]]:
        """List groups owned by a teacher. Returns Result[list[Group]]."""
        ...

    async def get_user_groups(self, user_uid: str) -> Result[list[Any]]:
        """List groups the user is a member of. Returns Result[list[Group]]."""
        ...

    async def update_group(
        self,
        uid: str,
        name: str | None = None,
        description: str | None = None,
        max_members: int | None = None,
        is_active: bool | None = None,
    ) -> Result[Any]:
        """Update a group. Returns Result[Group]."""
        ...

    async def delete_group(self, uid: str) -> Result[bool]:
        """Delete a group. Returns Result[bool]."""
        ...

    async def add_member(
        self,
        group_uid: str,
        user_uid: str,
        role: str = "student",
    ) -> Result[bool]:
        """Add a member to a group. Returns Result[bool]."""
        ...

    async def remove_member(
        self,
        group_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """Remove a member from a group. Returns Result[bool]."""
        ...

    async def get_members(self, group_uid: str) -> Result[list[dict[str, Any]]]:
        """Get group members. Returns Result[list[dict]]."""
        ...
