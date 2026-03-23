"""
Group Domain Protocols
=======================

Route-facing protocol for Group management (CRUD + membership).
ISP-compliant: captures only the methods called from routes.

CRUD operations use standard BaseService signatures (CRUDRouteFactory-compatible).
Membership operations are domain-specific (manual routes in groups_api.py).

TeacherReviewOperations lives in report_protocols.py — the teacher review
workflow is Phase 4 of the learning loop (Report), not Group infrastructure.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

import builtins
from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class GroupOperations(Protocol):
    """Group CRUD and membership management operations.

    Route consumer: CRUDRouteFactory (CRUD), groups_api.py (membership), groups_ui.py
    Implementation: GroupService
    """

    # Standard CRUD (CRUDRouteFactory-compatible)
    async def create(self, entity: Any) -> Result[Any]:
        """Create a group. Returns Result[Group]."""
        ...

    async def get(self, uid: str) -> Result[Any | None]:
        """Get group by UID. Returns Result[Group | None]."""
        ...

    async def get_for_user(self, uid: str, user_uid: str) -> Result[Any]:
        """Get group if user is owner or member. Returns Result[Group]."""
        ...

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[Any]:
        """Verify user owns the group (owner_uid match). Returns Result[Group]."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Any]:
        """Update a group. Returns Result[Group]."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete a group. Returns Result[bool]."""
        ...

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
        user_uid: str | None = None,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[Any]:
        """List groups with pagination and user filtering."""
        ...

    # Domain-specific (manual routes)
    async def get_user_groups(self, user_uid: str) -> Result[builtins.list[Any]]:
        """List groups the user is a member of. Returns Result[list[Group]]."""
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

    async def get_members(self, group_uid: str) -> Result[builtins.list[dict[str, Any]]]:
        """Get group members. Returns Result[list[dict]]."""
        ...
