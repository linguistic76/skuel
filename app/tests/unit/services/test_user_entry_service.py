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
from core.services.user_entry.user_entry_service import UserEntryService
from core.utils.result_simplified import Result


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
    return svc


def _make_interaction_service() -> MagicMock:
    svc = MagicMock()
    svc.create_interaction = AsyncMock(return_value=Result.ok(True))
    return svc


def _make_service(backend=None, sharing_service=None, interaction_service=None) -> UserEntryService:
    return UserEntryService(
        backend=backend or _make_backend(),
        sharing_service=sharing_service,
        interaction_service=interaction_service,
    )


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
        service = _make_service(backend=backend)
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
        """TEACHER_REVIEW + exercise + no explicit audience → auto-share."""
        sharing = _make_sharing_service()
        sharing.get_groups_shared_with = AsyncMock(
            return_value=Result.ok([{"group_uid": "teacher_group_1"}])
        )
        service = _make_service(sharing_service=sharing)
        request = UserEntryCreateRequest(
            title="Auto turn-in",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid="ex_1",
        )
        await service.create_entry(request, user_uid="user_1")
        sharing.get_groups_shared_with.assert_awaited_once()
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
        sharing.get_groups_shared_with.assert_not_called()
        sharing.share_with_group.assert_awaited_once()


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
