"""Tests for SubmissionsCoreService."""

import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

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
    entity.max_retention = kwargs.get("max_retention", None)
    entity.processed_content = kwargs.get("processed_content", None)
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
# A. Journal CRUD
# ===========================================================================


class TestCreateJournalEntry:
    """Tests for create_journal_entry."""

    @pytest.mark.asyncio
    async def test_minimal_creation(self):
        backend = _make_backend()
        backend.create = AsyncMock(return_value=Result.ok(None))
        backend.execute_query = AsyncMock(return_value=Result.ok([{"total": 0}]))
        backend.find_by = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.create_journal_entry(user_uid="user_1", content="Hello world")

        assert result.is_ok
        journal = result.value
        assert journal.user_uid == "user_1"
        assert journal.content == "Hello world"
        # Journal.__post_init__ forces entity_type to JOURNAL (deprecated alias)
        assert journal.entity_type == EntityType.JOURNAL
        assert journal.status == EntityStatus.DRAFT
        backend.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_generates_title_when_none(self):
        backend = _make_backend()
        backend.create = AsyncMock(return_value=Result.ok(None))
        backend.execute_query = AsyncMock(return_value=Result.ok([{"total": 2}]))
        backend.find_by = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.create_journal_entry(user_uid="user_1")

        assert result.is_ok
        # Title should contain a sequence number based on count (2+1=3)
        assert result.value.title is not None
        assert len(result.value.title) > 0

    @pytest.mark.asyncio
    async def test_uses_custom_title(self):
        backend = _make_backend()
        backend.create = AsyncMock(return_value=Result.ok(None))
        backend.find_by = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.create_journal_entry(
            user_uid="user_1", title="My Custom Title"
        )

        assert result.is_ok
        assert result.value.title == "My Custom Title"

    @pytest.mark.asyncio
    async def test_metadata_fields_populated(self):
        backend = _make_backend()
        backend.create = AsyncMock(return_value=Result.ok(None))
        backend.execute_query = AsyncMock(return_value=Result.ok([{"total": 0}]))
        backend.find_by = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.create_journal_entry(
            user_uid="user_1",
            title="Mood Entry",
            mood="happy",
            energy_level=8,
            key_topics=["fitness"],
            action_items=["run 5k"],
            project_uid="proj_1",
        )

        assert result.is_ok
        meta = result.value.metadata
        assert meta["mood"] == "happy"
        assert meta["energy_level"] == 8
        assert meta["key_topics"] == ["fitness"]
        assert meta["action_items"] == ["run 5k"]
        assert meta["project_uid"] == "proj_1"
        assert "entry_date" in meta

    @pytest.mark.asyncio
    async def test_source_fields_populated(self):
        backend = _make_backend()
        backend.create = AsyncMock(return_value=Result.ok(None))
        backend.execute_query = AsyncMock(return_value=Result.ok([{"total": 0}]))
        backend.find_by = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.create_journal_entry(
            user_uid="user_1",
            title="Audio Journal",
            source_type="audio",
            source_file="recording.m4a",
            transcription_uid="tx_abc",
        )

        assert result.is_ok
        meta = result.value.metadata
        assert meta["source_type"] == "audio"
        assert meta["source_file"] == "recording.m4a"
        assert meta["transcription_uid"] == "tx_abc"

    @pytest.mark.asyncio
    async def test_fifo_enforcement_called_when_max_retention_set(self):
        backend = _make_backend()
        backend.create = AsyncMock(return_value=Result.ok(None))
        backend.execute_query = AsyncMock(return_value=Result.ok([{"total": 0}]))
        # _enforce_fifo calls find_by — return empty so nothing to delete
        backend.find_by = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.create_journal_entry(
            user_uid="user_1", title="Ephemeral", max_retention=3
        )

        assert result.is_ok
        assert result.value.max_retention == 3
        # find_by was called by _enforce_fifo
        backend.find_by.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_fifo_when_permanent(self):
        backend = _make_backend()
        backend.create = AsyncMock(return_value=Result.ok(None))
        backend.execute_query = AsyncMock(return_value=Result.ok([{"total": 0}]))
        service = _make_service(backend=backend)

        result = await service.create_journal_entry(
            user_uid="user_1", title="Permanent", max_retention=None
        )

        assert result.is_ok
        # find_by should NOT be called because _enforce_fifo is skipped
        backend.find_by.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_backend_create_failure(self):
        backend = _make_backend()
        backend.create = AsyncMock(
            return_value=Result.fail(Errors.database(operation="create", message="DB down"))
        )
        backend.execute_query = AsyncMock(return_value=Result.ok([{"total": 0}]))
        service = _make_service(backend=backend)

        result = await service.create_journal_entry(user_uid="user_1", title="Fail")

        assert result.is_error


