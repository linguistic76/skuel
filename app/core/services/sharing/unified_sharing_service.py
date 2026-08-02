"""
Unified Sharing Service
=======================

Entity-agnostic sharing service. Any domain can share entities — SHARES_WITH
relationships and visibility levels work identically regardless of EntityType.

Composes with SharingBackend (persistence layer) for all Cypher queries.
The service handles validation logic (ownership, shareable status); the
backend handles Neo4j interactions.

Access Control Rules
---------------------
1. Owner always has access
2. PUBLIC entities visible to all users
3. SHARED entities visible to owner + users with SHARES_WITH relationship
4. KU entities (curriculum) always accessible (shared content)
5. Only active or completed entities can be shared

See: /docs/patterns/SHARING_PATTERNS.md
See: /docs/decisions/ADR-042-privacy-as-first-class-citizen.md
"""

from datetime import datetime
from typing import Any, cast

from core.models.entity_dto import EntityDTO
from core.models.enums.entity_enums import EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.type_hints import EntityUID, UserUID
from core.ports.query_types import SharedWithMeItem
from core.ports.sharing_protocols import SharingBackendOperations
from core.utils.logging import get_logger
from core.utils.neo4j_props import neo4j_opt_str
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.sharing")

# Entity types that can be shared while active (not just completed)
_ACTIVITY_ENTITY_TYPES = frozenset(
    {
        "task",
        "goal",
        "habit",
        "event",
        "choice",
        "principle",
        "revised_exercise",
    }
)

# Curriculum entity types — teachers share these with groups at assignment time,
# well before they reach a "completed" state. Allow any non-archived status.
_CURRICULUM_ENTITY_TYPES = frozenset(
    {
        "exercise",
        "path_step",
        "learning_path",
    }
)

# User-authored content — shareable in any status except archived.
_USER_ENTRY_TYPES = frozenset({EntityType.USER_ENTRY.value})


