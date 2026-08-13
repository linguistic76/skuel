# skuel-lint: disable-file=SKUEL005 -- fail-soft resolver by design: empty list is the documented safe fallback at every layer
"""
AudienceResolver — shared audience helper for UserEntry creation paths.

Both `UserEntryService.create_entry()` (the `/submit` form path) and
the `/upload` ingestion path need to validate audience declarations on a
`UserEntryCreateRequest` and resolve them into actual SHARES_WITH /
SHARED_WITH_GROUP edges. This module is the single home for that logic so
the two front-ends cannot drift.

Public surface:
    - ``ShareOutcome``           — frozen result dataclass
    - ``AudienceResolver``       — validate + resolve_and_share + resolve_default_teachers

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.models.enums import GroupMemberRole
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.type_hints import EntityUID, UserUID
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.groups.group_service import GroupService
    from core.services.sharing.unified_sharing_service import UnifiedSharingService

logger = get_logger("skuel.services.user_entry.audience_resolver")


@dataclass(frozen=True)
class ShareOutcome:
    """Result of a post-persist audience resolution pass.

    ``shared_groups`` / ``shared_users`` are the targets that succeeded.
    ``failed`` pairs each failed target with its error message so callers can
    surface partial-success warnings without re-fetching.
    """

    shared_groups: tuple[str, ...] = field(default_factory=tuple)
    shared_users: tuple[str, ...] = field(default_factory=tuple)
    failed: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def any_success(self) -> bool:
        return bool(self.shared_groups) or bool(self.shared_users)

    @property
    def any_failure(self) -> bool:
        return bool(self.failed)

    def to_payload(self) -> dict[str, Any]:
        return {
            "shared_groups": list(self.shared_groups),
            "shared_users": list(self.shared_users),
            "failed": [{"target": t, "reason": r} for t, r in self.failed],
        }


class AudienceResolver:
    """Validate + resolve audience declarations on a UserEntryCreateRequest.

    The resolver is deliberately stateless — callers pass the request and
    the freshly-persisted entry's UID into ``resolve_and_share``. Failures
    are collected into ``ShareOutcome`` rather than raised; the caller
    decides whether to compensate (delete the orphan entry) or surface
    partial-success warnings.
    """

    def __init__(
        self,
        sharing_service: UnifiedSharingService | None,
        group_service: GroupService | None,
    ) -> None:
        self.sharing_service = sharing_service
        self.group_service = group_service
        self.logger = logger

    # =========================================================================
    # VALIDATE
    # =========================================================================

    def validate(self, request: UserEntryCreateRequest) -> Result[None]:
        """ADR §3 + §5 guardrails on audience for this pipeline.

        §3 (TEACHER_REVIEW must resolve to a real audience):
          - Explicit ``share_with_groups`` / ``share_with_users`` OR
            ``fulfills_exercise_uid`` (auto-share to exercise groups)
          - Rejected: ``pipeline=TEACHER_REVIEW`` with none of the above.

        §5 (journal is PRIVATE):
          - ``Pipeline.allows_sharing()`` returns ``False`` for the journal
            pipeline (``TRANSCRIBE_AND_STRUCTURE``). Any explicit audience on
            such a request is rejected — the journal norm is preserved from
            the legacy ``JeInput``/``JeOutput`` split.
        """
        if not request.pipeline.allows_sharing():
            has_explicit_audience = bool(
                request.share_with_groups
                or request.share_with_users
                or request.auto_share_to_exercise_groups
                or (request.visibility is not None and request.visibility != Visibility.PRIVATE)
            )
            if has_explicit_audience:
                return Result.fail(
                    Errors.validation(
                        f"pipeline={request.pipeline.value} is private "
                        "(journals are not shareable at submit time)",
                        field="audience",
                    )
                )
            return Result.ok(None)

        if request.pipeline != Pipeline.TEACHER_REVIEW:
            return Result.ok(None)
        has_audience = bool(
            request.share_with_groups or request.share_with_users or request.fulfills_exercise_uid
        )
        if not has_audience:
            return Result.fail(
                Errors.validation(
                    "pipeline=TEACHER_REVIEW requires an audience: set "
                    "fulfills_exercise_uid, share_with_groups, or share_with_users",
                    field="audience",
                )
            )
        return Result.ok(None)

    # =========================================================================
    # REFERENCE VALIDATION (authorization guard)
    # =========================================================================

    async def validate_references(
        self,
        user_uid: UserUID,
        fulfills_exercise_uid: str | None,
        transforms_of_uid: str | None,
    ) -> Result[None]:
        """Verify the uploader has a legitimate claim to referenced entities.

        YAML uploads can name any UID in ``fulfills_exercise_uid`` /
        ``transforms_of_uid``. Without validation, a user could submit a
        UserEntry that silently attaches to an exercise or predecessor
        entry they have no relationship to — enabling cross-tenant leakage
        via the exercise auto-share fan-out, or masquerading a transforms
        chain over someone else's entry.

        Policy:
          - ``fulfills_exercise_uid``: user must be the exercise's owner, a
            member of a group the exercise is shared with, or currently in
            progress on a PathStep the exercise is linked to.
          - ``transforms_of_uid``: predecessor entry must belong to the
            uploader (TRANSFORMS chains are per-user).

        Returns a ``forbidden`` error on miss; ``not_found`` when the
        referenced entity doesn't exist; ``Result.ok(None)`` otherwise.
        """
        if self.sharing_service is None:
            # No backend to verify against — fail closed.
            if fulfills_exercise_uid or transforms_of_uid:
                return Result.fail(
                    Errors.forbidden(
                        action="reference external entity",
                        reason=(
                            "Cannot verify relationship to referenced entity — "
                            "sharing service unavailable."
                        ),
                    )
                )
            return Result.ok(None)

        backend = self.sharing_service.backend

        if fulfills_exercise_uid:
            allowed = await backend.query_user_can_use_exercise(
                exercise_uid=EntityUID(fulfills_exercise_uid),
                user_uid=user_uid,
            )
            if allowed.is_error:
                return Result.fail(allowed)
            if not allowed.value:
                return Result.fail(
                    Errors.forbidden(
                        action="submit for exercise",
                        reason=(
                            f"Exercise {fulfills_exercise_uid} is not assigned to "
                            "any of your groups and you are not its owner."
                        ),
                    )
                )

        if transforms_of_uid:
            owner = await backend.query_entity_owner(entity_uid=EntityUID(transforms_of_uid))
            if owner.is_error:
                return Result.fail(owner)
            if owner.value is None:
                return Result.fail(
                    Errors.not_found(resource="UserEntry", identifier=transforms_of_uid)
                )
            if owner.value != user_uid:
                return Result.fail(
                    Errors.forbidden(
                        action="transform predecessor entry",
                        reason=(f"Predecessor entry {transforms_of_uid} belongs to another user."),
                    )
                )

        return Result.ok(None)

    # =========================================================================
    # RESOLVE & SHARE
    # =========================================================================

    async def resolve_and_share(
        self,
        entry_uid: str,
        user_uid: UserUID,
        request: UserEntryCreateRequest,
    ) -> Result[ShareOutcome]:
        """Audience resolution + share calls. Returns which targets landed.

        Policy:
          1. Explicit ``share_with_groups`` / ``share_with_users`` — share
             directly via ``UnifiedSharingService``.
          2. ``auto_share_to_exercise_groups=True`` (or, for programmatic
             callers, implicit ``pipeline=TEACHER_REVIEW`` with exercise and
             no explicit shares) — resolve the exercise's assigned groups
             and SHARED_WITH_GROUP to each.
          3. Otherwise — no sharing (default visibility=PRIVATE).

        Failures are collected into the returned ``ShareOutcome`` rather than
        propagated — the caller decides whether to compensate (delete the
        just-persisted entry) or surface partial-success warnings.
        """
        if self.sharing_service is None:
            return Result.ok(ShareOutcome())

        shared_groups: list[str] = []
        shared_users: list[str] = []
        failed: list[tuple[str, str]] = []

        for group_uid in request.share_with_groups:
            result = await self.sharing_service.share_with_group(
                entity_uid=EntityUID(entry_uid),
                owner_uid=user_uid,
                group_uid=group_uid,
            )
            if result.is_error:
                reason = str(result.expect_error())
                self.logger.warning(
                    f"Failed to share UserEntry {entry_uid} with group {group_uid}: {reason}"
                )
                failed.append((group_uid, reason))
            else:
                shared_groups.append(group_uid)

        for recipient_uid in request.share_with_users:
            result = await self.sharing_service.share(
                entity_uid=EntityUID(entry_uid),
                owner_uid=user_uid,
                recipient_uid=recipient_uid,
            )
            if result.is_error:
                reason = str(result.expect_error())
                self.logger.warning(
                    f"Failed to share UserEntry {entry_uid} with user {recipient_uid}: {reason}"
                )
                failed.append((recipient_uid, reason))
            else:
                shared_users.append(recipient_uid)

        # Auto-share to exercise groups: explicit flag wins; otherwise fall
        # back to the implicit TEACHER_REVIEW+exercise+no-explicit-shares path
        # so programmatic callers keep working without the new flag.
        shared_any = bool(shared_groups) or bool(shared_users)
        should_auto_share = request.auto_share_to_exercise_groups or (
            not shared_any and request.pipeline == Pipeline.TEACHER_REVIEW
        )
        if should_auto_share and request.fulfills_exercise_uid:
            # Auto-share is scoped to the intersection of the exercise's
            # assigned groups and the uploader's memberships. Without this
            # intersection, an exercise assigned to groups A and B would
            # leak a submission from a member of A out to group B even
            # though that uploader has no relationship to B.
            groups_result = await self.sharing_service.backend.query_exercise_groups_for_member(
                exercise_uid=request.fulfills_exercise_uid,
                user_uid=user_uid,
            )
            if groups_result.is_error:
                reason = str(groups_result.expect_error())
                self.logger.warning(f"Could not resolve exercise groups for auto-share: {reason}")
                failed.append((request.fulfills_exercise_uid, reason))
            else:
                records = list(groups_result.value or [])
                if not records:
                    # Curriculum fallback (ruled 2026-07-04): vault-authored
                    # exercises are never ASSIGNED to a group, so the
                    # intersection is empty and a teacher_review submission
                    # would dissolve with no reviewer. Route it to the
                    # submitter's default group (owned by the default
                    # teacher). The backend query is scope-gated: zero rows
                    # for non-curriculum exercises.
                    fallback = await self.sharing_service.backend.query_default_groups_for_curriculum_submission(
                        exercise_uid=request.fulfills_exercise_uid,
                        user_uid=user_uid,
                    )
                    if fallback.is_error:
                        reason = str(fallback.expect_error())
                        self.logger.warning(f"Curriculum default-group fallback failed: {reason}")
                        failed.append((request.fulfills_exercise_uid, reason))
                    else:
                        records = list(fallback.value or [])
                for record in records:
                    raw = record.get("group_uid") if isinstance(record, dict) else None
                    if not raw:
                        continue
                    group_uid_str = str(raw)
                    share_result = await self.sharing_service.share_with_group(
                        entity_uid=EntityUID(entry_uid),
                        owner_uid=user_uid,
                        group_uid=group_uid_str,
                    )
                    if share_result.is_error:
                        reason = str(share_result.expect_error())
                        self.logger.warning(
                            f"Auto-share of {entry_uid} to group {group_uid_str} failed: {reason}"
                        )
                        failed.append((group_uid_str, reason))
                    else:
                        shared_groups.append(group_uid_str)

        return Result.ok(
            ShareOutcome(
                shared_groups=tuple(shared_groups),
                shared_users=tuple(shared_users),
                failed=tuple(failed),
            )
        )

    # =========================================================================
    # DEFAULT-AUDIENCE EXPANSION (ingestion only)
    # =========================================================================

    async def resolve_default_teachers(self, user_uid: UserUID) -> list[str]:
        """Expand ``audience: teachers`` (the YAML-ingestion default) to
        the explicit list of group UIDs the user is a student-member of.

        The student is sharing with "their teachers" by sharing the entry
        with each group they're enrolled in as a student — teachers of those
        groups then see the entry via group membership.

        Returns ``[]`` when the user is in no groups, when the group service
        is unavailable, or when the underlying lookup fails. Callers treat
        an empty list as "save privately, no shares" — there is no implicit
        "share with everyone" fallback.
        """
        if self.group_service is None:
            return []
        result = await self.group_service.get_user_groups(
            user_uid, role=GroupMemberRole.STUDENT.value
        )
        if result.is_error:
            self.logger.warning(
                f"Could not resolve default-teacher groups for {user_uid}: {result.expect_error()}"
            )
            return []
        return [g.uid for g in (result.value or [])]


__all__ = ["AudienceResolver", "ShareOutcome"]