class TestEnforceFifo:
    """Tests for _enforce_fifo."""

    @pytest.mark.asyncio
    async def test_under_limit_no_deletes(self):
        backend = _make_backend()
        journals = [
            _make_entity(uid=f"j_{i}", max_retention=3) for i in range(2)
        ]
        backend.find_by = AsyncMock(return_value=Result.ok(journals))
        service = _make_service(backend=backend)

        result = await service._enforce_fifo("user_1", max_retention=3)

        assert result.is_ok
        assert result.value == 0
        backend.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_over_limit_deletes_oldest(self):
        backend = _make_backend()
        journals = [
            _make_entity(
                uid=f"j_{i}",
                max_retention=3,
                created_at=datetime(2026, 1, i + 1, tzinfo=UTC),
            )
            for i in range(5)
        ]
        backend.find_by = AsyncMock(return_value=Result.ok(journals))
        backend.delete = AsyncMock(return_value=Result.ok(True))
        service = _make_service(backend=backend)

        result = await service._enforce_fifo("user_1", max_retention=3)

        assert result.is_ok
        assert result.value == 2  # 5 - 3 = 2 deleted
        assert backend.delete.await_count == 2
        # Oldest two (j_0, j_1) should be deleted
        deleted_uids = [call.args[0] for call in backend.delete.await_args_list]
        assert "j_0" in deleted_uids
        assert "j_1" in deleted_uids

    @pytest.mark.asyncio
    async def test_find_failure_returns_zero(self):
        backend = _make_backend()
        backend.find_by = AsyncMock(
            return_value=Result.fail(Errors.database(operation="find", message="err"))
        )
        service = _make_service(backend=backend)

        result = await service._enforce_fifo("user_1", max_retention=3)

        assert result.is_ok
        assert result.value == 0

    @pytest.mark.asyncio
    async def test_partial_delete_failure(self):
        backend = _make_backend()
        journals = [
            _make_entity(
                uid=f"j_{i}",
                max_retention=2,
                created_at=datetime(2026, 1, i + 1, tzinfo=UTC),
            )
            for i in range(4)
        ]
        backend.find_by = AsyncMock(return_value=Result.ok(journals))
        # First delete succeeds, second fails
        backend.delete = AsyncMock(
            side_effect=[Result.ok(True), Result.fail(Errors.database("del", "err"))]
        )
        service = _make_service(backend=backend)

        result = await service._enforce_fifo("user_1", max_retention=2)

        assert result.is_ok
        assert result.value == 1  # Only one succeeded

    @pytest.mark.asyncio
    async def test_filters_only_fifo_journals(self):
        """Only journals with max_retention set should be counted."""
        backend = _make_backend()
        fifo_journals = [
            _make_entity(uid=f"f_{i}", max_retention=2, created_at=datetime(2026, 1, i + 1, tzinfo=UTC))
            for i in range(4)
        ]
        permanent = _make_entity(uid="perm_1", max_retention=None)
        backend.find_by = AsyncMock(return_value=Result.ok(fifo_journals + [permanent]))
        backend.delete = AsyncMock(return_value=Result.ok(True))
        service = _make_service(backend=backend)

        result = await service._enforce_fifo("user_1", max_retention=2)

        assert result.is_ok
        assert result.value == 2
        deleted_uids = [call.args[0] for call in backend.delete.await_args_list]
        assert "perm_1" not in deleted_uids


