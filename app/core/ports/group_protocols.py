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

from core.models.type_hints import FilterParams, Neo4jProperties, UserUID
from core.models.update_contracts import RawChanges
from core.ports.base_protocols import BackendOperations
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.group.group import Group


class GroupBackendOperations(BackendOperations["Group"], Protocol):
    """Backend operations for Group — base CRUD + membership edges.

    Implementation: GroupBackend (backends/collab_backends.py)
    Consumer: GroupService.__init__

    Distinct from ``GroupOperations`` below, which is the *route-facing* slice
    implemented by ``GroupService`` itself. Same root word, two layers: the
    membership methods differ between them (``add_member`` carries ``joined_at``
    here and does not there), so neither can stand in for the other.
    """

    async def create_owns_relationship(self, teacher_uid: str, group_uid: str) -> Result[bool]: ...

    async def get_user_groups(
        self, user_uid: UserUID, role: str | None = None
    ) -> "Result[builtins.list[Group]]": ...

    async def add_member(
        self,
        group_uid: str,
        user_uid: UserUID,
        joined_at: str,
        role: str = "student",
    ) -> "Result[builtins.list[Neo4jProperties]]": ...

    async def remove_member(
        self, group_uid: str, user_uid: UserUID
    ) -> "Result[builtins.list[Neo4jProperties]]": ...

    async def get_members(self, group_uid: str) -> "Result[builtins.list[Neo4jProperties]]": ...

    async def get_member_count(self, group_uid: str) -> Result[int]: ...


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

    async def get(self, uid: str) -> "Result[Group]":
        """Get group by UID; a missing UID is a NOT_FOUND error, not a None value.

        Matches ``BaseService.get()``, which converts the backend's
        ``Result.ok(None)`` into an error precisely so callers need no None
        check. The former ``Result[Group | None]`` spelling described the
        *backend* contract one layer down, and typing GroupService's backend
        generic is what surfaced the mismatch.
        """
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
