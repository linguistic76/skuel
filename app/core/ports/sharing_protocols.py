"""
Sharing Protocols
=================

Entity-agnostic sharing protocol. Any entity type can be shared — submissions,
activity reports, or future domains. Sharing infrastructure is cross-cutting,
not submission-specific.

Protocol Responsibilities
--------------------------
    SharingBackendOperations — Persistence-layer operations consumed by
                               UnifiedSharingService (typed against self.backend).
    SharingOperations        — Route-facing service contract. Visibility control,
                               SHARES_WITH relationship management, access checking.
                               Works across all EntityTypes.

Same root word, two layers: SharingBackendOperations describes what the
SharingBackend exposes (low-level Cypher methods like create_share,
query_access); SharingOperations describes what UnifiedSharingService exposes
to routes (share, check_access, …). See CLAUDE.md § "Protocol-Based
Architecture" for the two-layer convention.

ISP-compliant: captures only the methods called from each consumer.

See: /docs/patterns/SHARING_PATTERNS.md
See: /docs/decisions/ADR-042-privacy-as-first-class-citizen.md
"""

from typing import Any, Protocol, runtime_checkable

from core.models.enums.metadata_enums import Visibility
from core.models.type_hints import EntityUID, Neo4jProperties, UserUID
from core.ports.query_types import SharedWithMeItem
from core.utils.result_simplified import Result


@runtime_checkable
class SharingBackendOperations(Protocol):
    """Backend operations consumed by UnifiedSharingService.

    Implementation: adapters/persistence/neo4j/backends/sharing_backend.py
    Consumer: core/services/sharing/unified_sharing_service.py
    """

    async def create_share(
        self,
        entity_uid: EntityUID,
        recipient_uid: str,
        role: str,
        share_version: str,
        shared_at: str,
    ) -> Result[list[Neo4jProperties]]: ...

    async def delete_share(
        self,
        entity_uid: EntityUID,
        recipient_uid: str,
    ) -> Result[list[Neo4jProperties]]: ...

    async def update_visibility(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        visibility: str,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_access(
        self,
        entity_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_shareable_status(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_ownership_and_status(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_shared_with_users(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_shared_with_me(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[Neo4jProperties]]: ...

    async def create_group_share(
        self,
        entity_uid: EntityUID,
        owner_uid: UserUID,
        group_uid: str,
        share_version: str,
        shared_at: str,
    ) -> Result[list[Neo4jProperties]]: ...

    async def delete_group_share(
        self,
        entity_uid: EntityUID,
        group_uid: str,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_groups_shared_with(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_shared_with_me_via_groups(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_user_entries_shared_with_group(
        self,
        user_uid: UserUID,
        group_uid: str,
        limit: int,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_user_entry_shared_with_group(
        self,
        user_uid: UserUID,
        group_uid: str,
        entry_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]: ...

    # ------------------------------------------------------------------
    # Cross-service backend reads (consumed by AudienceResolver via
    # ``sharing_service.backend.*`` — the SharingBackend is the natural
    # owner of these entity/group/exercise authorization checks).
    # ------------------------------------------------------------------

    async def query_user_can_use_exercise(
        self,
        exercise_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[bool]: ...

    async def query_entity_owner(
        self,
        entity_uid: EntityUID,
    ) -> Result[str | None]: ...

    async def query_exercise_groups_for_member(
        self,
        exercise_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_default_groups_for_curriculum_submission(
        self,
        exercise_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[list[Neo4jProperties]]: ...


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
    ) -> Result[list[SharedWithMeItem]]:
        """Get entities shared with a user, with share-edge metadata and the
        resolved subject context (which exercise/PathStep the item is about).
        """
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
