"""EntrySharingService — the Share / Stop-sharing door (Submit & Share arc PR 6b).

The door is UserEntry-only and owner-only, speaks the vocabulary's two share
values only, checks every target before the first write through the create
path's own checks, and rings a recipient once per new person share.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.group.group import create_group
from core.models.user_entry.audience import AudienceSpec
from core.models.user_entry.user_entry import UserEntry
from core.services.user_entry.audience_resolver import AudienceResolver, ShareOutcome
from core.services.user_entry.entry_sharing_service import EntrySharingService
from core.utils.result_simplified import Errors, Result

OWNER = "user_owner"
ENTRY = "ue_1"


def _entry(**overrides) -> UserEntry:
    fields = {"uid": ENTRY, "title": "My essay", "user_uid": OWNER, "pipeline": Pipeline.NONE}
    fields.update(overrides)
    return UserEntry(**fields)


def _sharing(*, co_members: dict[str, str] | None = None, reachable=None) -> MagicMock:
    co_members = co_members or {}
    sharing = MagicMock()

    async def resolve(owner_uid, username):
        return Result.ok(co_members.get(username))

    async def reach(user_uid, group_uids):
        return Result.ok(frozenset(reachable if reachable is not None else group_uids))

    sharing.resolve_co_member = AsyncMock(side_effect=resolve)
    sharing.reachable_groups = AsyncMock(side_effect=reach)
    sharing.share = AsyncMock(return_value=Result.ok(True))
    sharing.share_with_group = AsyncMock(return_value=Result.ok(True))
    sharing.submit_to_group = AsyncMock(return_value=Result.ok(True))
    sharing.unshare = AsyncMock(return_value=Result.ok(True))
    sharing.unshare_from_group = AsyncMock(return_value=Result.ok(True))
    sharing.get_share_candidate_people = AsyncMock(
        return_value=Result.ok([{"uid": "user_a", "username": "alice", "display_name": "Alice"}])
    )
    sharing.get_shared_by_me = AsyncMock(return_value=Result.ok([]))
    sharing.get_feedback_request_group_uids = AsyncMock(return_value=Result.ok(["g_1", "g_gone"]))
    return sharing


_OWNED = object()


def _service(
    sharing: MagicMock, *, entry: UserEntry | object | None = _OWNED
) -> EntrySharingService:
    entries = MagicMock()
    entries.get_entry = AsyncMock(return_value=Result.ok(_entry() if entry is _OWNED else entry))
    entries.audience_resolver = AudienceResolver(sharing_service=sharing, group_service=None)
    groups = MagicMock()
    groups.get_user_groups = AsyncMock(
        return_value=Result.ok([create_group(uid="g_1", name="Physics", owner_uid="user_t")])
    )
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    return EntrySharingService(entries=entries, sharing=sharing, groups=groups, event_bus=bus)


def _bus(service: EntrySharingService) -> AsyncMock:
    """The mocked bus's ``publish_async`` — what a bell test inspects."""
    return cast("AsyncMock", cast("MagicMock", service.event_bus).publish_async)


class TestShare:
    @pytest.mark.asyncio
    async def test_shares_with_a_group_and_a_co_member_and_rings_the_new_recipient(self):
        sharing = _sharing(co_members={"alice": "user_a"})
        service = _service(sharing)

        result = await service.share(
            ENTRY, OWNER, AudienceSpec.parse(["group:g_1", "user:alice"]).value
        )

        assert result.is_ok, result.error
        outcome: ShareOutcome = result.value
        assert outcome.shared_groups == ("g_1",)
        assert outcome.shared_users == ("user_a",)
        assert outcome.newly_shared_users == ("user_a",)
        sharing.share_with_group.assert_awaited_once()
        sharing.share.assert_awaited_once()
        call = _bus(service).await_args
        assert call is not None
        published = call.args[0]
        assert published.event_type == "user_entry.shared"
        assert published.recipient_uid == "user_a"
        assert published.owner_uid == OWNER
        assert published.title == "My essay"

    @pytest.mark.asyncio
    async def test_a_share_that_already_stood_rings_nobody(self):
        sharing = _sharing(co_members={"alice": "user_a"})
        sharing.share = AsyncMock(return_value=Result.ok(False))
        service = _service(sharing)

        result = await service.share(ENTRY, OWNER, AudienceSpec.parse(["user:alice"]).value)

        assert result.is_ok
        assert result.value.newly_shared_users == ()
        _bus(service).assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "audience", ["teachers", "teacher:g_1", "public", "private", ["group:g_1", "teachers"]]
    )
    async def test_only_the_two_share_values_are_accepted(self, audience):
        sharing = _sharing()
        service = _service(sharing)

        result = await service.share(ENTRY, OWNER, AudienceSpec.parse(audience).value)

        assert result.is_error
        assert result.expect_error().category.value == "validation"
        sharing.share.assert_not_awaited()
        sharing.share_with_group.assert_not_awaited()
        sharing.submit_to_group.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_empty_audience_is_refused(self):
        sharing = _sharing()
        result = await _service(sharing).share(ENTRY, OWNER, AudienceSpec())
        assert result.is_error
        assert result.expect_error().category.value == "validation"

    @pytest.mark.asyncio
    async def test_a_non_owner_and_a_missing_entry_are_one_not_found(self):
        sharing = _sharing(co_members={"alice": "user_a"})
        service = _service(sharing, entry=None)

        result = await service.share(ENTRY, "user_other", AudienceSpec.parse(["user:alice"]).value)

        assert result.is_error
        assert result.expect_error().category.value == "not_found"
        sharing.share.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_every_target_is_checked_before_the_first_write(self):
        """A stranger beside a valid group refuses the whole list, nothing written."""
        sharing = _sharing(co_members={})
        service = _service(sharing)

        result = await service.share(
            ENTRY, OWNER, AudienceSpec.parse(["group:g_1", "user:stranger"]).value
        )

        assert result.is_error
        assert result.expect_error().category.value == "not_found"
        sharing.share_with_group.assert_not_awaited()
        sharing.share.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_unreachable_group_is_not_found(self):
        sharing = _sharing(reachable=[])
        result = await _service(sharing).share(
            ENTRY, OWNER, AudienceSpec.parse(["group:g_missing"]).value
        )
        assert result.is_error
        assert result.expect_error().category.value == "not_found"

    @pytest.mark.asyncio
    async def test_a_late_refusal_with_nothing_landed_is_the_error(self):
        """The lifetime privacy rule is the sharing service's own: its refusal surfaces."""
        sharing = _sharing(co_members={"alice": "user_a"})
        sharing.share = AsyncMock(
            return_value=Result.fail(Errors.validation("A private entry cannot be shared"))
        )
        service = _service(sharing)

        result = await service.share(ENTRY, OWNER, AudienceSpec.parse(["user:alice"]).value)

        assert result.is_error
        assert "private entry" in result.expect_error().message
        _bus(service).assert_not_awaited()


