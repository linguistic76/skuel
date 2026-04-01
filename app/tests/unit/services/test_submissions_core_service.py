"""Tests for SubmissionsCoreService."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.services.submissions.submissions_core_service import (
    ReportCategory,
    SubmissionsCoreService,
)
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(**kwargs):
    """Create a mock entity with sensible defaults."""
    entity = MagicMock()
    entity.uid = kwargs.get("uid", "sub_123")
    entity.title = kwargs.get("title", "Test Submission")
    entity.entity_type = kwargs.get("entity_type", EntityType.EXERCISE_SUBMISSION)
    entity.status = kwargs.get("status", EntityStatus.ACTIVE)
    entity.metadata = kwargs.get("metadata", {})
    entity.content = kwargs.get("content", "test content")
    entity.created_at = kwargs.get("created_at", datetime(2026, 3, 1, tzinfo=UTC))
    entity.user_uid = kwargs.get("user_uid", "user_1")
    entity.max_retention = kwargs.get("max_retention")
    entity.processed_content = kwargs.get("processed_content")
    entity.tags = kwargs.get("tags", ())
    return entity


def _make_backend():
    """Create a mock backend with all common async methods."""
    backend = MagicMock()
    backend.get = AsyncMock()
    backend.create = AsyncMock()
    backend.update = AsyncMock()
    backend.delete = AsyncMock()
    backend.find_by = AsyncMock()
    backend.list = AsyncMock()
    backend.execute_query = AsyncMock()
    return backend


def _make_service(backend=None, event_bus=None, sharing_service=None):
    backend = backend or _make_backend()
    return SubmissionsCoreService(
        backend=backend,
        event_bus=event_bus,
        sharing_service=sharing_service,
    )


# ===========================================================================
# A. Retrieve
# ===========================================================================


class TestGetSubmission:
    """Tests for get_submission."""

    @pytest.mark.asyncio
    async def test_success(self):
        backend = _make_backend()
        entity = _make_entity()
        backend.get = AsyncMock(return_value=Result.ok(entity))
        service = _make_service(backend=backend)

        result = await service.get_submission("sub_123")

        assert result.is_ok
        assert result.value.uid == "sub_123"

    @pytest.mark.asyncio
    async def test_not_found(self):
        backend = _make_backend()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.get_submission("missing")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_backend_error(self):
        backend = _make_backend()
        backend.get = AsyncMock(return_value=Result.fail(Errors.database("get", "DB timeout")))
        service = _make_service(backend=backend)

        result = await service.get_submission("sub_123")

        assert result.is_error


class TestGetWithAccessCheck:
    """Tests for get_with_access_check."""

    @pytest.mark.asyncio
    async def test_access_granted(self):
        backend = _make_backend()
        entity = _make_entity()
        backend.get = AsyncMock(return_value=Result.ok(entity))
        sharing = MagicMock()
        sharing.check_access = AsyncMock(return_value=Result.ok(True))
        service = _make_service(backend=backend, sharing_service=sharing)

        result = await service.get_with_access_check("sub_123", "user_1")

        assert result.is_ok
        sharing.check_access.assert_awaited_once_with("sub_123", "user_1")

    @pytest.mark.asyncio
    async def test_access_denied_returns_not_found(self):
        backend = _make_backend()
        sharing = MagicMock()
        sharing.check_access = AsyncMock(return_value=Result.ok(False))
        service = _make_service(backend=backend, sharing_service=sharing)

        result = await service.get_with_access_check("sub_123", "user_1")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_sharing_error_propagated(self):
        backend = _make_backend()
        sharing = MagicMock()
        sharing.check_access = AsyncMock(return_value=Result.fail(Errors.system("sharing down")))
        service = _make_service(backend=backend, sharing_service=sharing)

        result = await service.get_with_access_check("sub_123", "user_1")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_no_sharing_service_fallback(self):
        backend = _make_backend()
        entity = _make_entity()
        backend.get = AsyncMock(return_value=Result.ok(entity))
        service = _make_service(backend=backend, sharing_service=None)

        result = await service.get_with_access_check("sub_123", "user_1")

        assert result.is_ok
        assert result.value.uid == "sub_123"

    @pytest.mark.asyncio
    async def test_owner_can_access(self):
        backend = _make_backend()
        entity = _make_entity(user_uid="user_1")
        backend.get = AsyncMock(return_value=Result.ok(entity))
        sharing = MagicMock()
        sharing.check_access = AsyncMock(return_value=Result.ok(True))
        service = _make_service(backend=backend, sharing_service=sharing)

        result = await service.get_with_access_check("sub_123", "user_1")

        assert result.is_ok
        assert result.value.user_uid == "user_1"


class TestGetRecentSubmissions:
    """Tests for get_recent_submissions."""

    @pytest.mark.asyncio
    async def test_with_user_filter(self):
        backend = _make_backend()
        entities = [_make_entity(uid=f"s_{i}") for i in range(3)]
        backend.find_by = AsyncMock(return_value=Result.ok(entities))
        service = _make_service(backend=backend)

        result = await service.get_recent_submissions(limit=10, user_uid="user_1")

        assert result.is_ok
        assert len(result.value) == 3
        backend.find_by.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_type_filter(self):
        backend = _make_backend()
        entities = [_make_entity()]
        backend.find_by = AsyncMock(return_value=Result.ok(entities))
        service = _make_service(backend=backend)

        result = await service.get_recent_submissions(
            limit=5, entity_type=EntityType.EXERCISE_SUBMISSION
        )

        assert result.is_ok
        call_kwargs = backend.find_by.call_args.kwargs
        assert call_kwargs["entity_type"] == EntityType.EXERCISE_SUBMISSION.value

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        backend = _make_backend()
        entities = [
            _make_entity(uid=f"s_{i}", created_at=datetime(2026, 3, i + 1, tzinfo=UTC))
            for i in range(10)
        ]
        backend.find_by = AsyncMock(return_value=Result.ok(entities))
        service = _make_service(backend=backend)

        result = await service.get_recent_submissions(limit=3, user_uid="user_1")

        assert result.is_ok
        assert len(result.value) <= 3

    @pytest.mark.asyncio
    async def test_backend_error(self):
        backend = _make_backend()
        backend.find_by = AsyncMock(return_value=Result.fail(Errors.database("find", "err")))
        service = _make_service(backend=backend)

        result = await service.get_recent_submissions(user_uid="user_1")

        assert result.is_error


class TestGetSubmissionForDate:
    """Tests for get_submission_for_date."""

    @pytest.mark.asyncio
    async def test_found(self):
        backend = _make_backend()
        entity = _make_entity(created_at=datetime(2026, 3, 5, 10, 30, tzinfo=UTC))
        backend.find_by = AsyncMock(return_value=Result.ok([entity]))
        service = _make_service(backend=backend)

        result = await service.get_submission_for_date(date(2026, 3, 5))

        assert result.is_ok
        assert result.value is not None
        assert result.value.uid == "sub_123"

    @pytest.mark.asyncio
    async def test_not_found(self):
        backend = _make_backend()
        entity = _make_entity(created_at=datetime(2026, 3, 5, tzinfo=UTC))
        backend.find_by = AsyncMock(return_value=Result.ok([entity]))
        service = _make_service(backend=backend)

        result = await service.get_submission_for_date(date(2026, 4, 1))

        assert result.is_ok
        assert result.value is None

    @pytest.mark.asyncio
    async def test_backend_error(self):
        backend = _make_backend()
        backend.find_by = AsyncMock(return_value=Result.fail(Errors.database("find", "err")))
        service = _make_service(backend=backend)

        result = await service.get_submission_for_date(date(2026, 3, 5))

        assert result.is_error


# ===========================================================================
# B. Update / Status
# ===========================================================================


class TestUpdateSubmission:
    """Tests for update_submission."""

    @pytest.mark.asyncio
    async def test_success(self):
        backend = _make_backend()
        updated = _make_entity(title="Updated")
        backend.update = AsyncMock(return_value=Result.ok(updated))
        service = _make_service(backend=backend)

        result = await service.update_submission("sub_123", {"title": "Updated"})

        assert result.is_ok
        assert result.value.title == "Updated"

    @pytest.mark.asyncio
    async def test_disallowed_fields_filtered(self):
        backend = _make_backend()
        updated = _make_entity()
        backend.update = AsyncMock(return_value=Result.ok(updated))
        service = _make_service(backend=backend)

        await service.update_submission(
            "sub_123", {"title": "OK", "uid": "hacked", "user_uid": "evil"}
        )

        call_args = backend.update.call_args
        update_dict = call_args.args[1]
        assert "uid" not in update_dict
        assert "user_uid" not in update_dict
        assert "title" in update_dict

    @pytest.mark.asyncio
    async def test_metadata_passed_as_dict(self):
        """Backend.update() now auto-serializes complex types for Neo4j."""
        backend = _make_backend()
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        await service.update_submission("sub_123", {"metadata": {"key": "val"}})

        call_args = backend.update.call_args
        update_dict = call_args.args[1]
        assert isinstance(update_dict["metadata"], dict)
        assert update_dict["metadata"]["key"] == "val"

    @pytest.mark.asyncio
    async def test_not_found(self):
        backend = _make_backend()
        backend.update = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.update_submission("missing", {"title": "T"})

        assert result.is_error


class TestPublishSubmission:
    """Tests for publish_submission."""

    @pytest.mark.asyncio
    async def test_sets_completed_status(self):
        backend = _make_backend()
        published = _make_entity(status=EntityStatus.COMPLETED)
        backend.update = AsyncMock(return_value=Result.ok(published))
        service = _make_service(backend=backend)

        result = await service.publish_submission("sub_123")

        assert result.is_ok
        call_args = backend.update.call_args
        assert call_args.args[1]["status"] == EntityStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_not_found(self):
        backend = _make_backend()
        backend.update = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.publish_submission("missing")

        assert result.is_error


class TestArchiveSubmission:
    """Tests for archive_submission."""

    @pytest.mark.asyncio
    async def test_success(self):
        backend = _make_backend()
        entity = _make_entity(metadata={})
        backend.get = AsyncMock(return_value=Result.ok(entity))
        archived = _make_entity(metadata={"archived": True})
        backend.update = AsyncMock(return_value=Result.ok(archived))
        service = _make_service(backend=backend)

        result = await service.archive_submission("sub_123")

        assert result.is_ok

    @pytest.mark.asyncio
    async def test_not_found(self):
        backend = _make_backend()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.archive_submission("missing")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_preserves_existing_metadata(self):
        backend = _make_backend()
        entity = _make_entity(metadata={"category": "daily", "extra": "keep"})
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        await service.archive_submission("sub_123")

        call_args = backend.update.call_args
        update_dict = call_args.args[1]
        # metadata should be JSON-serialized and contain both old and new keys
        meta = update_dict["metadata"]
        assert meta["archived"] is True
        assert meta["category"] == "daily"
        assert meta["extra"] == "keep"
        assert "archived_at" in meta


class TestMarkAsDraft:
    """Tests for mark_as_draft."""

    @pytest.mark.asyncio
    async def test_sets_draft_status(self):
        backend = _make_backend()
        draft = _make_entity(status=EntityStatus.DRAFT)
        backend.update = AsyncMock(return_value=Result.ok(draft))
        service = _make_service(backend=backend)

        result = await service.mark_as_draft("sub_123")

        assert result.is_ok
        call_args = backend.update.call_args
        assert call_args.args[1]["status"] == EntityStatus.DRAFT.value

    @pytest.mark.asyncio
    async def test_not_found(self):
        backend = _make_backend()
        backend.update = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.mark_as_draft("missing")

        assert result.is_error


# ===========================================================================
# C. Exercise Linking
# ===========================================================================


class TestProcessExerciseSubmission:
    """Tests for process_exercise_submission."""

    @pytest.mark.asyncio
    async def test_standard_linking_and_auto_share(self):
        backend = _make_backend()
        backend.get_exercise_context = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "exercise_entity_type": "exercise",
                        "scope": "assigned",
                        "teacher_uid": "teacher_1",
                        "student_uid": None,
                        "exercise_title": "Write Essay",
                        "group_uid": "grp_1",
                    }
                ]
            )
        )
        backend.verify_student_group_membership = AsyncMock(
            return_value=Result.ok([{"student_uid": "user_1", "member_of_group": "grp_1"}])
        )
        backend.get_submission_owner = AsyncMock(
            return_value=Result.ok([{"student_uid": "user_1"}])
        )
        backend.count_submissions_for_exercise = AsyncMock(return_value=Result.ok(0))
        backend.update = AsyncMock(return_value=Result.ok(True))
        backend.link_to_exercise = AsyncMock(return_value=Result.ok([{"success": True}]))
        backend.auto_share_with_teacher = AsyncMock(return_value=Result.ok([{"success": True}]))
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is True

    @pytest.mark.asyncio
    async def test_not_assigned_scope_returns_false(self):
        backend = _make_backend()
        backend.get_exercise_context = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "exercise_entity_type": "exercise",
                        "scope": "shared",
                        "teacher_uid": "teacher_1",
                        "student_uid": None,
                        "exercise_title": "Shared Ex",
                        "group_uid": None,
                    }
                ]
            )
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_exercise_not_found(self):
        backend = _make_backend()
        backend.get_exercise_context = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_missing")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_query_failure_returns_false(self):
        backend = _make_backend()
        backend.get_exercise_context = AsyncMock(
            return_value=Result.fail(Errors.database("query", "timeout"))
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_revised_exercise_path(self):
        backend = _make_backend()
        backend.get_exercise_context = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "exercise_entity_type": "revised_exercise",
                        "scope": None,
                        "teacher_uid": "teacher_1",
                        "student_uid": "user_1",
                        "exercise_title": "Revision",
                        "group_uid": None,
                    }
                ]
            )
        )
        backend.get_submission_owner = AsyncMock(
            return_value=Result.ok([{"student_uid": "user_1"}])
        )
        backend.count_submissions_for_exercise = AsyncMock(return_value=Result.ok(0))
        backend.update = AsyncMock(return_value=Result.ok(True))
        backend.link_to_exercise = AsyncMock(return_value=Result.ok([{"success": True}]))
        backend.auto_share_with_teacher = AsyncMock(return_value=Result.ok([{"success": True}]))
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "re_1")

        assert result.is_ok
        assert result.value is True

    @pytest.mark.asyncio
    async def test_wrong_student_for_revised_exercise(self):
        backend = _make_backend()
        backend.get_exercise_context = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "exercise_entity_type": "revised_exercise",
                        "scope": None,
                        "teacher_uid": "teacher_1",
                        "student_uid": "user_2",
                        "exercise_title": "Revision",
                        "group_uid": None,
                    }
                ]
            )
        )
        # Submitter is user_1, but exercise targets user_2
        backend.get_submission_owner = AsyncMock(
            return_value=Result.ok([{"student_uid": "user_1"}])
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "re_1")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_not_in_group(self):
        backend = _make_backend()
        backend.get_exercise_context = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "exercise_entity_type": "exercise",
                        "scope": "assigned",
                        "teacher_uid": "teacher_1",
                        "student_uid": None,
                        "exercise_title": "Essay",
                        "group_uid": "grp_1",
                    }
                ]
            )
        )
        # Student not in group
        backend.verify_student_group_membership = AsyncMock(
            return_value=Result.ok([{"student_uid": "user_1", "member_of_group": None}])
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_auto_title_generated(self):
        """When exercise has a title, submission gets an auto-generated title."""
        backend = _make_backend()
        backend.get_exercise_context = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "exercise_entity_type": "exercise",
                        "scope": "assigned",
                        "teacher_uid": "teacher_1",
                        "student_uid": None,
                        "exercise_title": "Write Essay",
                        "group_uid": None,
                    }
                ]
            )
        )
        backend.get_submission_owner = AsyncMock(
            return_value=Result.ok([{"student_uid": "user_1"}])
        )
        backend.count_submissions_for_exercise = AsyncMock(return_value=Result.ok(0))
        backend.update = AsyncMock(return_value=Result.ok(True))
        backend.link_to_exercise = AsyncMock(return_value=Result.ok([{"success": True}]))
        backend.auto_share_with_teacher = AsyncMock(return_value=Result.ok([{"success": True}]))
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is True
        # Title update should have been called
        backend.update.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_title_when_exercise_title_empty(self):
        """When exercise has no title, no title update is attempted."""
        backend = _make_backend()
        backend.get_exercise_context = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "exercise_entity_type": "exercise",
                        "scope": "assigned",
                        "teacher_uid": "teacher_1",
                        "student_uid": None,
                        "exercise_title": "",
                        "group_uid": None,
                    }
                ]
            )
        )
        backend.link_to_exercise = AsyncMock(return_value=Result.ok([{"success": True}]))
        backend.auto_share_with_teacher = AsyncMock(return_value=Result.ok([{"success": True}]))
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is True

    @pytest.mark.asyncio
    async def test_no_teacher_uid_skips_auto_share(self):
        """Exercise with no OWNS relationship (e.g. YAML-ingested) skips auto-share gracefully."""
        backend = _make_backend()
        backend.get_exercise_context = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "exercise_entity_type": "exercise",
                        "scope": "assigned",
                        "teacher_uid": None,  # no OWNS relationship → COALESCE returns None
                        "student_uid": None,
                        "exercise_title": "Group Exercise",
                        "group_uid": "grp_1",
                    }
                ]
            )
        )
        backend.verify_student_group_membership = AsyncMock(
            return_value=Result.ok([{"student_uid": "user_1", "member_of_group": "grp_1"}])
        )
        backend.get_submission_owner = AsyncMock(
            return_value=Result.ok([{"student_uid": "user_1"}])
        )
        backend.count_submissions_for_exercise = AsyncMock(return_value=Result.ok(0))
        backend.update = AsyncMock(return_value=Result.ok(True))
        backend.link_to_exercise = AsyncMock(return_value=Result.ok([{"success": True}]))
        backend.auto_share_with_teacher = AsyncMock(return_value=Result.ok([{"success": True}]))
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is True
        backend.auto_share_with_teacher.assert_not_called()


# ===========================================================================
# D. Content Management
# ===========================================================================


class TestCategorizeSubmission:
    """Tests for categorize_submission."""

    @pytest.mark.asyncio
    async def test_success(self):
        backend = _make_backend()
        entity = _make_entity(metadata={})
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        result = await service.categorize_submission("sub_123", ReportCategory.DAILY)

        assert result.is_ok

    @pytest.mark.asyncio
    async def test_unknown_category_still_succeeds(self):
        """Unknown categories log a warning but proceed."""
        backend = _make_backend()
        entity = _make_entity(metadata={})
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        result = await service.categorize_submission("sub_123", "totally_made_up")

        assert result.is_ok

    @pytest.mark.asyncio
    async def test_not_found(self):
        backend = _make_backend()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.categorize_submission("missing", "daily")

        assert result.is_error


class TestAddRemoveTags:
    """Tests for add_tags and remove_tags."""

    @pytest.mark.asyncio
    async def test_add_success(self):
        backend = _make_backend()
        entity = _make_entity(metadata={"tags": ["existing"]})
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        result = await service.add_tags("sub_123", ["new_tag"])

        assert result.is_ok
        call_args = backend.update.call_args
        update_dict = call_args.args[1]
        meta = update_dict["metadata"]
        assert "existing" in meta["tags"]
        assert "new_tag" in meta["tags"]

    @pytest.mark.asyncio
    async def test_add_deduplicates(self):
        backend = _make_backend()
        entity = _make_entity(metadata={"tags": ["alpha"]})
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        result = await service.add_tags("sub_123", ["alpha", "beta"])

        assert result.is_ok
        call_args = backend.update.call_args
        update_dict = call_args.args[1]
        meta = update_dict["metadata"]
        # alpha should appear only once
        assert meta["tags"].count("alpha") == 1
        assert "beta" in meta["tags"]

    @pytest.mark.asyncio
    async def test_remove_success(self):
        backend = _make_backend()
        entity = _make_entity(metadata={"tags": ["keep", "remove_me"]})
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        result = await service.remove_tags("sub_123", ["remove_me"])

        assert result.is_ok
        call_args = backend.update.call_args
        update_dict = call_args.args[1]
        meta = update_dict["metadata"]
        assert "keep" in meta["tags"]
        assert "remove_me" not in meta["tags"]

    @pytest.mark.asyncio
    async def test_add_not_found(self):
        backend = _make_backend()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.add_tags("missing", ["tag"])

        assert result.is_error

    @pytest.mark.asyncio
    async def test_remove_not_found(self):
        backend = _make_backend()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.remove_tags("missing", ["tag"])

        assert result.is_error


class TestBulkOperations:
    """Tests for bulk_categorize, bulk_tag, bulk_delete."""

    @pytest.mark.asyncio
    async def test_bulk_categorize(self):
        backend = _make_backend()
        entity = _make_entity(metadata={})
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        result = await service.bulk_categorize(["s1", "s2", "s3"], "daily")

        assert result.is_ok
        assert result.value == 3

    @pytest.mark.asyncio
    async def test_bulk_tag(self):
        backend = _make_backend()
        entity = _make_entity(metadata={"tags": []})
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        result = await service.bulk_tag(["s1", "s2"], ["important"])

        assert result.is_ok
        assert result.value == 2

    @pytest.mark.asyncio
    async def test_bulk_soft_delete(self):
        backend = _make_backend()
        entity = _make_entity(metadata={})
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        result = await service.bulk_delete(["s1", "s2"], soft_delete=True)

        assert result.is_ok
        assert result.value == 2

    @pytest.mark.asyncio
    async def test_bulk_hard_delete(self):
        backend = _make_backend()
        entity = _make_entity(user_uid="user_1")
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.delete = AsyncMock(return_value=Result.ok(True))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        result = await service.bulk_delete(["s1", "s2"], soft_delete=False)

        assert result.is_ok
        assert result.value == 2

    @pytest.mark.asyncio
    async def test_bulk_categorize_partial_failure(self):
        backend = _make_backend()
        good_entity = _make_entity(metadata={})
        backend.get = AsyncMock(
            side_effect=[
                Result.ok(good_entity),
                Result.ok(None),  # not found
                Result.ok(good_entity),
            ]
        )
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        result = await service.bulk_categorize(["s1", "s2", "s3"], "daily")

        assert result.is_ok
        assert result.value == 2  # 1 failed

    @pytest.mark.asyncio
    async def test_bulk_tag_partial_failure(self):
        backend = _make_backend()
        good_entity = _make_entity(metadata={"tags": []})
        backend.get = AsyncMock(
            side_effect=[
                Result.ok(good_entity),
                Result.ok(None),  # not found
            ]
        )
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        result = await service.bulk_tag(["s1", "s2"], ["tag"])

        assert result.is_ok
        assert result.value == 1


# ===========================================================================
# E. Delete + Export
# ===========================================================================


class TestDeleteSubmission:
    """Tests for delete_submission."""

    @pytest.mark.asyncio
    async def test_publishes_event(self):
        backend = _make_backend()
        entity = _make_entity(user_uid="user_1")
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.delete = AsyncMock(return_value=Result.ok(True))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        result = await service.delete_submission("sub_123")

        assert result.is_ok
        assert result.value is True
        event_bus.publish_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self):
        backend = _make_backend()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.delete_submission("missing")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_backend_delete_failure(self):
        backend = _make_backend()
        entity = _make_entity()
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.delete = AsyncMock(
            return_value=Result.fail(Errors.database("delete", "constraint"))
        )
        service = _make_service(backend=backend)

        result = await service.delete_submission("sub_123")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_delete_returns_false_is_system_error(self):
        backend = _make_backend()
        entity = _make_entity()
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.delete = AsyncMock(return_value=Result.ok(False))
        service = _make_service(backend=backend)

        result = await service.delete_submission("sub_123")

        assert result.is_error


class TestExportToMarkdown:
    """Tests for export_to_markdown."""

    @pytest.mark.asyncio
    async def test_success(self):
        backend = _make_backend()
        entity = _make_entity(
            title="My Submission",
            content="Body text here",
            entity_type=EntityType.EXERCISE_SUBMISSION,
            status=EntityStatus.COMPLETED,
            metadata={"category": "daily", "tags": ["focus", "morning"]},
            created_at=datetime(2026, 3, 15, tzinfo=UTC),
        )
        backend.get = AsyncMock(return_value=Result.ok(entity))
        service = _make_service(backend=backend)

        result = await service.export_to_markdown("sub_123")

        assert result.is_ok
        md = result.value
        assert "# My Submission" in md
        assert "2026-03-15" in md
        assert "exercise_submission" in md
        assert "daily" in md
        assert "focus" in md

    @pytest.mark.asyncio
    async def test_not_found(self):
        backend = _make_backend()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.export_to_markdown("missing")

        assert result.is_error


# ===========================================================================
# F. Additional Coverage
# ===========================================================================


class TestGetRecentSubmissionsNoFilters:
    """Tests for get_recent_submissions when no filters provided (list path)."""

    @pytest.mark.asyncio
    async def test_no_filters_uses_list(self):
        backend = _make_backend()
        entities = [
            _make_entity(uid=f"s_{i}", created_at=datetime(2026, 3, i + 1, tzinfo=UTC))
            for i in range(5)
        ]
        backend.list = AsyncMock(return_value=Result.ok((entities, len(entities))))
        service = _make_service(backend=backend)

        result = await service.get_recent_submissions(limit=3)

        assert result.is_ok
        assert len(result.value) <= 3
        backend.list.assert_awaited_once()
        backend.find_by.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_filters_list_error_returns_empty(self):
        backend = _make_backend()
        backend.list = AsyncMock(return_value=Result.fail(Errors.database("list", "err")))
        service = _make_service(backend=backend)

        result = await service.get_recent_submissions(limit=5)

        assert result.is_ok
        assert result.value == []


class TestGetPublicSubmissions:
    """Tests for get_public_submissions."""

    @pytest.mark.asyncio
    async def test_returns_public_submissions(self):
        backend = _make_backend()
        entities = [_make_entity(uid="pub_1"), _make_entity(uid="pub_2")]
        backend.find_by = AsyncMock(return_value=Result.ok(entities))
        service = _make_service(backend=backend)

        result = await service.get_public_submissions(limit=10)

        assert result.is_ok
        assert len(result.value) == 2

    @pytest.mark.asyncio
    async def test_with_user_filter(self):
        backend = _make_backend()
        backend.find_by = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.get_public_submissions(limit=10, user_uid="user_1")

        assert result.is_ok
        call_kwargs = backend.find_by.call_args.kwargs
        assert call_kwargs["user_uid"] == "user_1"

    @pytest.mark.asyncio
    async def test_error(self):
        backend = _make_backend()
        backend.find_by = AsyncMock(return_value=Result.fail(Errors.database("find", "err")))
        service = _make_service(backend=backend)

        result = await service.get_public_submissions()

        assert result.is_error


class TestValidateSubmissionExists:
    """Tests for _validate_submission_exists helper."""

    @pytest.mark.asyncio
    async def test_returns_ok_when_exists(self):
        service = _make_service()
        entity = _make_entity()

        result = service._validate_submission_exists(entity)

        assert result.is_ok
        assert result.value.uid == "sub_123"

    @pytest.mark.asyncio
    async def test_returns_error_when_none(self):
        service = _make_service()

        result = service._validate_submission_exists(None)

        assert result.is_error


class TestGetSubmissionForDateEdgeCases:
    """Additional edge cases for get_submission_for_date."""

    @pytest.mark.asyncio
    async def test_user_uid_passed_as_filter(self):
        backend = _make_backend()
        backend.find_by = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        await service.get_submission_for_date(date(2026, 3, 1), user_uid="user_1")

        call_kwargs = backend.find_by.call_args.kwargs
        assert call_kwargs["user_uid"] == "user_1"
