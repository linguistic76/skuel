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
create_group_share); SharingOperations describes what UnifiedSharingService
exposes to its callers (share, share_with_group, …). See CLAUDE.md §
"Protocol-Based Architecture" for the two-layer convention.

SharingOperations is the service's whole surface, not an ISP slice: the
``Services.sharing`` slot (services_bootstrap/_container.py) is typed against
it, and the callers reach it through that slot. Its live half is share,
get_shared_with_me, share_with_group, submit_to_group (the feedback request —
``SUBMITTED_TO_GROUP``, ADR-088 §2) and the two ``*_shared_with_group`` reads;
there is no access check — a link grants what its reader reads, and an
EntryReport is an owner read (ADR-088 §3); the revoke / visibility / access-list half
(unshare, unshare_from_group, set_visibility, get_shared_with,
get_groups_shared_with) has no caller yet — it is the PLANNED sharing
management door, ``docs/roadmap/sharing-http-door.md``.

See: /docs/patterns/SHARING_PATTERNS.md
See: /docs/decisions/ADR-042-privacy-as-first-class-citizen.md
"""

from typing import Any, Protocol, runtime_checkable

from core.models.enums.entity_enums import EntityType
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
        owner_uid: UserUID,
        recipient_uid: str,
        role: str,
        share_version: str,
        shared_at: str,
        require_co_membership: bool,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_co_member_uid(
        self,
        owner_uid: UserUID,
        username: str | None = None,
        recipient_uid: str | None = None,
    ) -> Result[list[Neo4jProperties]]: ...

    async def query_reachable_groups(
        self,
        user_uid: UserUID,
        group_uids: list[str],
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
        entity_type: str | None = None,
        sharer_uid: UserUID | None = None,
    ) -> Result[list[Neo4jProperties]]: ...

    async def create_group_share(
        self,
        entity_uid: EntityUID,
        owner_uid: UserUID,
        group_uid: str,
        share_version: str,
        shared_at: str,
    ) -> Result[list[Neo4jProperties]]: ...

    async def create_group_submission(
        self,
        entity_uid: EntityUID,
        owner_uid: UserUID,
        group_uid: str,
        submitted_at: str,
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

    async def query_user_entries_shared_with_group(
        self,
        user_uid: UserUID,
        group_uid: str,
        limit: int,
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

    Consumers: ``Services.sharing`` (services_bootstrap/_container.py) —
    reached by UserEntryService's audience resolution, FormSubmissionService,
    ExerciseService, UserEntryOrchestrator, ``/profile/shared`` and the
    groups hub. No route posts to the revoke / visibility / access-list
    members (see the module docstring).
    Implementation: UnifiedSharingService
    """

    async def share(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
        share_version: str = "original",
        *,
        require_co_membership: bool = True,
    ) -> Result[bool]:
        """Share an entity with one person (``SHARES_WITH``). The recipient
        must share a group with the owner (R8, ADR-088 §7) unless the caller
        is the forms' ``share_with_admin``. The bool is ``created``: True when
        this call wrote the link, False when it already stood — both are
        successes; an unknown or non-co-member recipient is one not-found.
        """
        ...

    async def resolve_co_member(self, owner_uid: str, username: str) -> Result[str | None]:
        """The uid behind a ``user:<username>`` target when that user shares a
        group with the owner; ``None`` for unknown and non-co-member alike.
        """
        ...

    async def shares_group_with(self, owner_uid: str, recipient_uid: str) -> Result[bool]:
        """R8 co-membership by uid (default-group co-membership counts only
        through its owner); never True for the owner's own uid.
        """
        ...

    async def reachable_groups(
        self, user_uid: str, group_uids: list[str]
    ) -> Result[frozenset[str]]:
        """The subset of ``group_uids`` that exist, are active and the user
        is a member or owner of — the pre-write check for group targets.
        """
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
        entity_type: EntityType | None = None,
        sharer_uid: UserUID | None = None,
    ) -> Result[list[SharedWithMeItem]]:
        """Get entities shared with a user, with share-edge metadata and the
        resolved subject context (which exercise/PathStep the item is about).
        Optional ``entity_type`` / ``sharer_uid`` narrow the inbox (arc 2 C4);
        ``None`` means no filter.
        """
        ...

    async def set_visibility(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        visibility: Visibility,
    ) -> Result[bool]:
        """Publish (PUBLIC) or unpublish (PRIVATE) an owned entity. Returns Result[bool]."""
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

    async def submit_to_group(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        group_uid: str,
    ) -> Result[bool]:
        """File a feedback request with the teachers who own a group
        (``SUBMITTED_TO_GROUP``, ADR-088 §2). The bool is ``created``:
        True when this call wrote the link, False when it already stood —
        both are successes; a forbidden group is the error.
        """
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

    async def get_user_entries_shared_with_group(
        self,
        user_uid: UserUID,
        group_uid: str,
        limit: int = 20,
    ) -> Result[list[dict[str, Any]]]:
        """Get UserEntries shared with one specific group the user belongs to."""
        ...