class TestUnshare:
    @pytest.mark.asyncio
    async def test_a_group_value_deletes_the_group_share(self):
        sharing = _sharing()
        result = await _service(sharing).unshare(ENTRY, OWNER, "group:g_1")
        assert result.is_ok
        assert result.value == "group:g_1"
        sharing.unshare_from_group.assert_awaited_once_with(
            entity_uid=ENTRY, owner_uid=OWNER, group_uid="g_1"
        )
        sharing.unshare.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_user_value_deletes_the_person_share_by_username(self):
        sharing = _sharing()
        result = await _service(sharing).unshare(ENTRY, OWNER, "user:alice")
        assert result.is_ok
        assert result.value == "user:alice"
        sharing.unshare.assert_awaited_once_with(
            entity_uid=ENTRY, owner_uid=OWNER, recipient_username="alice"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("target", ["teachers", "teacher:g_1", "public", "private", "nonsense"])
    async def test_a_feedback_request_cannot_be_cancelled_here(self, target):
        sharing = _sharing()
        result = await _service(sharing).unshare(ENTRY, OWNER, target)
        assert result.is_error
        assert result.expect_error().category.value == "validation"
        sharing.unshare.assert_not_awaited()
        sharing.unshare_from_group.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_non_owner_is_not_found(self):
        sharing = _sharing()
        result = await _service(sharing, entry=None).unshare(ENTRY, "user_other", "user:alice")
        assert result.is_error
        assert result.expect_error().category.value == "not_found"
        sharing.unshare.assert_not_awaited()


class TestCandidates:
    @pytest.mark.asyncio
    async def test_groups_people_and_the_current_audience(self):
        sharing = _sharing()
        sharing.get_shared_by_me = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "entity": MagicMock(uid=ENTRY),
                        "users": [
                            {
                                "uid": "user_a",
                                "username": "alice",
                                "display_name": "Alice",
                                "shared_at": None,
                            }
                        ],
                        "groups": [],
                        "last_shared_at": None,
                    }
                ]
            )
        )
        service = _service(sharing)

        result = await service.candidates(ENTRY, OWNER)

        assert result.is_ok, result.error
        assert result.value["groups"] == [{"uid": "g_1", "name": "Physics"}]
        assert result.value["people"] == [
            {"uid": "user_a", "username": "alice", "display_name": "Alice"}
        ]
        assert result.value["shared_user_uids"] == ["user_a"]
        assert result.value["shared_group_uids"] == []
        # the reviewer groups are reported as read — the panel intersects them
        # with the offered groups, so an unoffered one here is harmless
        assert result.value["reviewer_group_uids"] == ["g_1", "g_gone"]
        sharing.get_feedback_request_group_uids.assert_awaited_once_with(ENTRY)
        cast("AsyncMock", service.groups.get_user_groups).assert_awaited_once_with(
            OWNER, role="student", include_owned=True
        )
        sharing.get_shared_by_me.assert_awaited_once_with(OWNER, limit=1, entity_uid=ENTRY)

    @pytest.mark.asyncio
    async def test_a_non_owner_is_not_found(self):
        sharing = _sharing()
        result = await _service(sharing, entry=None).candidates(ENTRY, "user_other")
        assert result.is_error
        assert result.expect_error().category.value == "not_found"
