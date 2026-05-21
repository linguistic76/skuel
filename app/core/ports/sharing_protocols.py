"""
Sharing Protocols
=================

Entity-agnostic sharing protocol. Any entity type can be shared — submissions,
activity reports, or future domains. Sharing infrastructure is cross-cutting,
not submission-specific.

Protocol Responsibilities
--------------------------
    SharingOperations  — Visibility control, SHARES_WITH relationship management,
                         access checking. Works across all EntityTypes.

ISP-compliant: captures only the methods called from routes.

See: /docs/patterns/SHARING_PATTERNS.md
See: /docs/decisions/ADR-042-privacy-as-first-class-citizen.md
"""

from typing import Any, Protocol, runtime_checkable

from core.models.enums.metadata_enums import Visibility
from core.models.type_hints import EntityUID, UserUID
from core.utils.result_simplified import Result


@runtime_checkable
class SharingOperations(Protocol):
    """Entity-agnostic sharing and visibility control.

    Manages SHARES_WITH relationships and visibility levels
    (PRIVATE / SHARED / PUBLIC) for any entity type.

    Route consumer: submissions_sharing_api.py
    Implementation: UnifiedSharingService
    """

    async def share(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
        share_version: str = "original",
    ) -> Result[bool]:
        """Share an entity with a user. Returns Result[bool]."""
        ...

    async def unshare(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        recipient_uid: str,
    ) -> Result[bool]:
        """Revoke sharing access. Returns Result[bool]."""
        ...

    async def get_shared_with(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[dict[str, Any]]]:
        """Get users an entity is shared with. Returns Result[list[dict]]."""
        ...

    async def get_shared_with_me(
        self,
        user_uid: UserUID,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get entities shared with a user. Returns Result[list[EntityDTO]]."""
        ...

    async def set_visibility(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        visibility: Visibility,
    ) -> Result[bool]:
        """Set entity visibility level. Returns Result[bool]."""
        ...

    async def check_access(
        self,
        entity_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[bool]:
        """Check if a user has access to an entity. Returns Result[bool]."""
        ...

    async def verify_shareable(
        self,
        entity_uid: EntityUID,
    ) -> Result[bool]:
        """Verify entity can be shared (status + type check). Returns Result[bool]."""
        ...

    async def share_with_group(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        group_uid: str,
        share_version: str = "original",
    ) -> Result[bool]:
        """Share an entity with all members of a group. Returns Result[bool]."""
        ...

    async def unshare_from_group(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        group_uid: str,
    ) -> Result[bool]:
        """Revoke group-level access to an entity. Returns Result[bool]."""
        ...

    async def get_groups_shared_with(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[dict[str, Any]]]:
        """Get groups an entity is shared with. Returns Result[list[dict]]."""
        ...

    async def get_shared_with_me_via_groups(
        self,
        user_uid: UserUID,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get entities shared via group membership. Returns Result[list[dict]]."""
        ...

    async def get_user_entries_shared_with_group(
        self,
        user_uid: UserUID,
        group_uid: str,
        limit: int = 20,
    ) -> Result[list[dict[str, Any]]]:
        """Get UserEntries shared with one specific group the user belongs to."""
        ...

    async def get_user_entry_shared_with_group(
        self,
        user_uid: UserUID,
        group_uid: str,
        entry_uid: EntityUID,
    ) -> Result[dict[str, Any] | None]:
        """Read-only peer fetch for one UserEntry, gated by group membership.

        Returns Result.ok(None) when not visible to the viewer via this group.
        """
        ...
