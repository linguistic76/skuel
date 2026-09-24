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
    # The feedback request; the bool is ``created`` (True = a new link).
    svc.submit_to_group = AsyncMock(return_value=Result.ok(True))
    backend = MagicMock()
    backend.query_exercise_groups_for_member = AsyncMock(return_value=Result.ok([]))
    backend.query_default_groups_for_curriculum_submission = AsyncMock(return_value=Result.ok([]))
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
        """An explicit group on TEACHER_REVIEW is routed to ``submit_to_groups``
        by the request model — a feedback target, so the validator passes."""
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            share_with_groups=["g1"],
        )
        assert req.submit_to_groups == ["g1"]
        assert resolver.validate(req).is_ok

    def test_teacher_review_with_submit_to_groups_passes(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            submit_to_groups=["g1"],
        )
        assert resolver.validate(req).is_ok

    def test_teacher_review_with_only_a_person_share_fails(self):
        """A share asks nobody for feedback (R5): ``share_with_users`` alone is
        not a feedback target, so TEACHER_REVIEW is refused."""
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            share_with_users=["user_peer"],
        )
        result = resolver.validate(req)
        assert result.is_error
        assert "feedback target" in str(result.expect_error()).lower()

    def test_journal_pipeline_rejects_submit_to_groups(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.REFERENCE,
            submit_to_groups=["g1"],
        )
        result = resolver.validate(req)
        assert result.is_error
        assert "private" in str(result.expect_error()).lower()

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
        assert outcome.submitted_groups == ()
        assert outcome.shared_groups == ()
        assert outcome.shared_users == ()

    @pytest.mark.asyncio
    async def test_explicit_groups_on_teacher_review_file_feedback_requests(self):
        """An explicit group on TEACHER_REVIEW is a feedback request
        (SUBMITTED_TO_GROUP): never a share, so classmates see nothing."""
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
        assert outcome.submitted_groups == ("g1", "g2")
        assert outcome.newly_submitted_groups == ("g1", "g2")
        assert outcome.shared_groups == ()
        assert outcome.any_success is True
        assert outcome.any_failure is False
        assert sharing.submit_to_group.await_count == 2
        sharing.share_with_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_explicit_groups_on_none_pipeline_share(self):
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.NONE,
            share_with_groups=["g1"],
        )

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        assert result.value.shared_groups == ("g1",)
        assert result.value.submitted_groups == ()
        sharing.share_with_group.assert_awaited_once()
        sharing.submit_to_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_matched_request_is_a_success_and_only_a_created_one_is_new(self):
        """``submitted_groups`` = every MERGE that matched (a re-filed request
        is reach, not zero reach); ``newly_submitted_groups`` = the created
        subset, the only thing that rings a teacher."""
        sharing = _make_sharing_service()
        sharing.submit_to_group = AsyncMock(side_effect=[Result.ok(False), Result.ok(True)])
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            submit_to_groups=["g_existing", "g_new"],
        )

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        outcome = result.value
        assert outcome.submitted_groups == ("g_existing", "g_new")
        assert outcome.newly_submitted_groups == ("g_new",)
        assert outcome.any_success is True

    @pytest.mark.asyncio
    async def test_feedback_target_on_a_pipeline_without_a_reviewer_writes_no_link(self):
        """A feedback request requires TEACHER_REVIEW: ``teachers`` (the web
        flag or the vault value) on any other pipeline files nothing and
        shares nothing — the exercise's groups are not even resolved."""
        sharing = _make_sharing_service()
        sharing.backend.query_exercise_groups_for_member = AsyncMock(
            return_value=Result.ok([{"group_uid": "g_class"}])
        )
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.NONE,
            fulfills_exercise_uid="ex_1",
            submit_to_groups=["g1"],
            auto_share_to_exercise_groups=True,
        )

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        assert result.value == ShareOutcome()
        sharing.submit_to_group.assert_not_called()
        sharing.share_with_group.assert_not_called()
        sharing.backend.query_exercise_groups_for_member.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_failure_is_collected_not_raised(self):
        from core.utils.result_simplified import Errors

        sharing = _make_sharing_service()
        sharing.submit_to_group = AsyncMock(
            side_effect=[Result.ok(True), Result.fail(Errors.database("submit", "nope"))]
        )
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            submit_to_groups=["g1", "g2"],
        )

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        outcome = result.value
        assert outcome.submitted_groups == ("g1",)
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
        assert result.value.submitted_groups == ("g_class",)
        assert result.value.shared_groups == ()
        sharing.backend.query_exercise_groups_for_member.assert_awaited_once_with(
            exercise_uid="ex_1", user_uid="user_1"
        )
        sharing.share_with_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_curriculum_fallback_files_with_the_default_group(self):
        """A curriculum exercise is never assigned to a group, so the request
        goes to the submitter's default group — under SUBMITTED_TO_GROUP it
        reaches only that group's owner, never its members."""
        sharing = _make_sharing_service()
        sharing.backend.query_default_groups_for_curriculum_submission = AsyncMock(
            return_value=Result.ok([{"group_uid": "group_default_user_admin"}])
        )
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_curriculum",
        )

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        assert result.value.submitted_groups == ("group_default_user_admin",)
        _, kwargs = sharing.submit_to_group.await_args
        assert kwargs["group_uid"] == "group_default_user_admin"
        sharing.share_with_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_explicit_feedback_target_skips_the_exercise_groups(self):
        sharing = _make_sharing_service()
        sharing.backend.query_exercise_groups_for_member = AsyncMock(
            return_value=Result.ok([{"group_uid": "g_class"}])
        )
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        req = UserEntryCreateRequest(
            title="x",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_1",
            submit_to_groups=["g_one_teacher"],
        )

        result = await resolver.resolve_and_share("ue_1", "user_1", req)

        assert result.is_ok
        assert result.value.submitted_groups == ("g_one_teacher",)
        sharing.backend.query_exercise_groups_for_member.assert_not_called()

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
        assert result.value.submitted_groups == ("g_A",)
        # Exactly one request filed — with A, not B.
        assert sharing.submit_to_group.await_count == 1
        _, kwargs = sharing.submit_to_group.await_args
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
            submitted_groups=("g_t", "g_old"),
            newly_submitted_groups=("g_t",),
            shared_groups=("g1",),
            shared_users=("u1",),
            failed=(("g2", "nope"),),
        )
        payload = outcome.to_payload()
        assert payload["submitted_groups"] == ["g_t", "g_old"]
        assert payload["newly_submitted_groups"] == ["g_t"]
        assert payload["shared_groups"] == ["g1"]
        assert payload["shared_users"] == ["u1"]
        assert payload["failed"] == [{"target": "g2", "reason": "nope"}]

    def test_default_outcome_is_empty(self):
        outcome = ShareOutcome()
        assert outcome.any_success is False
        assert outcome.any_failure is False

    def test_a_feedback_request_alone_is_a_success(self):
        """Without this, a vault copy that only filed a request would read as
        zero reach and be compensated away."""
        assert ShareOutcome(submitted_groups=("g_t",)).any_success is True
