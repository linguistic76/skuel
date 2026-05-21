"""Tests for AudienceResolver (ADR-054 /upload-integration).

Covers the validator (shared with UserEntryService) and the two ingestion-
specific helpers — ``resolve_default_teachers`` and ``resolve_and_share``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.user_entry.audience_resolver import AudienceResolver, ShareOutcome
from core.utils.result_simplified import Result


def _make_sharing_service() -> MagicMock:
    svc = MagicMock()
    svc.share = AsyncMock(return_value=Result.ok(True))
    svc.share_with_group = AsyncMock(return_value=Result.ok(True))
    svc.get_groups_shared_with = AsyncMock(return_value=Result.ok([]))
    backend = MagicMock()
    backend.query_exercise_groups_for_member = AsyncMock(return_value=Result.ok([]))
    backend.query_user_can_use_exercise = AsyncMock(return_value=Result.ok(True))
    backend.query_entity_owner = AsyncMock(return_value=Result.ok(None))
    svc.backend = backend
    return svc


def _make_group_service(groups=None) -> MagicMock:
    svc = MagicMock()
    svc.get_user_groups = AsyncMock(return_value=Result.ok(groups or []))
    return svc


def _group(uid: str) -> MagicMock:
    g = MagicMock()
    g.uid = uid
    return g


class TestValidate:
    def test_none_pipeline_is_always_ok(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(title="x", pipeline=Pipeline.NONE)
        assert resolver.validate(req).is_ok

    def test_teacher_review_without_audience_fails(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(title="x", pipeline=Pipeline.TEACHER_REVIEW)
        result = resolver.validate(req)
        assert result.is_error
        assert "audience" in str(result.expect_error()).lower()

    def test_teacher_review_with_exercise_link_passes(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_foo",
        )
        assert resolver.validate(req).is_ok

    def test_teacher_review_with_groups_passes(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            share_with_groups=["g1"],
        )
        assert resolver.validate(req).is_ok

    def test_journal_pipeline_rejects_explicit_audience(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE,
            share_with_groups=["g1"],
        )
        result = resolver.validate(req)
        assert result.is_error
        assert "private" in str(result.expect_error()).lower()

    def test_journal_pipeline_without_audience_passes(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE,
            file_path="/tmp/x.mp3",
        )
        assert resolver.validate(req).is_ok


class TestResolveDefaultTeachers:
    @pytest.mark.asyncio
    async def test_returns_group_uids_for_student_memberships(self):
        group_service = _make_group_service([_group("g_math"), _group("g_science")])
        resolver = AudienceResolver(sharing_service=None, group_service=group_service)

        uids = await resolver.resolve_default_teachers("user_1")

        assert uids == ["g_math", "g_science"]
        group_service.get_user_groups.assert_awaited_once_with("user_1", role="student")

    @pytest.mark.asyncio
    async def test_empty_list_when_user_has_no_groups(self):
        group_service = _make_group_service([])
        resolver = AudienceResolver(sharing_service=None, group_service=group_service)
        assert await resolver.resolve_default_teachers("user_1") == []

    @pytest.mark.asyncio
    async def test_empty_list_when_group_service_missing(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        assert await resolver.resolve_default_teachers("user_1") == []

    @pytest.mark.asyncio
    async def test_empty_list_when_lookup_fails(self):
        from core.utils.result_simplified import Errors

        group_service = MagicMock()
        group_service.get_user_groups = AsyncMock(
            return_value=Result.fail(Errors.database("lookup", "boom"))
        )
        resolver = AudienceResolver(sharing_service=None, group_service=group_service)
        assert await resolver.resolve_default_teachers("user_1") == []


class TestResolveAndShare:
    @pytest.mark.asyncio
    async def test_no_sharing_service_returns_empty_outcome(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(title="x", pipeline=Pipeline.NONE)

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        outcome = result.value
        assert outcome.shared_groups == ()
        assert outcome.shared_users == ()

    @pytest.mark.asyncio
    async def test_explicit_groups_share_successfully(self):
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            share_with_groups=["g1", "g2"],
        )

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        outcome = result.value
        assert outcome.shared_groups == ("g1", "g2")
        assert outcome.any_success is True
        assert outcome.any_failure is False
        assert sharing.share_with_group.await_count == 2

    @pytest.mark.asyncio
    async def test_partial_failure_is_collected_not_raised(self):
        from core.utils.result_simplified import Errors

        sharing = _make_sharing_service()
        sharing.share_with_group = AsyncMock(
            side_effect=[Result.ok(True), Result.fail(Errors.database("share", "nope"))]
        )
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            share_with_groups=["g1", "g2"],
        )

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        outcome = result.value
        assert outcome.shared_groups == ("g1",)
        assert outcome.any_failure is True
        assert outcome.failed[0][0] == "g2"

    @pytest.mark.asyncio
    async def test_teacher_review_auto_share_from_exercise_groups(self):
        sharing = _make_sharing_service()
        sharing.backend.query_exercise_groups_for_member = AsyncMock(
            return_value=Result.ok([{"group_uid": "g_class"}])
        )
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_1",
        )

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        assert result.value.shared_groups == ("g_class",)
        sharing.backend.query_exercise_groups_for_member.assert_awaited_once_with(
            exercise_uid="ex_1", user_uid="user_1"
        )

    @pytest.mark.asyncio
    async def test_auto_share_filters_by_student_membership(self):
        """Exercise assigned to groups A + B; uploader only in A → only A gets the share."""
        sharing = _make_sharing_service()
        # The backend query intersects at Cypher level — returns only groups the
        # user is a member of. Simulate: exercise is assigned to {A, B}; user
        # belongs only to A.
        sharing.backend.query_exercise_groups_for_member = AsyncMock(
            return_value=Result.ok([{"group_uid": "g_A"}])
        )
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_shared_AB",
        )

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        assert result.value.shared_groups == ("g_A",)
        # Exactly one share call — to A, not B.
        assert sharing.share_with_group.await_count == 1
        _, kwargs = sharing.share_with_group.await_args
        assert kwargs["group_uid"] == "g_A"


class TestValidateReferences:
    @pytest.mark.asyncio
    async def test_missing_sharing_service_rejects_any_reference(self):
        """Fail-closed: without a backend we cannot verify relationships."""
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        result = await resolver.validate_references(
            user_uid="user_1",
            fulfills_exercise_uid="ex_1",
            transforms_of_uid=None,
        )
        assert result.is_error
        assert "verify" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_no_references_passes_without_service(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        result = await resolver.validate_references(
            user_uid="user_1",
            fulfills_exercise_uid=None,
            transforms_of_uid=None,
        )
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_rejects_unassigned_exercise(self):
        sharing = _make_sharing_service()
        sharing.backend.query_user_can_use_exercise = AsyncMock(return_value=Result.ok(False))
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(
            user_uid="user_1",
            fulfills_exercise_uid="ex_not_mine",
            transforms_of_uid=None,
        )

        assert result.is_error
        err = str(result.expect_error()).lower()
        assert "exercise" in err or "group" in err

    @pytest.mark.asyncio
    async def test_accepts_assigned_exercise(self):
        sharing = _make_sharing_service()
        sharing.backend.query_user_can_use_exercise = AsyncMock(return_value=Result.ok(True))
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(
            user_uid="user_1",
            fulfills_exercise_uid="ex_ok",
            transforms_of_uid=None,
        )
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_rejects_unowned_transforms_of(self):
        sharing = _make_sharing_service()
        sharing.backend.query_entity_owner = AsyncMock(return_value=Result.ok("other_user"))
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(
            user_uid="user_1",
            fulfills_exercise_uid=None,
            transforms_of_uid="ue_not_mine",
        )

        assert result.is_error
        assert "predecessor" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_transforms_of_missing_entity_returns_not_found(self):
        sharing = _make_sharing_service()
        sharing.backend.query_entity_owner = AsyncMock(return_value=Result.ok(None))
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(
            user_uid="user_1",
            fulfills_exercise_uid=None,
            transforms_of_uid="ue_missing",
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_accepts_owned_transforms_of(self):
        sharing = _make_sharing_service()
        sharing.backend.query_entity_owner = AsyncMock(return_value=Result.ok("user_1"))
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(
            user_uid="user_1",
            fulfills_exercise_uid=None,
            transforms_of_uid="ue_mine",
        )
        assert result.is_ok


class TestShareOutcome:
    def test_to_payload_shape(self):
        outcome = ShareOutcome(
            shared_groups=("g1",),
            shared_users=("u1",),
            failed=(("g2", "nope"),),
        )
        payload = outcome.to_payload()
        assert payload["shared_groups"] == ["g1"]
        assert payload["shared_users"] == ["u1"]
        assert payload["failed"] == [{"target": "g2", "reason": "nope"}]

    def test_default_outcome_is_empty(self):
        outcome = ShareOutcome()
        assert outcome.any_success is False
        assert outcome.any_failure is False
