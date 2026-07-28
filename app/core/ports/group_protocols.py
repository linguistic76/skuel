"""
Group Domain Protocols
=======================

Route-facing protocol for Group management (CRUD + membership).
ISP-compliant: captures only the methods called from routes.

CRUD operations use standard BaseService signatures (CRUDRouteFactory-compatible).
Membership operations are domain-specific (manual routes in groups_api.py).

TeacherReviewOperations lives in report_protocols.py — the teacher review
workflow is Phase 4 of the learning loop (Report), not Group infrastructure.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

import builtins
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.models.type_hints import FilterParams, UserUID
from core.models.update_contracts import RawChanges
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.group.group import Group


@runtime_checkable
class GroupOperations(Protocol):
    """Group CRUD and membership management operations.

    Route consumer: CRUDRouteFactory (CRUD), groups_api.py (membership), groups_ui.py
    Implementation: GroupService
    """

    # Standard CRUD (CRUDRouteFactory-compatible)
    async def create(self, entity: "Group") -> "Result[Group]":
        """Create a group. Returns Result[Group]."""
        ...

    async def get(self, uid: str) -> "Result[Group | None]":
        """Get group by UID. Returns Result[Group | None]."""
        ...

    async def get_for_user(self, uid: str, user_uid: UserUID) -> "Result[Group]":
        """Get group if user is owner or member. Returns Result[Group]."""
        ...

    async def verify_ownership(self, uid: str, user_uid: UserUID) -> "Result[Group]":
        """Verify user owns the group (owner_uid match). Returns Result[Group]."""
        ...

    async def update(self, uid: str, updates: RawChanges) -> "Result[Group]":
        """Update a group. Returns Result[Group]."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete a group. Returns Result[bool]."""
        ...

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: FilterParams | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
        user_uid: UserUID | None = None,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> "Result[tuple[builtins.list[Group], int]]":
        """List groups with pagination and user filtering."""
        ...

    # Domain-specific (manual routes)
    async def get_user_groups(
        self, user_uid: UserUID, role: str | None = None
    ) -> "Result[builtins.list[Group]]":
        """List groups the user is a member of, optionally filtered by MEMBER_OF role.

        Pass role="student" to count only student-role memberships.
        Returns Result[list[Group]].
        """
        ...

    async def add_member(
        self,
        group_uid: str,
        user_uid: UserUID,
        role: str = "student",
    ) -> Result[bool]:
        """Add a member to a group. Returns Result[bool]."""
        ...

    async def remove_member(
        self,
        group_uid: str,
        user_uid: UserUID,
    ) -> Result[bool]:
        """Remove a member from a group. Returns Result[bool]."""
        ...

    async def get_members(self, group_uid: str) -> Result[builtins.list[dict[str, Any]]]:
        """Get group members. Returns Result[list[dict]]."""
        ...