class TestGetEphemeralJournals:
    """Tests for get_ephemeral_journals."""

    @pytest.mark.asyncio
    async def test_returns_fifo_only(self):
        backend = _make_backend()
        fifo = _make_entity(uid="fifo_1", max_retention=3, metadata={"entry_date": "2026-03-01"})
        perm = _make_entity(uid="perm_1", max_retention=None, metadata={"entry_date": "2026-03-01"})
        backend.find_by = AsyncMock(return_value=Result.ok([fifo, perm]))
        service = _make_service(backend=backend)

        result = await service.get_ephemeral_journals("user_1")

        assert result.is_ok
        uids = [j.uid for j in result.value]
        assert "fifo_1" in uids
        assert "perm_1" not in uids

    @pytest.mark.asyncio
    async def test_sorted_by_entry_date(self):
        backend = _make_backend()
        j1 = _make_entity(uid="j1", max_retention=5, metadata={"entry_date": "2026-01-01"})
        j2 = _make_entity(uid="j2", max_retention=5, metadata={"entry_date": "2026-03-01"})
        backend.find_by = AsyncMock(return_value=Result.ok([j1, j2]))
        service = _make_service(backend=backend)

        result = await service.get_ephemeral_journals("user_1")

        assert result.is_ok
        # Newest first
        assert result.value[0].uid == "j2"
        assert result.value[1].uid == "j1"

    @pytest.mark.asyncio
    async def test_backend_error(self):
        backend = _make_backend()
        backend.find_by = AsyncMock(
            return_value=Result.fail(Errors.database("find", "err"))
        )
        service = _make_service(backend=backend)

        result = await service.get_ephemeral_journals("user_1")

        assert result.is_error


class TestGetPermanentJournals:
    """Tests for get_permanent_journals."""

    @pytest.mark.asyncio
    async def test_returns_permanent_only(self):
        backend = _make_backend()
        fifo = _make_entity(uid="fifo_1", max_retention=3, metadata={"entry_date": "2026-03-01"})
        perm = _make_entity(uid="perm_1", max_retention=None, metadata={"entry_date": "2026-03-01"})
        backend.find_by = AsyncMock(return_value=Result.ok([fifo, perm]))
        service = _make_service(backend=backend)

        result = await service.get_permanent_journals("user_1")

        assert result.is_ok
        uids = [j.uid for j in result.value]
        assert "perm_1" in uids
        assert "fifo_1" not in uids

    @pytest.mark.asyncio
    async def test_backend_error(self):
        backend = _make_backend()
        backend.find_by = AsyncMock(
            return_value=Result.fail(Errors.database("find", "err"))
        )
        service = _make_service(backend=backend)

        result = await service.get_permanent_journals("user_1")

        assert result.is_error


class TestGetJournalsByDateRange:
    """Tests for get_journals_by_date_range."""

    @pytest.mark.asyncio
    async def test_within_range(self):
        backend = _make_backend()
        j1 = _make_entity(uid="j1", metadata={"entry_date": "2026-03-05"})
        j2 = _make_entity(uid="j2", metadata={"entry_date": "2026-03-10"})
        backend.find_by = AsyncMock(return_value=Result.ok([j1, j2]))
        service = _make_service(backend=backend)

        result = await service.get_journals_by_date_range(
            "user_1", date(2026, 3, 1), date(2026, 3, 15)
        )

        assert result.is_ok
        assert len(result.value) == 2

    @pytest.mark.asyncio
    async def test_excludes_out_of_range(self):
        backend = _make_backend()
        inside = _make_entity(uid="in", metadata={"entry_date": "2026-03-05"})
        outside = _make_entity(uid="out", metadata={"entry_date": "2026-04-20"})
        backend.find_by = AsyncMock(return_value=Result.ok([inside, outside]))
        service = _make_service(backend=backend)

        result = await service.get_journals_by_date_range(
            "user_1", date(2026, 3, 1), date(2026, 3, 31)
        )

        assert result.is_ok
        uids = [j.uid for j in result.value]
        assert "in" in uids
        assert "out" not in uids

    @pytest.mark.asyncio
    async def test_bad_metadata_skipped(self):
        backend = _make_backend()
        bad = _make_entity(uid="bad", metadata={"entry_date": "not-a-date"})
        good = _make_entity(uid="good", metadata={"entry_date": "2026-03-05"})
        backend.find_by = AsyncMock(return_value=Result.ok([bad, good]))
        service = _make_service(backend=backend)

        result = await service.get_journals_by_date_range(
            "user_1", date(2026, 3, 1), date(2026, 3, 31)
        )

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0].uid == "good"

    @pytest.mark.asyncio
    async def test_backend_error(self):
        backend = _make_backend()
        backend.find_by = AsyncMock(
            return_value=Result.fail(Errors.database("find", "err"))
        )
        service = _make_service(backend=backend)

        result = await service.get_journals_by_date_range(
            "user_1", date(2026, 3, 1), date(2026, 3, 31)
        )

        assert result.is_error


