"""Tests for UserEntryService (ADR-054)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.models.user_entry.user_entry_request import (
    UserEntryCreateRequest,
    UserEntryUpdateRequest,
)
from core.services.user_entry.user_entry_service import ShareOutcome, UserEntryService
from core.utils.result_simplified import Errors, Result


def _make_entry(**kwargs) -> UserEntry:
    defaults = dict(
        uid="ue_test_1",
        title="Entry",
        user_uid="user_1",
        pipeline=Pipeline.NONE,
    )
    defaults.update(kwargs)
    return UserEntry(**defaults)  # type: ignore[arg-type]


def _make_backend(entry: UserEntry | None = None) -> MagicMock:
    entry = entry or _make_entry()
    backend = MagicMock()
    backend.create = AsyncMock(return_value=Result.ok(entry))
    backend.create_with_exercise_link = AsyncMock(return_value=Result.ok(entry))
    backend.count_entries_for_exercise = AsyncMock(return_value=Result.ok(0))
    backend.add_relationship = AsyncMock(return_value=Result.ok(True))
    backend.get = AsyncMock(return_value=Result.ok(entry))
    backend.update = AsyncMock(return_value=Result.ok(entry))
    backend.delete = AsyncMock(return_value=Result.ok(True))
    backend.health_check = AsyncMock(return_value=Result.ok(True))
    return backend


def _make_sharing_service() -> MagicMock:
    svc = MagicMock()
    svc.share = AsyncMock(return_value=Result.ok(True))
    svc.share_with_group = AsyncMock(return_value=Result.ok(True))
    svc.get_groups_shared_with = AsyncMock(return_value=Result.ok([]))
    backend = MagicMock()
    backend.query_exercise_groups_for_member = AsyncMock(return_value=Result.ok([]))
    # Curriculum default-group fallback (care arc): empty intersection triggers
    # this second lookup; default = no default group, so behavior is unchanged.
    backend.query_default_groups_for_curriculum_submission = AsyncMock(
        return_value=Result.ok([])
    )
    backend.query_user_can_use_exercise = AsyncMock(return_value=Result.ok(True))
    # Default: referenced predecessor entry is owned by the canonical test user
    # (user_1), so validate_references' TRANSFORMS ownership check passes.
    backend.query_entity_owner = AsyncMock(return_value=Result.ok("user_1"))
    svc.backend = backend
    return svc


def _make_interaction_service() -> MagicMock:
    svc = MagicMock()
    svc.create_interaction = AsyncMock(return_value=Result.ok(True))
    return svc


def _make_service(
    backend=None,
    sharing_service=None,
    interaction_service=None,
    user_service=None,
) -> UserEntryService:
    return UserEntryService(
        backend=backend or _make_backend(),
        sharing_service=sharing_service,
        interaction_service=interaction_service,
        user_service=user_service,
    )


def _make_user_service_for_role(role) -> MagicMock:
    """Build a user_service that returns a User with the given role via has_permission."""
    user = MagicMock()
    user.has_permission = role.has_permission
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


class TestValidateAudience:
    """Guardrail: TEACHER_REVIEW must resolve to a real audience (ADR §3)."""

    @pytest.mark.asyncio
    async def test_teacher_review_with_no_audience_and_no_exercise_fails(self):
        service = _make_service()
        request = UserEntryCreateRequest(
            title="Naked turn-in",
            pipeline=Pipeline.TEACHER_REVIEW,
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_error
        err = result.expect_error()
        assert "audience" in str(err).lower()

    @pytest.mark.asyncio
    async def test_teacher_review_with_exercise_uid_passes(self):
        service = _make_service(sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="Exercise turn-in",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_foo",
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_teacher_review_with_explicit_groups_passes(self):
        service = _make_service(sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="Group turn-in",
            pipeline=Pipeline.TEACHER_REVIEW,
            share_with_groups=["group_1"],
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_pipeline_none_with_no_audience_passes(self):
        """Plain NONE submissions don't need an audience — default PRIVATE."""
        service = _make_service(sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(title="Private note", pipeline=Pipeline.NONE)
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_ok


class TestJournalSharingPolicy:
    """ADR-054 §5: TRANSCRIBE_AND_STRUCTURE is PRIVATE by policy."""

    @pytest.mark.asyncio
    async def test_journal_with_no_audience_passes(self):
        service = _make_service(sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="Morning reflection",
            pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE,
            file_path="/tmp/x.mp3",
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_journal_with_share_with_groups_rejected(self):
        service = _make_service(sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="Reflection",
            pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE,
            share_with_groups=["g1"],
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_error
        assert "private" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_journal_with_share_with_users_rejected(self):
        service = _make_service(sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="Reflection",
            pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE,
            share_with_users=["user_peer"],
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_error

    @pytest.mark.asyncio
    async def test_journal_with_public_visibility_rejected(self):
        service = _make_service(sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="Reflection",
            pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE,
            visibility=Visibility.PUBLIC,
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_error

    @pytest.mark.asyncio
    async def test_journal_with_auto_share_flag_rejected(self):
        service = _make_service(sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="Reflection",
            pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE,
            auto_share_to_exercise_groups=True,
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_error

    def test_pipeline_allows_sharing_matrix(self):
        """The policy: only TRANSCRIBE_AND_STRUCTURE is private."""
        assert Pipeline.NONE.allows_sharing()
        assert Pipeline.TRANSCRIBE.allows_sharing()
        assert Pipeline.LLM_SUMMARY.allows_sharing()
        assert Pipeline.TEACHER_REVIEW.allows_sharing()
        assert not Pipeline.TRANSCRIBE_AND_STRUCTURE.allows_sharing()


class TestCreateEntryRouting:
    """Service routes create calls based on exercise link presence."""

    @pytest.mark.asyncio
    async def test_no_exercise_uses_plain_create(self):
        backend = _make_backend()
        service = _make_service(backend=backend)
        request = UserEntryCreateRequest(title="Note", pipeline=Pipeline.NONE)
        await service.create_entry(request, user_uid="user_1")
        backend.create.assert_awaited_once()
        backend.create_with_exercise_link.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_exercise_uses_linked_create(self):
        backend = _make_backend()
        service = _make_service(backend=backend, sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="Turn-in",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_1",
        )
        await service.create_entry(request, user_uid="user_1")
        backend.create_with_exercise_link.assert_awaited_once()
        backend.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_unauthorized_exercise_reference_is_rejected(self):
        """create_entry must reject an exercise the caller can't use.

        Security regression: without validate_references a caller could attach an
        entry to another user's exercise (cross-tenant leak via auto-share). The
        entry must NOT be persisted when access is denied.
        """
        backend = _make_backend()
        sharing = _make_sharing_service()
        sharing.backend.query_user_can_use_exercise = AsyncMock(return_value=Result.ok(False))
        service = _make_service(backend=backend, sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Turn-in for someone else's exercise",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_not_mine",
        )
        result = await service.create_entry(request, user_uid="user_attacker")
        assert result.is_error
        backend.create_with_exercise_link.assert_not_called()
        backend.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_revision_number_comes_from_count_plus_one(self):
        backend = _make_backend()
        backend.count_entries_for_exercise = AsyncMock(return_value=Result.ok(2))
        service = _make_service(backend=backend, sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="Retry",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_1",
        )
        await service.create_entry(request, user_uid="user_1")
        kwargs = backend.create_with_exercise_link.await_args.kwargs
        assert kwargs["revision"] == 3


class TestTransformsEdge:
    """transforms_of_uid creates a TRANSFORMS edge on the new entry."""

    @pytest.mark.asyncio
    async def test_transforms_wiring(self):
        backend = _make_backend()
        service = _make_service(backend=backend, sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="Structured output",
            pipeline=Pipeline.NONE,
            transforms_of_uid="ue_source_1",
        )
        await service.create_entry(request, user_uid="user_1")
        backend.add_relationship.assert_awaited_once()
        kwargs = backend.add_relationship.await_args.kwargs
        assert kwargs["to_uid"] == "ue_source_1"

    @pytest.mark.asyncio
    async def test_no_transforms_when_uid_absent(self):
        backend = _make_backend()
        service = _make_service(backend=backend)
        request = UserEntryCreateRequest(title="Plain", pipeline=Pipeline.NONE)
        await service.create_entry(request, user_uid="user_1")
        backend.add_relationship.assert_not_called()


class TestInteractionAutoCreate:
    """Interaction audit record fires when exercise + interaction_service present."""

    @pytest.mark.asyncio
    async def test_interaction_created_for_exercise_linked_entry(self):
        interaction_svc = _make_interaction_service()
        service = _make_service(
            sharing_service=_make_sharing_service(),
            interaction_service=interaction_svc,
        )
        request = UserEntryCreateRequest(
            title="Turn-in",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_1",
        )
        await service.create_entry(request, user_uid="user_1")
        interaction_svc.create_interaction.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_interaction_without_exercise(self):
        interaction_svc = _make_interaction_service()
        service = _make_service(
            sharing_service=_make_sharing_service(),
            interaction_service=interaction_svc,
        )
        request = UserEntryCreateRequest(title="Note", pipeline=Pipeline.NONE)
        await service.create_entry(request, user_uid="user_1")
        interaction_svc.create_interaction.assert_not_called()


class TestAudienceResolution:
    """Audience resolution — explicit groups, users, auto-share fallback."""

    @pytest.mark.asyncio
    async def test_explicit_groups_shared_via_group(self):
        sharing = _make_sharing_service()
        service = _make_service(sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Share",
            pipeline=Pipeline.NONE,
            share_with_groups=["g1", "g2"],
        )
        await service.create_entry(request, user_uid="user_1")
        assert sharing.share_with_group.await_count == 2

    @pytest.mark.asyncio
    async def test_explicit_users_shared_directly(self):
        sharing = _make_sharing_service()
        service = _make_service(sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Share",
            pipeline=Pipeline.NONE,
            share_with_users=["user_peer"],
        )
        await service.create_entry(request, user_uid="user_1")
        sharing.share.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_teacher_review_auto_shares_to_exercise_groups(self):
        """TEACHER_REVIEW + exercise + no explicit audience → auto-share
        scoped to the intersection of exercise groups and uploader membership."""
        sharing = _make_sharing_service()
        sharing.backend.query_exercise_groups_for_member = AsyncMock(
            return_value=Result.ok([{"group_uid": "teacher_group_1"}])
        )
        service = _make_service(sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Auto turn-in",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_1",
        )
        await service.create_entry(request, user_uid="user_1")
        sharing.backend.query_exercise_groups_for_member.assert_awaited_once_with(
            exercise_uid="ex_1", user_uid="user_1"
        )
        sharing.share_with_group.assert_awaited_once()
        kwargs = sharing.share_with_group.await_args.kwargs
        assert kwargs["group_uid"] == "teacher_group_1"

    @pytest.mark.asyncio
    async def test_explicit_audience_skips_auto_share(self):
        """When caller provides share_with_groups, auto-share is bypassed."""
        sharing = _make_sharing_service()
        service = _make_service(sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Turn-in",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_1",
            share_with_groups=["explicit_group"],
        )
        await service.create_entry(request, user_uid="user_1")
        sharing.backend.query_exercise_groups_for_member.assert_not_called()
        sharing.share_with_group.assert_awaited_once()


class TestPublicVisibilityGate:
    """``visibility=PUBLIC`` must be TEACHER-gated at the service layer so
    every caller (YAML upload, form API, programmatic) hits the same check."""

    @pytest.mark.asyncio
    async def test_public_rejected_for_registered_user(self):
        from core.models.enums.user_enums import UserRole

        user_service = _make_user_service_for_role(UserRole.REGISTERED)
        service = _make_service(
            sharing_service=_make_sharing_service(),
            user_service=user_service,
        )
        request = UserEntryCreateRequest(
            title="Brag post",
            pipeline=Pipeline.NONE,
            visibility=Visibility.PUBLIC,
        )
        result = await service.create_entry(request, user_uid="user_registered")
        assert result.is_error
        err = result.expect_error()
        assert err.category.value == "forbidden"
        assert "teacher" in str(err).lower()

    @pytest.mark.asyncio
    async def test_public_accepted_for_teacher(self):
        from core.models.enums.user_enums import UserRole

        user_service = _make_user_service_for_role(UserRole.TEACHER)
        service = _make_service(
            sharing_service=_make_sharing_service(),
            user_service=user_service,
        )
        request = UserEntryCreateRequest(
            title="Published exemplar",
            pipeline=Pipeline.NONE,
            visibility=Visibility.PUBLIC,
        )
        result = await service.create_entry(request, user_uid="user_teacher")
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_public_fail_closed_without_user_service(self):
        service = _make_service(
            sharing_service=_make_sharing_service(),
            user_service=None,
        )
        request = UserEntryCreateRequest(
            title="Anything",
            pipeline=Pipeline.NONE,
            visibility=Visibility.PUBLIC,
        )
        result = await service.create_entry(request, user_uid="user_unknown")
        assert result.is_error
        assert "teacher" in str(result.expect_error()).lower()


class TestEntryStatus:
    """Status derives from pipeline at create time."""

    @pytest.mark.asyncio
    async def test_teacher_review_creates_submitted(self):
        backend = _make_backend()
        service = _make_service(backend=backend, sharing_service=_make_sharing_service())
        request = UserEntryCreateRequest(
            title="T",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_1",
        )
        await service.create_entry(request, user_uid="user_1")
        entry_passed = backend.create_with_exercise_link.await_args.kwargs["entry"]
        assert entry_passed.status == EntityStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_pipeline_none_creates_active(self):
        backend = _make_backend()
        service = _make_service(backend=backend)
        request = UserEntryCreateRequest(title="T", pipeline=Pipeline.NONE)
        await service.create_entry(request, user_uid="user_1")
        entry_passed = backend.create.await_args.args[0]
        assert entry_passed.status == EntityStatus.ACTIVE


class TestReadOperations:
    """get_entry ownership verification + list helpers."""

    @pytest.mark.asyncio
    async def test_get_entry_returns_owned_entry(self):
        entry = _make_entry(user_uid="user_1")
        backend = _make_backend(entry=entry)
        service = _make_service(backend=backend)
        result = await service.get_entry("ue_test_1", user_uid="user_1")
        assert result.is_ok
        assert result.value is not None
        assert result.value.uid == "ue_test_1"

    @pytest.mark.asyncio
    async def test_get_entry_returns_none_for_other_owner(self):
        entry = _make_entry(user_uid="user_other")
        backend = _make_backend(entry=entry)
        service = _make_service(backend=backend)
        result = await service.get_entry("ue_test_1", user_uid="user_1")
        assert result.is_ok
        assert result.value is None


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_rejects_empty_request(self):
        entry = _make_entry(user_uid="user_1")
        backend = _make_backend(entry=entry)
        service = _make_service(backend=backend)
        result = await service.update_entry("ue_test_1", "user_1", UserEntryUpdateRequest())
        assert result.is_error

    @pytest.mark.asyncio
    async def test_update_applies_content_fields(self):
        entry = _make_entry(user_uid="user_1")
        backend = _make_backend(entry=entry)
        service = _make_service(backend=backend)
        req = UserEntryUpdateRequest(title="New title", content="New body")
        result = await service.update_entry("ue_test_1", "user_1", req)
        assert result.is_ok
        updates = backend.update.await_args.args[1]
        assert updates["title"] == "New title"
        assert updates["content"] == "New body"


class TestVisibilityDefault:
    @pytest.mark.asyncio
    async def test_default_visibility_is_private(self):
        backend = _make_backend()
        service = _make_service(backend=backend)
        request = UserEntryCreateRequest(title="T", pipeline=Pipeline.NONE)
        await service.create_entry(request, user_uid="user_1")
        entry_passed = backend.create.await_args.args[0]
        assert entry_passed.visibility == Visibility.PRIVATE


class TestShareOutcome:
    """ShareOutcome surfaces share successes/failures and drives compensation.

    ADR-054 §3 requires that a TEACHER_REVIEW submission resolves to a real
    audience. The pre-persist guard rejects naked requests; this layer covers
    the post-persist path: when every requested share fails, the orphaned
    entry must be rolled back, not silently left as PRIVATE.
    """

    @pytest.mark.asyncio
    async def test_success_returns_outcome_with_shared_group(self):
        sharing = _make_sharing_service()
        service = _make_service(sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Share",
            pipeline=Pipeline.NONE,
            share_with_groups=["g1"],
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_ok
        _entry, outcome = result.value
        assert isinstance(outcome, ShareOutcome)
        assert outcome.shared_groups == ("g1",)
        assert outcome.failed == ()

    @pytest.mark.asyncio
    async def test_partial_failure_on_non_teacher_pipeline_is_surfaced_not_fatal(self):
        """NONE pipeline with mixed success/failure returns ok + failed list."""
        sharing = _make_sharing_service()
        sharing.share_with_group = AsyncMock(
            side_effect=[
                Result.ok(True),
                Result.fail(Errors.not_found("Group", "g_missing")),
            ]
        )
        service = _make_service(sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Share",
            pipeline=Pipeline.NONE,
            share_with_groups=["g1", "g_missing"],
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_ok
        _entry, outcome = result.value
        assert outcome.shared_groups == ("g1",)
        assert len(outcome.failed) == 1
        assert outcome.failed[0][0] == "g_missing"

    @pytest.mark.asyncio
    async def test_teacher_review_total_share_failure_compensates(self):
        """TEACHER_REVIEW + every share fails → entry deleted + validation error."""
        backend = _make_backend()
        sharing = _make_sharing_service()
        sharing.share_with_group = AsyncMock(
            return_value=Result.fail(Errors.not_found("Group", "g1"))
        )
        service = _make_service(backend=backend, sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Naked to bad group",
            pipeline=Pipeline.TEACHER_REVIEW,
            share_with_groups=["g1"],
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_error
        err = str(result.expect_error())
        assert "no audience was reached" in err.lower() or "could not be shared" in err.lower()
        # The just-persisted node must have been rolled back
        backend.delete.assert_awaited_once()
        delete_kwargs = backend.delete.await_args.kwargs
        assert delete_kwargs.get("cascade") is True

    @pytest.mark.asyncio
    async def test_teacher_review_partial_success_does_not_compensate(self):
        """At least one recipient landed → keep the entry, surface partial warning."""
        backend = _make_backend()
        sharing = _make_sharing_service()
        sharing.share_with_group = AsyncMock(
            side_effect=[
                Result.ok(True),
                Result.fail(Errors.not_found("Group", "g_missing")),
            ]
        )
        service = _make_service(backend=backend, sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Mixed success",
            pipeline=Pipeline.TEACHER_REVIEW,
            share_with_groups=["g1", "g_missing"],
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_ok
        _entry, outcome = result.value
        backend.delete.assert_not_called()
        assert outcome.shared_groups == ("g1",)
        assert len(outcome.failed) == 1

    @pytest.mark.asyncio
    async def test_teacher_review_auto_share_failure_compensates(self):
        """TEACHER_REVIEW + exercise resolves to zero groups failure → compensate."""
        backend = _make_backend()
        sharing = _make_sharing_service()
        sharing.backend.query_exercise_groups_for_member = AsyncMock(
            return_value=Result.fail(Errors.database(operation="cypher", message="resolve failed"))
        )
        service = _make_service(backend=backend, sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Auto-share crash",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_1",
        )
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_error
        backend.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_outcome_when_no_sharing_service(self):
        """Services without sharing still return a well-formed empty outcome."""
        service = _make_service(sharing_service=None)
        request = UserEntryCreateRequest(title="Solo", pipeline=Pipeline.NONE)
        result = await service.create_entry(request, user_uid="user_1")
        assert result.is_ok
        _entry, outcome = result.value
        assert outcome == ShareOutcome()


class TestDeleteEntryAsTeacher:
    """Tests for ``UserEntryService.delete_entry_as_teacher`` (ADR-054 + ADR-040)."""

    @pytest.mark.asyncio
    async def test_teacher_with_group_access_can_delete(self):
        backend = _make_backend()
        backend.verify_teacher_has_group_access = AsyncMock(
            return_value=Result.ok([{"has_access": True}])
        )
        service = _make_service(backend=backend)
        result = await service.delete_entry_as_teacher("ue_test_1", teacher_uid="teacher_1")
        assert result.is_ok
        backend.verify_teacher_has_group_access.assert_awaited_once_with("ue_test_1", "teacher_1")
        backend.delete.assert_awaited_once_with("ue_test_1", cascade=True)

    @pytest.mark.asyncio
    async def test_teacher_without_group_access_returns_not_found(self):
        """Empty access → 404, not 403 (do not leak entry existence)."""
        backend = _make_backend()
        backend.verify_teacher_has_group_access = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)
        result = await service.delete_entry_as_teacher("ue_test_1", teacher_uid="teacher_1")
        assert result.is_error
        assert result.expect_error().category.value == "not_found"
        backend.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_access_check_database_error_propagates(self):
        backend = _make_backend()
        backend.verify_teacher_has_group_access = AsyncMock(
            return_value=Result.fail(Errors.database(operation="cypher", message="boom"))
        )
        service = _make_service(backend=backend)
        result = await service.delete_entry_as_teacher("ue_test_1", teacher_uid="teacher_1")
        assert result.is_error
        backend.delete.assert_not_called()
