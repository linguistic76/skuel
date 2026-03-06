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
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.submissions.submission_dto import SubmissionDTO
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import SharingBackend

logger = get_logger("skuel.services.sharing")

# Entity types that can be shared while active (not just completed)
_ACTIVITY_ENTITY_TYPES = frozenset({"task", "goal", "habit", "event", "choice", "principle"})


class UnifiedSharingService:
    """Entity-agnostic sharing and access control service.

    Manages SHARES_WITH relationships and visibility levels across all domains.
    Delegates all Cypher queries to SharingBackend.

    See: /docs/patterns/SHARING_PATTERNS.md
    """

    def __init__(self, backend: "SharingBackend") -> None:
        self.backend = backend

    # =========================================================================
    # SHARE / UNSHARE
    # =========================================================================

    async def share(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.fail(
                Errors.not_found(f"User {recipient_uid} or Entity {entity_uid} not found")
            )
        logger.info(f"Entity {entity_uid} shared with {recipient_uid} as {role}")
        return Result.ok(True)

    async def unshare(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
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
        entity_uid: str,
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
            return Result.fail(result.expect_error())
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
        entity_uid: str,
        user_uid: str,
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
            return Result.fail(result.expect_error())
        records = result.value or []
        if not records:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))

        record = records[0]
        owner_uid_val = record["owner_uid"]
        visibility = (
            Visibility(record["visibility"]) if record["visibility"] else Visibility.PRIVATE
        )
        entity_type = record["entity_type"]
        has_share = record["has_direct_share"] or record["has_group_share"]

        # Curriculum entities are always accessible (shared curriculum content)
        if entity_type in (EntityType.ARTICLE.value, EntityType.KU.value):
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
        entity_uid: str,
    ) -> Result[bool]:
        """Verify an entity can be shared based on status and type.

        Activity entities (task, goal, habit, event, choice, principle)
        can be shared when active or completed. All other entities require
        completed status.
        """
        result = await self.backend.query_shareable_status(entity_uid=entity_uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        records = result.value or []
        if not records:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))

        status = records[0]["status"]
        entity_type = records[0]["entity_type"]
        return self._check_shareable(status, entity_type)

    # =========================================================================
    # QUERY
    # =========================================================================

    async def get_shared_with(
        self,
        entity_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """Get list of users an entity is shared with."""
        result = await self.backend.query_shared_with_users(entity_uid=entity_uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def get_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[SubmissionDTO]]:
        """Get entities shared with a specific user."""
        result = await self.backend.query_shared_with_me(user_uid=user_uid, limit=limit)
        if result.is_error:
            return Result.fail(result.expect_error())
        entities = [SubmissionDTO.from_dict(record["ku"]) for record in (result.value or [])]
        return Result.ok(entities)

    # =========================================================================
    # GROUP SHARING
    # =========================================================================

    async def share_with_group(
        self,
        entity_uid: str,
        owner_uid: str,
        group_uid: str,
        share_version: str = "original",
    ) -> Result[bool]:
        """Share an entity with all members of a group."""
        check = await self._verify_owned_and_shareable(entity_uid, owner_uid)
        if check.is_error:
            return check

        result = await self.backend.create_group_share(
            entity_uid=entity_uid,
            group_uid=group_uid,
            share_version=share_version,
            shared_at=datetime.now().isoformat(),
        )
        if result.is_error:
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.fail(
                Errors.not_found(f"Entity {entity_uid} or Group {group_uid} not found")
            )
        logger.info(f"Entity {entity_uid} shared with group {group_uid}")
        return Result.ok(True)

    async def unshare_from_group(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
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
        entity_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """Get groups an entity is shared with."""
        result = await self.backend.query_groups_shared_with(entity_uid=entity_uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def get_shared_with_me_via_groups(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[dict[str, Any]]]:
        """Get entities shared with a user through group membership."""
        result = await self.backend.query_shared_with_me_via_groups(user_uid=user_uid, limit=limit)
        if result.is_error:
            return Result.fail(result.expect_error())
        records = result.value or []
        entities = [
            {
                "entity": dict(r["entity"]),
                "group_uid": r["group_uid"],
                "group_name": r["group_name"],
                "share_version": r["share_version"],
                "shared_at": r["shared_at"],
            }
            for r in records
        ]
        return Result.ok(entities)

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _verify_owned_and_shareable(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
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

        return self._check_shareable(record["status"], record["entity_type"])

    @staticmethod
    def _check_shareable(status: str, entity_type: str) -> Result[bool]:
        """Evaluate whether an entity with given status/entity_type can be shared."""
        if entity_type in _ACTIVITY_ENTITY_TYPES:
            if status in ("active", "completed"):
                return Result.ok(True)
            return Result.fail(
                Errors.validation(
                    f"Activity Ku can be shared when active or completed. Current status: {status}"
                )
            )
        if status != "completed":
            return Result.fail(
                Errors.validation(f"Only completed Ku can be shared. Current status: {status}")
            )
        return Result.ok(True)