# ===========================================================================
# B. Retrieve
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
        backend.get = AsyncMock(
            return_value=Result.fail(Errors.database("get", "DB timeout"))
        )
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
        sharing.check_access = AsyncMock(
            return_value=Result.fail(Errors.system("sharing down"))
        )
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
        backend.find_by = AsyncMock(
            return_value=Result.fail(Errors.database("find", "err"))
        )
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
        backend.find_by = AsyncMock(
            return_value=Result.fail(Errors.database("find", "err"))
        )
        service = _make_service(backend=backend)

        result = await service.get_submission_for_date(date(2026, 3, 5))

        assert result.is_error


# ===========================================================================
# C. Update / Status
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
    async def test_metadata_serialized_to_json(self):
        backend = _make_backend()
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        await service.update_submission("sub_123", {"metadata": {"key": "val"}})

        call_args = backend.update.call_args
        update_dict = call_args.args[1]
        assert isinstance(update_dict["metadata"], str)
        parsed = json.loads(update_dict["metadata"])
        assert parsed["key"] == "val"

    @pytest.mark.asyncio
    async def test_updated_at_always_set(self):
        backend = _make_backend()
        backend.update = AsyncMock(return_value=Result.ok(_make_entity()))
        service = _make_service(backend=backend)

        await service.update_submission("sub_123", {"title": "T"})

        call_args = backend.update.call_args
        update_dict = call_args.args[1]
        assert "updated_at" in update_dict
        assert isinstance(update_dict["updated_at"], datetime)

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
        meta = json.loads(update_dict["metadata"])
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
# D. Exercise Linking
# ===========================================================================


