"""
Entry Sharing Service — the Share / Stop-sharing door on a UserEntry
====================================================================

The post-create half of R1's **Share** verb (Submit & Share arc R2, R7, R8):
an owner shares an entry they already have with groups and people, takes a
share back, and sees whom the Share panel may offer. Every operation is
UserEntry-only (any other entity is not-found) and owner-only (a non-owner
gets the same not-found as a missing entry).

The rules are the create path's, not a second copy: the targets are checked
by ``AudienceResolver.resolve_people`` / ``check_groups_reachable`` before the
first write, the links are written by ``AudienceResolver.resolve_and_share``
(the same guarded MERGEs), and the lifetime privacy rule — a ``private: true``
entry or a private pipeline never shares — is ``UnifiedSharingService``'s own
check inside ``share`` / ``share_with_group``. The vocabulary is
``AudienceSpec``; this door accepts ``group:<uid>`` and ``user:<username>``
only — ``teachers`` / ``teacher:`` are Submit (the Submit page), ``public``
waits on the PUBLIC reader, ``private`` names nobody.

A new person share rings its recipient (``EntryShared`` → the
``shared_with_you`` bell); a share that already stood, and a group share,
ring no one (R10). ``publish_entry_shared`` is the one publisher, used here
and by ``UserEntryService.create_entry``.

See: /docs/decisions/ADR-088-submit-and-share.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.events import publish_event
from core.events.user_entry_events import EntryShared
from core.models.enums import GroupMemberRole
from core.models.type_hints import EntityUID, UserUID
from core.models.user_entry.audience import GROUP_PREFIX, USER_PREFIX, AudienceSpec
from core.services.user_entry.audience_resolver import ResolvedAudience, ShareOutcome
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import logging

    import structlog

    from core.models.user_entry.user_entry import UserEntry
    from core.ports.group_protocols import GroupOperations
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.query_types import ShareCandidates, SharedByMeItem
    from core.ports.sharing_protocols import SharingOperations
    from core.services.user_entry.user_entry_service import UserEntryService

logger = get_logger("skuel.services.user_entry.sharing")

_SHARE_ONLY = (
    f"Share takes {GROUP_PREFIX}<uid> and {USER_PREFIX}<username> only — a feedback "
    "request (teachers / teacher:<group_uid>) is Submit, and public waits on the portfolio"
)


async def publish_entry_shared(  # skuel-lint: disable=SKUEL005 -- an event publisher: nothing to return, publish_event logs a missing bus
    event_bus: EventBusOperations | None,
    entry: UserEntry,
    outcome: ShareOutcome,
    log: structlog.BoundLogger | logging.Logger,
) -> None:
    """Ring every recipient whose ``SHARES_WITH`` this pass created — one ``EntryShared`` each."""
    for recipient_uid in outcome.newly_shared_users:
        await publish_event(
            event_bus,
            EntryShared(
                entity_uid=entry.uid,
                owner_uid=UserUID(entry.user_uid),
                recipient_uid=UserUID(recipient_uid),
                title=entry.title,
            ),
            log,
        )


class EntrySharingService:
    """Share, Stop sharing and the Share panel's candidates, for an owned UserEntry."""

    def __init__(
        self,
        entries: UserEntryService,
        sharing: SharingOperations,
        groups: GroupOperations,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        self.entries = entries
        self.sharing = sharing
        self.groups = groups
        self.event_bus = event_bus
        self.logger = logger

    # ------------------------------------------------------------------
    # The owner read every door starts with
    # ------------------------------------------------------------------

    async def _owned_entry(self, entry_uid: str, owner_uid: UserUID) -> Result[UserEntry]:
        """The entry, when it is a UserEntry the caller owns; one not-found otherwise.

        ``UserEntryService.get_entry`` reads by the ``:UserEntry`` label, so any
        other entity is absent here — a Task the caller owns gets the same
        not-found as a stranger's entry.
        """
        result = await self.entries.get_entry(entry_uid, owner_uid)
        if result.is_error:
            return Result.fail(result)
        entry = result.value
        if entry is None:
            return Result.fail(Errors.not_found(resource="UserEntry", identifier=entry_uid))
        return Result.ok(entry)

    # ------------------------------------------------------------------
    # Share
    # ------------------------------------------------------------------

    async def share(
        self, entry_uid: str, owner_uid: UserUID, audience: AudienceSpec
    ) -> Result[ShareOutcome]:
        """Share an owned entry with the groups and people ``audience`` names.

        Every target is checked before the first write; each write re-checks
        its own authorisation and the entry's lifetime privacy rule. A pass
        in which nothing landed returns its first refusal as the error; a
        partial pass returns the outcome, which names what failed. New
        person shares ring their recipients.
        """
        if audience.is_empty:
            return Result.fail(Errors.validation("Nobody to share with", field="audience"))
        if audience.names_feedback_target or audience.public or audience.private:
            return Result.fail(Errors.validation(_SHARE_ONLY, field="audience"))

        owned = await self._owned_entry(entry_uid, owner_uid)
        if owned.is_error:
            return Result.fail(owned)
        entry = owned.value

        resolver = self.entries.audience_resolver
        people = await resolver.resolve_people(owner_uid, audience.share_users)
        if people.is_error:
            return Result.fail(people)
        groups_check = await resolver.check_groups_reachable(owner_uid, audience.share_groups)
        if groups_check.is_error:
            return Result.fail(groups_check)

        written = await resolver.resolve_and_share(
            entry_uid=entry.uid,
            user_uid=owner_uid,
            pipeline=entry.pipeline,
            resolved=ResolvedAudience(
                share_groups=tuple(audience.share_groups), share_users=people.value
            ),
        )
        if written.is_error:
            return Result.fail(written)
        outcome = written.value
        if outcome.any_failure and not outcome.any_success:
            _target, reason = outcome.failed[0]
            return Result.fail(Errors.validation(reason, field="audience"))

        await publish_entry_shared(self.event_bus, entry, outcome, self.logger)
        return Result.ok(outcome)

    # ------------------------------------------------------------------
    # Stop sharing
    # ------------------------------------------------------------------

    async def unshare(self, entry_uid: str, owner_uid: UserUID, target: str) -> Result[str]:
        """Take one share back: ``group:<uid>`` deletes its ``SHARED_WITH_GROUP``, ``user:<username>`` their ``SHARES_WITH``.

        Exactly one share target; a feedback request cannot be cancelled here
        (the delete never touches ``SUBMITTED_TO_GROUP``). Returns the value
        removed. A share that does not stand is a not-found.
        """
        parsed = AudienceSpec.parse([target])
        if parsed.is_error:
            return Result.fail(parsed)
        spec = parsed.value
        targets = [*spec.share_groups, *spec.share_users]
        if (
            spec.names_feedback_target
            or spec.public
            or spec.private
            or len(targets) != 1
            or len(spec.share_groups) + len(spec.share_users) != 1
        ):
            return Result.fail(
                Errors.validation(
                    f"Stop sharing takes one {GROUP_PREFIX}<uid> or {USER_PREFIX}<username>",
                    field="audience",
                )
            )

        owned = await self._owned_entry(entry_uid, owner_uid)
        if owned.is_error:
            return Result.fail(owned)

        if spec.share_groups:
            group_uid = spec.share_groups[0]
            result = await self.sharing.unshare_from_group(
                entity_uid=EntityUID(entry_uid), owner_uid=owner_uid, group_uid=group_uid
            )
            value = f"{GROUP_PREFIX}{group_uid}"
        else:
            username = spec.share_users[0]
            result = await self.sharing.unshare(
                entity_uid=EntityUID(entry_uid),
                owner_uid=owner_uid,
                recipient_username=username,
            )
            value = f"{USER_PREFIX}{username}"
        if result.is_error:
            return Result.fail(result)
        return Result.ok(value)

    async def wall_row(self, entry_uid: str, owner_uid: UserUID) -> Result[SharedByMeItem | None]:
        """The entry's row on the owner's wall — its current audience — or ``None`` once nothing is shared."""
        current = await self.sharing.get_shared_by_me(
            owner_uid, limit=1, entity_uid=EntityUID(entry_uid)
        )
        if current.is_error:
            return Result.fail(current)
        return Result.ok(current.value[0] if current.value else None)

    # ------------------------------------------------------------------
    # Candidates — what the Share panel offers
    # ------------------------------------------------------------------

    async def candidates(self, entry_uid: str, owner_uid: UserUID) -> Result[ShareCandidates]:
        """The groups and people the owner may share ``entry_uid`` with, and whom it already reaches.

        Groups: the active groups the owner is a student of or owns (one
        reader, ``GroupOperations.get_user_groups``). People: the R8
        co-members (the default group's roster excluded, its owner kept).
        The current audience is the wall's read for this one entry; the
        reviewer groups (its ``SUBMITTED_TO_GROUP`` targets) are what the
        GradeBook nudge preselects, among the offered groups only.
        """
        owned = await self._owned_entry(entry_uid, owner_uid)
        if owned.is_error:
            return Result.fail(owned)

        groups = await self.groups.get_user_groups(
            owner_uid, role=GroupMemberRole.STUDENT.value, include_owned=True
        )
        if groups.is_error:
            return Result.fail(groups)
        people = await self.sharing.get_share_candidate_people(owner_uid)
        if people.is_error:
            return Result.fail(people)
        current = await self.sharing.get_shared_by_me(
            owner_uid, limit=1, entity_uid=EntityUID(entry_uid)
        )
        if current.is_error:
            return Result.fail(current)
        row = current.value[0] if current.value else None
        reviewers = await self.sharing.get_feedback_request_group_uids(EntityUID(entry_uid))
        if reviewers.is_error:
            return Result.fail(reviewers)

        return Result.ok(
            {
                "groups": [{"uid": g.uid, "name": g.name} for g in groups.value],
                "people": list(people.value),
                "shared_group_uids": [g["uid"] for g in row["groups"]] if row else [],
                "shared_user_uids": [u["uid"] for u in row["users"]] if row else [],
                "reviewer_group_uids": reviewers.value,
            }
        )


__all__ = ["EntrySharingService", "publish_entry_shared"]