class UnifiedSharingService:
    """Entity-agnostic sharing and access control service.

    Manages SHARES_WITH relationships and visibility levels across all domains.
    Delegates all Cypher queries to SharingBackend.

    See: /docs/patterns/SHARING_PATTERNS.md
    """

    def __init__(self, backend: SharingBackendOperations) -> None:
        self.backend = backend

    # =========================================================================
    # SHARE / UNSHARE
    # =========================================================================

    async def share(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
        share_version: str = "original",
    ) -> Result[bool]:
        """Share an entity with a specific user.

        Creates a SHARES_WITH relationship from recipient to entity.
        Only the owner can share their entity.
        Only active or completed entities can be shared.
        """
        check = await self._verify_owned_and_shareable(entity_uid, owner_uid)
        if check.is_error:
            return check

        result = await self.backend.create_share(
            entity_uid=entity_uid,
            recipient_uid=recipient_uid,
            role=role,
            share_version=share_version,
            shared_at=datetime.now().isoformat(),
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(
                Errors.not_found(f"User {recipient_uid} or Entity {entity_uid} not found")
            )
        logger.info(f"Entity {entity_uid} shared with {recipient_uid} as {role}")
        return Result.ok(True)

    async def unshare(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        recipient_uid: str,
    ) -> Result[bool]:
        """Revoke a user's access to a shared entity.

        Deletes the SHARES_WITH relationship.
        Only the owner can revoke access.
        """
        check = await self._verify_owned_and_shareable(
            entity_uid, owner_uid, require_shareable=False
        )
        if check.is_error:
            return check

        result = await self.backend.delete_share(
            entity_uid=entity_uid,
            recipient_uid=recipient_uid,
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        deleted_count = records[0]["deleted_count"] if records else 0
        if deleted_count == 0:
            return Result.fail(
                Errors.not_found(
                    f"No sharing relationship found between {recipient_uid} and {entity_uid}"
                )
            )
        logger.info(f"Entity {entity_uid} unshared from {recipient_uid}")
        return Result.ok(True)

    # =========================================================================
    # VISIBILITY
    # =========================================================================

    async def set_visibility(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        visibility: Visibility,
    ) -> Result[bool]:
        """Set entity visibility level.

        Only the owner can change visibility.
        Only active or completed entities can be made SHARED or PUBLIC.
        """
        if visibility in (Visibility.SHARED, Visibility.PUBLIC):
            check = await self._verify_owned_and_shareable(entity_uid, owner_uid)
        else:
            check = await self._verify_owned_and_shareable(
                entity_uid, owner_uid, require_shareable=False
            )
        if check.is_error:
            return check

        result = await self.backend.update_visibility(
            entity_uid=entity_uid,
            owner_uid=owner_uid,
            visibility=visibility.value,
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(
                Errors.not_found(f"Entity {entity_uid} not found or not owned by {owner_uid}")
            )
        logger.info(f"Entity {entity_uid} visibility set to {visibility.value}")
        return Result.ok(True)

    # =========================================================================
    # ACCESS CHECKING
    # =========================================================================

    async def check_access(
        self,
        entity_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[bool]:
        """Check if a user can access an entity.

        Access granted if:
        - User is the owner
        - Entity is PUBLIC
        - Entity is SHARED and user has SHARES_WITH relationship
        - Entity is SHARED and user is a member of a group with SHARED_WITH_GROUP
        - Entity is KU type (curriculum — always accessible)
        """
        result = await self.backend.query_access(
            entity_uid=entity_uid,
            user_uid=user_uid,
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))

        record = records[0]
        owner_uid_val = record["owner_uid"]
        visibility = (
            Visibility(str(record["visibility"])) if record["visibility"] else Visibility.PRIVATE
        )
        entity_type = record["entity_type"]
        has_share = record["has_direct_share"] or record["has_group_share"]

        # Curriculum entities are always accessible (shared curriculum content)
        if entity_type in (EntityType.PATH_STEP.value, EntityType.KU.value):
            return Result.ok(True)
        if user_uid == owner_uid_val:
            return Result.ok(True)
        if visibility == Visibility.PUBLIC:
            return Result.ok(True)
        if visibility == Visibility.SHARED and has_share:
            return Result.ok(True)
        return Result.ok(False)

    async def verify_shareable(
        self,
        entity_uid: EntityUID,
    ) -> Result[bool]:
        """Verify an entity can be shared based on status and type.

        Activity entities (task, goal, habit, event, choice, principle)
        can be shared when active or completed. All other entities require
        completed status.
        """
        result = await self.backend.query_shareable_status(entity_uid=entity_uid)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))

        status = str(records[0]["status"] or "")
        entity_type = str(records[0]["entity_type"] or "")
        return self._check_shareable(status, entity_type)

    # =========================================================================
    # QUERY
    # =========================================================================

    async def get_shared_with(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[dict[str, Any]]]:
        """Get list of users an entity is shared with."""
        result = await self.backend.query_shared_with_users(entity_uid=entity_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_shared_with_me(
        self,
        user_uid: UserUID,
        limit: int = 50,
        entity_type: EntityType | None = None,
        sharer_uid: UserUID | None = None,
    ) -> Result[list[SharedWithMeItem]]:
        """Get entities shared with a specific user, with share-edge metadata.

        Each item carries the entity DTO, who shared it and when, plus the
        resolved subject context (which exercise the feedback is about, and
        its PathStep when linked) — the Shared With Me page renders type-aware
        cards from this shape. ``entity_type`` / ``sharer_uid`` optionally
        narrow the inbox (arc 2 C4); ``None`` means no filter. The enum
        crosses to the backend as its canonical value — a driver parameter,
        never interpolated.

        Backend: SharingBackend.query_shared_with_me
        """
        result = await self.backend.query_shared_with_me(
            user_uid=user_uid,
            limit=limit,
            entity_type=entity_type.value if entity_type is not None else None,
            sharer_uid=sharer_uid,
        )
        if result.is_error:
            return Result.fail(result)
        items: list[SharedWithMeItem] = [
            {
                "entity": EntityDTO.from_dict(dict(cast("dict[str, Any]", record["entity"]))),
                "role": neo4j_opt_str(record, "role"),
                "shared_at": neo4j_opt_str(record, "shared_at"),
                "shared_by": neo4j_opt_str(record, "shared_by"),
                "sharer_uid": neo4j_opt_str(record, "sharer_uid"),
                "share_version": neo4j_opt_str(record, "share_version"),
                "subject_exercise_uid": neo4j_opt_str(record, "subject_exercise_uid"),
                "subject_exercise_title": neo4j_opt_str(record, "subject_exercise_title"),
                "subject_ps_uid": neo4j_opt_str(record, "subject_ps_uid"),
                "subject_ps_title": neo4j_opt_str(record, "subject_ps_title"),
            }
            for record in (result.value or [])
        ]
        return Result.ok(items)

    # =========================================================================
    # GROUP SHARING
    # =========================================================================

    async def share_with_group(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        group_uid: str,
        share_version: str = "original",
    ) -> Result[bool]:
        """Share an entity with all members of a group.

        The owner must either OWN the target group (teacher sharing curriculum
        with their class) or be MEMBER_OF it (student sharing their UserEntry
        with a group they belong to). The backend Cypher enforces this. An
        empty result covers all miss cases (missing entity/group OR no
        qualifying relationship); we treat it as a ``forbidden`` error so
        callers can surface the real reason rather than a generic 404.
        """
        check = await self._verify_owned_and_shareable(entity_uid, owner_uid)
        if check.is_error:
            return check

        result = await self.backend.create_group_share(
            entity_uid=entity_uid,
            owner_uid=UserUID(owner_uid),
            group_uid=group_uid,
            share_version=share_version,
            shared_at=datetime.now().isoformat(),
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(
                Errors.forbidden(
                    action="share with group",
                    reason=(
                        f"Cannot share {entity_uid} with group {group_uid}: "
                        "you must own or be a member of the group, "
                        "or the group does not exist."
                    ),
                )
            )
        logger.info(f"Entity {entity_uid} shared with group {group_uid}")
        return Result.ok(True)

    async def unshare_from_group(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        group_uid: str,
    ) -> Result[bool]:
        """Revoke group-level access to an entity."""
        check = await self._verify_owned_and_shareable(
            entity_uid, owner_uid, require_shareable=False
        )
        if check.is_error:
            return check

        result = await self.backend.delete_group_share(
            entity_uid=entity_uid,
            group_uid=group_uid,
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        deleted_count = records[0]["deleted_count"] if records else 0
        if deleted_count == 0:
            return Result.fail(
                Errors.not_found(
                    f"No group sharing relationship found between {entity_uid} and {group_uid}"
                )
            )
        logger.info(f"Entity {entity_uid} unshared from group {group_uid}")
        return Result.ok(True)

    async def get_groups_shared_with(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[dict[str, Any]]]:
        """Get groups an entity is shared with."""
        result = await self.backend.query_groups_shared_with(entity_uid=entity_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_shared_with_me_via_groups(
        self,
        user_uid: UserUID,
        limit: int = 50,
    ) -> Result[list[dict[str, Any]]]:
        """Get entities shared with a user through group membership."""
        result = await self.backend.query_shared_with_me_via_groups(user_uid=user_uid, limit=limit)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        entities: list[dict[str, Any]] = [
            {
                "entity": dict(cast("dict[str, Any]", r["entity"])),
                "group_uid": r["group_uid"],
                "group_name": r["group_name"],
                "share_version": r["share_version"],
                "shared_at": r["shared_at"],
            }
            for r in records
        ]
        return Result.ok(entities)

    async def get_user_entries_shared_with_group(
        self,
        user_uid: UserUID,
        group_uid: str,
        limit: int = 20,
    ) -> Result[list[dict[str, Any]]]:
        """Get UserEntries shared with a specific group the user belongs to.

        Empty list if the user is not a member of the group (query guards on
        MEMBER_OF). Own entries are excluded.
        """
        result = await self.backend.query_user_entries_shared_with_group(
            user_uid=user_uid, group_uid=group_uid, limit=limit
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok(
            [
                {
                    "entity": dict(cast("dict[str, Any]", r["entry"])),
                    "author_name": r["author_name"],
                    "share_version": r["share_version"],
                    "shared_at": r["shared_at"],
                }
                for r in records
            ]
        )

    async def get_user_entry_shared_with_group(
        self,
        user_uid: UserUID,
        group_uid: str,
        entry_uid: EntityUID,
    ) -> Result[dict[str, Any] | None]:
        """Read-only peer fetch for a single UserEntry, gated by group membership.

        Returns ``Result.ok(None)`` when the entry is not visible to the viewer
        via this group — callers should render a 404-equivalent view so we do
        not leak whether the entry or group exists.
        """
        result = await self.backend.query_user_entry_shared_with_group(
            user_uid=user_uid, group_uid=group_uid, entry_uid=entry_uid
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        record = records[0]
        return Result.ok(
            {
                "entity": dict(cast("dict[str, Any]", record["entry"])),
                "group_name": record["group_name"],
                "author_name": record["author_name"],
                "share_version": record["share_version"],
                "shared_at": record["shared_at"],
            }
        )

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _verify_owned_and_shareable(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        *,
        require_shareable: bool = True,
    ) -> Result[bool]:
        """Verify ownership and optionally shareable status in a single query.

        Returns not_found for both missing entities and ownership mismatches
        to prevent UID enumeration.
        """
        result = await self.backend.query_ownership_and_status(entity_uid=entity_uid)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))

        record = records[0]
        actual_owner = record["actual_owner"]

        # Ownership check — not_found (not validation) to prevent UID enumeration
        if actual_owner != owner_uid:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))

        if not require_shareable:
            return Result.ok(True)

        return self._check_shareable(str(record["status"] or ""), str(record["entity_type"] or ""))

    @staticmethod
    def _check_shareable(status: str, entity_type: str) -> Result[bool]:
        """Evaluate whether an entity with given status/entity_type can be shared."""
        if entity_type in _USER_ENTRY_TYPES:
            if status == "archived":
                return Result.fail(
                    Errors.validation(
                        f"Archived user entries cannot be shared. Current status: {status}"
                    )
                )
            return Result.ok(True)
        if entity_type in _ACTIVITY_ENTITY_TYPES:
            if status in ("active", "completed"):
                return Result.ok(True)
            return Result.fail(
                Errors.validation(
                    f"Activity Ku can be shared when active or completed. Current status: {status}"
                )
            )
        if entity_type in _CURRICULUM_ENTITY_TYPES:
            if status != "archived":
                return Result.ok(True)
            return Result.fail(
                Errors.validation(f"Archived curriculum cannot be shared. Current status: {status}")
            )
        if status != "completed":
            return Result.fail(
                Errors.validation(f"Only completed Ku can be shared. Current status: {status}")
            )
        return Result.ok(True)
