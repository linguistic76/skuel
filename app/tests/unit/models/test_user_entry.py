"""Tests for UserEntry domain model (ADR-054)."""

from dataclasses import FrozenInstanceError, fields
from datetime import datetime

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_entry_enums import SubmissionModality
from core.models.user_entry.user_entry import UserEntry
from core.models.user_entry.user_entry_dto import UserEntryDTO


class TestUserEntryConstruction:
    """UserEntry frozen-dataclass construction and __post_init__ behavior."""

    def test_basic_construction(self):
        entry = UserEntry(
            uid="ue_test_123",
            title="My Submission",
            user_uid="user_1",
        )
        assert entry.uid == "ue_test_123"
        assert entry.title == "My Submission"
        assert entry.user_uid == "user_1"
        assert entry.entity_type == EntityType.USER_ENTRY

    def test_entity_type_mismatch_raises(self):
        """G6: a wrong entity_type fails loudly instead of being silently corrected."""
        with pytest.raises(ValueError, match="entity_type"):
            UserEntry(uid="ue_force", title="Test", user_uid="user_1", entity_type=EntityType.TASK)

    def test_default_pipeline_none(self):
        entry = UserEntry(uid="ue_p", title="Test", user_uid="user_1")
        assert entry.pipeline == Pipeline.NONE

    def test_default_visibility_private(self):
        entry = UserEntry(uid="ue_v", title="Test", user_uid="user_1")
        assert entry.visibility == Visibility.PRIVATE

    def test_file_fields_default_none(self):
        entry = UserEntry(uid="ue_f", title="Test", user_uid="user_1")
        assert entry.original_filename is None
        assert entry.file_path is None
        assert entry.file_size is None
        assert entry.file_type is None

    def test_processing_fields_default_none(self):
        entry = UserEntry(uid="ue_proc", title="Test", user_uid="user_1")
        assert entry.processing_started_at is None
        assert entry.processing_completed_at is None
        assert entry.processing_error is None
        assert entry.processed_content is None
        assert entry.instructions is None
        assert entry.max_retention is None

    def test_modality_default_none(self):
        entry = UserEntry(uid="ue_m", title="Test", user_uid="user_1")
        assert entry.modality is None

    def test_is_frozen(self):
        entry = UserEntry(uid="ue_frozen", title="Test", user_uid="user_1")
        with pytest.raises(FrozenInstanceError):
            entry.title = "Changed"  # type: ignore[misc]

    def test_no_revision_number_field(self):
        """revision_number lives on the FULFILLS_EXERCISE edge, not the node."""
        field_names = {f.name for f in fields(UserEntry)}
        assert "revision_number" not in field_names


class TestUserEntryPipeline:
    """pipeline discriminator drives dispatch."""

    @pytest.mark.parametrize(
        "pipeline",
        [
            Pipeline.NONE,
            Pipeline.TRANSCRIBE,
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
            Pipeline.LLM_SUMMARY,
            Pipeline.TEACHER_REVIEW,
        ],
    )
    def test_pipeline_roundtrip(self, pipeline: Pipeline):
        entry = UserEntry(
            uid=f"ue_{pipeline.value}",
            title="Test",
            user_uid="user_1",
            pipeline=pipeline,
        )
        assert entry.pipeline == pipeline


class TestUserEntryHelpers:
    """Helper methods."""

    def test_get_processing_duration_none_when_incomplete(self):
        entry = UserEntry(uid="ue_d1", title="Test", user_uid="user_1")
        assert entry.get_processing_duration() is None

    def test_get_processing_duration_computed(self):
        started = datetime(2026, 4, 14, 10, 0, 0)
        completed = datetime(2026, 4, 14, 10, 0, 30)
        entry = UserEntry(
            uid="ue_d2",
            title="Test",
            user_uid="user_1",
            processing_started_at=started,
            processing_completed_at=completed,
        )
        assert entry.get_processing_duration() == 30.0

    def test_get_summary_truncates(self):
        long = "x" * 500
        entry = UserEntry(uid="ue_sum", title="T", user_uid="user_1", content=long)
        result = entry.get_summary(max_length=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_get_summary_prefers_content_over_processed(self):
        entry = UserEntry(
            uid="ue_sum2",
            title="T",
            user_uid="user_1",
            content="raw content",
            processed_content="processed version",
        )
        assert entry.get_summary() == "raw content"

    def test_generate_exercise_title_no_revision(self):
        title = UserEntry.generate_exercise_title(
            exercise_title="Chapter 1 Quiz",
            user_uid="user_alice",
        )
        assert title == "Chapter 1 Quiz \u2014 alice"

    def test_generate_exercise_title_with_revision(self):
        from datetime import date

        title = UserEntry.generate_exercise_title(
            exercise_title="Chapter 1 Quiz",
            user_uid="user_alice",
            revision_number=2,
            revision_date=date(2026, 4, 14),
        )
        assert "#2" in title
        assert "Apr 14" in title


class TestUserEntryDTORoundtrip:
    """DTO <-> domain model round-trip."""

    def test_to_dto_preserves_core_fields(self):
        entry = UserEntry(
            uid="ue_rt",
            title="Roundtrip",
            user_uid="user_1",
            content="Some content",
            pipeline=Pipeline.TEACHER_REVIEW,
            modality=SubmissionModality.FILE_UPLOAD,
            original_filename="essay.md",
            file_size=1024,
        )
        dto = entry.to_dto()
        assert isinstance(dto, UserEntryDTO)
        assert dto.uid == "ue_rt"
        assert dto.title == "Roundtrip"
        assert dto.pipeline == Pipeline.TEACHER_REVIEW
        assert dto.modality == SubmissionModality.FILE_UPLOAD
        assert dto.original_filename == "essay.md"
        assert dto.file_size == 1024

    def test_dto_to_dict_includes_pipeline(self):
        dto = UserEntryDTO(
            uid="ue_dict",
            title="Dict",
            user_uid="user_1",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.SUBMITTED,
            pipeline=Pipeline.TRANSCRIBE,
        )
        data = dto.to_dict()
        assert data["pipeline"] == "transcribe"
        assert data["uid"] == "ue_dict"

    def test_from_dto_restores_entry(self):
        dto = UserEntryDTO(
            uid="ue_back",
            title="Back",
            user_uid="user_1",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.ACTIVE,
            pipeline=Pipeline.LLM_SUMMARY,
            instructions="summarize in 3 bullets",
        )
        entry = UserEntry.from_dto(dto)
        assert entry.uid == "ue_back"
        assert entry.pipeline == Pipeline.LLM_SUMMARY
        assert entry.instructions == "summarize in 3 bullets"
        assert entry.entity_type == EntityType.USER_ENTRY