class TestProcessExerciseSubmission:
    """Tests for process_exercise_submission."""

    @pytest.mark.asyncio
    async def test_standard_linking_and_auto_share(self):
        backend = _make_backend()
        # Sequence of execute_query calls:
        # 1. Query exercise info
        # 2. Check group membership
        # 3. Get student uid for title gen
        # 4. Count prior submissions
        # 5. Set title
        # 6. Create FULFILLS_EXERCISE
        # 7. Auto-share with teacher
        backend.execute_query = AsyncMock(
            side_effect=[
                Result.ok([{
                    "exercise_entity_type": "exercise",
                    "scope": "assigned",
                    "teacher_uid": "teacher_1",
                    "student_uid": None,
                    "exercise_title": "Write Essay",
                    "group_uid": "grp_1",
                }]),
                Result.ok([{"student_uid": "user_1", "member_of_group": "grp_1"}]),
                Result.ok([{"student_uid": "user_1"}]),
                Result.ok([{"prior_count": 0}]),
                Result.ok([]),
                Result.ok([{"success": True}]),
                Result.ok([{"success": True}]),
            ]
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is True
        assert backend.execute_query.await_count == 7

    @pytest.mark.asyncio
    async def test_not_assigned_scope_returns_false(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(
            return_value=Result.ok([{
                "exercise_entity_type": "exercise",
                "scope": "shared",
                "teacher_uid": "teacher_1",
                "student_uid": None,
                "exercise_title": "Shared Ex",
                "group_uid": None,
            }])
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_exercise_not_found(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_missing")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_query_failure_returns_false(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(
            return_value=Result.fail(Errors.database("query", "timeout"))
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_revised_exercise_path(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(
            side_effect=[
                # 1. Query exercise
                Result.ok([{
                    "exercise_entity_type": "revised_exercise",
                    "scope": None,
                    "teacher_uid": "teacher_1",
                    "student_uid": "user_1",
                    "exercise_title": "Revision",
                    "group_uid": None,
                }]),
                # 2. Check submitter identity
                Result.ok([{"student_uid": "user_1"}]),
                # 3. Get student uid for title gen
                Result.ok([{"student_uid": "user_1"}]),
                # 4. Count prior submissions
                Result.ok([{"prior_count": 0}]),
                # 5. Set title
                Result.ok([]),
                # 6. FULFILLS_EXERCISE
                Result.ok([{"success": True}]),
                # 7. Auto-share
                Result.ok([{"success": True}]),
            ]
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "re_1")

        assert result.is_ok
        assert result.value is True

    @pytest.mark.asyncio
    async def test_wrong_student_for_revised_exercise(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(
            side_effect=[
                Result.ok([{
                    "exercise_entity_type": "revised_exercise",
                    "scope": None,
                    "teacher_uid": "teacher_1",
                    "student_uid": "user_2",
                    "exercise_title": "Revision",
                    "group_uid": None,
                }]),
                # Submitter is user_1, but exercise targets user_2
                Result.ok([{"student_uid": "user_1"}]),
            ]
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "re_1")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_not_in_group(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(
            side_effect=[
                Result.ok([{
                    "exercise_entity_type": "exercise",
                    "scope": "assigned",
                    "teacher_uid": "teacher_1",
                    "student_uid": None,
                    "exercise_title": "Essay",
                    "group_uid": "grp_1",
                }]),
                # Student not in group
                Result.ok([{"student_uid": "user_1", "member_of_group": None}]),
            ]
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_auto_title_generated(self):
        """When exercise has a title, submission gets an auto-generated title."""
        backend = _make_backend()
        backend.execute_query = AsyncMock(
            side_effect=[
                Result.ok([{
                    "exercise_entity_type": "exercise",
                    "scope": "assigned",
                    "teacher_uid": "teacher_1",
                    "student_uid": None,
                    "exercise_title": "Write Essay",
                    "group_uid": None,
                }]),
                # No group check needed (group_uid is None)
                # Get student uid for title
                Result.ok([{"student_uid": "user_1"}]),
                # Prior count
                Result.ok([{"prior_count": 0}]),
                # Set title
                Result.ok([]),
                # FULFILLS_EXERCISE
                Result.ok([{"success": True}]),
                # Auto-share
                Result.ok([{"success": True}]),
            ]
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is True
        # Title update query should have been executed
        assert backend.execute_query.await_count >= 4

    @pytest.mark.asyncio
    async def test_no_title_when_exercise_title_empty(self):
        """When exercise has no title, no title update is attempted."""
        backend = _make_backend()
        backend.execute_query = AsyncMock(
            side_effect=[
                Result.ok([{
                    "exercise_entity_type": "exercise",
                    "scope": "assigned",
                    "teacher_uid": "teacher_1",
                    "student_uid": None,
                    "exercise_title": "",
                    "group_uid": None,
                }]),
                # FULFILLS_EXERCISE
                Result.ok([{"success": True}]),
                # Auto-share
                Result.ok([{"success": True}]),
            ]
        )
        service = _make_service(backend=backend)

        result = await service.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        # Only 3 queries (no title generation queries)
        assert backend.execute_query.await_count == 3


class TestProcessAssignmentSubmission:
    """Tests for process_assignment_submission backward-compat alias."""

    @pytest.mark.asyncio
    async def test_delegates_to_process_exercise_submission(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.process_assignment_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value is False  # Exercise not found


# ===========================================================================
# E. Content Management
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
        meta = json.loads(update_dict["metadata"])
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
        meta = json.loads(update_dict["metadata"])
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
        meta = json.loads(update_dict["metadata"])
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
# F. Delete + Export
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
# G. Additional Coverage
# ===========================================================================


class TestCountJournalsForDate:
    """Tests for _count_journals_for_date."""

    @pytest.mark.asyncio
    async def test_returns_count(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(return_value=Result.ok([{"total": 5}]))
        service = _make_service(backend=backend)

        count = await service._count_journals_for_date("user_1", date(2026, 3, 1))

        assert count == 5

    @pytest.mark.asyncio
    async def test_returns_zero_on_error(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(
            return_value=Result.fail(Errors.database("count", "err"))
        )
        service = _make_service(backend=backend)

        count = await service._count_journals_for_date("user_1", date(2026, 3, 1))

        assert count == 0

    @pytest.mark.asyncio
    async def test_returns_zero_on_empty_result(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        count = await service._count_journals_for_date("user_1", date(2026, 3, 1))

        assert count == 0


class TestGenerateJournalTitle:
    """Tests for generate_journal_title."""

    @pytest.mark.asyncio
    async def test_generates_title_with_sequence(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(return_value=Result.ok([{"total": 2}]))
        service = _make_service(backend=backend)

        result = await service.generate_journal_title("user_1", date(2026, 3, 15))

        assert result.is_ok
        assert "#3" in result.value  # 2 existing + 1

    @pytest.mark.asyncio
    async def test_uses_today_when_no_date(self):
        backend = _make_backend()
        backend.execute_query = AsyncMock(return_value=Result.ok([{"total": 0}]))
        service = _make_service(backend=backend)

        result = await service.generate_journal_title("user_1")

        assert result.is_ok
        assert "#1" in result.value


class TestGetRecentSubmissionsNoFilters:
    """Tests for get_recent_submissions when no filters provided (list path)."""

    @pytest.mark.asyncio
    async def test_no_filters_uses_list(self):
        backend = _make_backend()
        entities = [
            _make_entity(uid=f"s_{i}", created_at=datetime(2026, 3, i + 1, tzinfo=UTC))
            for i in range(5)
        ]
        backend.list = AsyncMock(return_value=Result.ok(entities))
        service = _make_service(backend=backend)

        result = await service.get_recent_submissions(limit=3)

        assert result.is_ok
        assert len(result.value) <= 3
        backend.list.assert_awaited_once()
        backend.find_by.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_filters_list_error_returns_empty(self):
        backend = _make_backend()
        backend.list = AsyncMock(
            return_value=Result.fail(Errors.database("list", "err"))
        )
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
        backend.find_by = AsyncMock(
            return_value=Result.fail(Errors.database("find", "err"))
        )
        service = _make_service(backend=backend)

        result = await service.get_public_submissions()

        assert result.is_error


class TestMakePermanent:
    """Tests for make_permanent."""

    @pytest.mark.asyncio
    async def test_success(self):
        backend = _make_backend()
        entity = _make_entity(max_retention=3)
        backend.get = AsyncMock(return_value=Result.ok(entity))
        backend.update = AsyncMock(return_value=Result.ok(_make_entity(max_retention=None)))
        service = _make_service(backend=backend)

        result = await service.make_permanent("sub_123")

        assert result.is_ok

    @pytest.mark.asyncio
    async def test_not_found(self):
        backend = _make_backend()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.make_permanent("missing")

        assert result.is_error


class TestGetJournalWithInsights:
    """Tests for get_journal_with_insights."""

    @pytest.mark.asyncio
    async def test_success(self):
        backend = _make_backend()
        entity = _make_entity(entity_type=EntityType.JOURNAL_SUBMISSION)
        backend.get = AsyncMock(return_value=Result.ok(entity))
        service = _make_service(backend=backend)

        result = await service.get_journal_with_insights("sub_123")

        assert result.is_ok
        assert result.value is not None

    @pytest.mark.asyncio
    async def test_non_journal_returns_none(self):
        backend = _make_backend()
        entity = _make_entity(entity_type=EntityType.EXERCISE_SUBMISSION)
        backend.get = AsyncMock(return_value=Result.ok(entity))
        service = _make_service(backend=backend)

        result = await service.get_journal_with_insights("sub_123")

        assert result.is_ok
        assert result.value is None

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        backend = _make_backend()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.get_journal_with_insights("missing")

        assert result.is_ok
        assert result.value is None


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
