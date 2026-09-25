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
from core.models.enums.pipeline import Pipeline
from core.models.type_hints import EntityUID, UserUID
from core.ports.query_types import SharedWithMeItem
from core.ports.sharing_protocols import SharingBackendOperations
from core.utils.logging import get_logger
from core.utils.neo4j_props import neo4j_opt_str
from core.utils.result_simplified import ErrorContext, Errors, Result

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

# User-authored content — shareable in any status except archived, and never
# when private or on a private pipeline (ADR-088 §1, for the entry's lifetime).
_USER_ENTRY_TYPES = frozenset({EntityType.USER_ENTRY.value})


def _person_not_found(identifier: str) -> ErrorContext:
    """The one error for an unknown person and a non-co-member alike (ADR-088 §7)."""
    return Errors.not_found(resource="User", identifier=identifier)


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
        *,
        require_co_membership: bool = True,
    ) -> Result[bool]:
        """Share an owned, shareable entity with one person (``SHARES_WITH``).

        R8 (ADR-088 §7): the recipient must share a group with the owner,
        and the write re-checks that in its own statement, so a membership
        change after the caller's validation refuses here rather than
        landing an unauthorised edge. Only the forms' ``share_with_admin``
        passes ``require_co_membership=False``. The bool is ``created`` —
        True when this call wrote the link, False when it already stood —
        both successes. A recipient the guard refuses, or one that does not
        exist, is one not-found (the door discloses nothing about who
        exists).

        Backend: SharingBackend.create_share
        """
        check = await self._verify_owned_and_shareable(entity_uid, owner_uid)
        if check.is_error:
            return check

        result = await self.backend.create_share(
            entity_uid=entity_uid,
            owner_uid=UserUID(owner_uid),
            recipient_uid=recipient_uid,
            role=role,
            share_version=share_version,
            shared_at=datetime.now().isoformat(),
            require_co_membership=require_co_membership,
        )
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        if not rows:
            return Result.fail(_person_not_found(recipient_uid))
        created = bool(rows[0].get("created"))
        logger.info(
            f"Entity {entity_uid} shared with {recipient_uid} as {role} (created={created})"
        )
        return Result.ok(created)

    async def resolve_co_member(self, owner_uid: str, username: str) -> Result[str | None]:
        """The uid of the user named ``username`` when they share a group with the owner (R8).

        ``None`` for an unknown username and for a non-co-member alike — the
        one uniform answer ADR-088 §7 requires. The owner's own username
        resolves to the owner's uid; the caller refuses that.

        Backend: SharingBackend.query_co_member_uid
        """
        result = await self.backend.query_co_member_uid(UserUID(owner_uid), username=username)
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        return Result.ok(neo4j_opt_str(rows[0], "uid") if rows else None)

    async def shares_group_with(self, owner_uid: str, recipient_uid: str) -> Result[bool]:
        """Whether ``recipient_uid`` exists and shares a group with the owner (R8, ADR-088 §7).

        Co-membership through a default group counts only when one of the two
        owns it; a user's own uid is never a co-member here.

        Backend: SharingBackend.query_co_member_uid
        """
        if recipient_uid == owner_uid:
            return Result.ok(False)
        result = await self.backend.query_co_member_uid(
            UserUID(owner_uid), recipient_uid=recipient_uid
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(bool(result.value))

    async def reachable_groups(
        self, user_uid: str, group_uids: list[str]
    ) -> Result[frozenset[str]]:
        """The subset of ``group_uids`` the user may share with or submit to: existing, active, joined or owned.

        Backend: SharingBackend.query_reachable_groups
        """
        if not group_uids:
            return Result.ok(frozenset())
        result = await self.backend.query_reachable_groups(UserUID(user_uid), list(group_uids))
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            frozenset(
                uid
                for row in (result.value or [])
                if (uid := neo4j_opt_str(row, "group_uid")) is not None
            )
        )

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
        """Publish (PUBLIC) or unpublish (PRIVATE) an owned entity.

        Only the owner can change it. Publishing requires a shareable entity
        (the same rule every share applies); unpublishing never does. The
        property is publication only — who else may open the entity is the
        share links' record (ADR-088 §4), so this never widens an audience.
        """
        if visibility is Visibility.PUBLIC:
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

    async def submit_to_group(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        group_uid: str,
    ) -> Result[bool]:
        """File a feedback request with the teachers who own a group.

        Writes ``SUBMITTED_TO_GROUP`` (ADR-088 §2): the group's owners see the
        entity in their review surfaces; its members see nothing. The
        submitter must own or belong to the group, and the group must be
        active — the backend statement enforces both, and an empty result is
        the forbidden refusal (a missing entity or group, or no qualifying
        membership), never a not-found, so callers can name the reason.

        The returned bool is ``created``: True when this call wrote the link,
        False when the request already stood. Both are successes — a re-sync
        that re-files the same request is idempotent — and only the created
        subset rings a teacher's bell.

        Backend: SharingBackend.create_group_submission
        """
        # A feedback request is Submit, not Share (ADR-088 §1): a private
        # entry may still ask its teacher — only the archived gate applies.
        check = await self._verify_owned_and_shareable(entity_uid, owner_uid, privacy_gated=False)
        if check.is_error:
            return check

        result = await self.backend.create_group_submission(
            entity_uid=entity_uid,
            owner_uid=UserUID(owner_uid),
            group_uid=group_uid,
            submitted_at=datetime.now().isoformat(),
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.forbidden(
                    action="submit to group",
                    reason=(
                        f"Cannot submit {entity_uid} to group {group_uid}: "
                        "you must own or be a member of the group, "
                        "or the group does not exist or is inactive."
                    ),
                )
            )
        created = bool(records[0].get("created"))
        logger.info(
            f"Entity {entity_uid} submitted to group {group_uid} "
            f"({'new request' if created else 'request already filed'})"
        )
        return Result.ok(created)

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

    async def _verify_owned_and_shareable(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        *,
        require_shareable: bool = True,
        privacy_gated: bool = True,
    ) -> Result[bool]:
        """Verify ownership and optionally shareable status in a single query.

        Returns not_found for both missing entities and ownership mismatches
        to prevent UID enumeration. ``privacy_gated`` is the Share verb's
        rule — a ``private: true`` UserEntry, or one on a private pipeline,
        cannot be shared at any time (ADR-088 §1); a feedback request passes
        ``False`` and keeps only the archived gate.
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

        return self._check_shareable(
            str(record["status"] or ""),
            str(record["entity_type"] or ""),
            private=bool(record.get("private")),
            pipeline=neo4j_opt_str(record, "pipeline"),
            privacy_gated=privacy_gated,
        )

    @staticmethod
    def _check_shareable(
        status: str,
        entity_type: str,
        *,
        private: bool = False,
        pipeline: str | None = None,
        privacy_gated: bool = True,
    ) -> Result[bool]:
        """Evaluate whether an entity with the given status / type / privacy can be shared."""
        if entity_type in _USER_ENTRY_TYPES:
            if status == "archived":
                return Result.fail(
                    Errors.validation(
                        f"Archived user entries cannot be shared. Current status: {status}"
                    )
                )
            if privacy_gated and private:
                return Result.fail(
                    Errors.validation(
                        "A private entry (private: true) cannot be shared; a feedback "
                        "request is still allowed"
                    )
                )
            if privacy_gated and pipeline is not None and not Pipeline(pipeline).allows_sharing():
                return Result.fail(
                    Errors.validation(
                        f"pipeline={pipeline} is private (journals are not shareable); a "
                        "feedback request is still allowed"
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
