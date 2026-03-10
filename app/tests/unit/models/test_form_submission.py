"""Tests for FormSubmission domain model."""

import json

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.forms.form_submission import FormSubmission
from core.models.forms.form_submission_dto import FormSubmissionDTO


class TestFormSubmissionConstruction:
    """Test FormSubmission frozen dataclass construction."""

    def test_basic_construction(self):
        fs = FormSubmission(
            uid="fs_test_123",
            title="My Response",
            user_uid="user_1",
            form_template_uid="ft_test_456",
            form_data={"q1": "answer 1", "q2": "answer 2"},
        )
        assert fs.uid == "fs_test_123"
        assert fs.title == "My Response"
        assert fs.entity_type == EntityType.FORM_SUBMISSION
        assert fs.user_uid == "user_1"
        assert fs.form_template_uid == "ft_test_456"
        assert fs.form_data == {"q1": "answer 1", "q2": "answer 2"}

    def test_entity_type_forced(self):
        """entity_type is always FORM_SUBMISSION regardless of input."""
        fs = FormSubmission(
            uid="fs_force",
            title="Test",
            entity_type=EntityType.TASK,
        )
        assert fs.entity_type == EntityType.FORM_SUBMISSION

    def test_default_status_completed(self):
        """FormSubmissions default to COMPLETED status."""
        fs = FormSubmission(uid="fs_status", title="Test")
        assert fs.status == EntityStatus.COMPLETED

    def test_default_visibility_private(self):
        """FormSubmission is user-owned — default visibility is PRIVATE."""
        fs = FormSubmission(uid="fs_vis", title="Test", user_uid="user_1")
        assert fs.visibility == Visibility.PRIVATE

    def test_has_data(self):
        fs = FormSubmission(
            uid="fs_data",
            title="Test",
            form_data={"q1": "answer"},
        )
        assert fs.has_data() is True

    def test_has_data_empty(self):
        fs = FormSubmission(uid="fs_empty", title="Test", form_data={})
        assert fs.has_data() is False

    def test_has_data_none(self):
        fs = FormSubmission(uid="fs_none", title="Test")
        assert fs.has_data() is False


class TestFormSubmissionConversion:
    def test_to_dto(self):
        fs = FormSubmission(
            uid="fs_conv",
            title="Test",
            user_uid="user_1",
            form_template_uid="ft_1",
            form_data={"q1": "answer"},
            processed_content="q1: answer",
        )
        dto = fs.to_dto()
        assert isinstance(dto, FormSubmissionDTO)
        assert dto.uid == "fs_conv"
        assert dto.user_uid == "user_1"
        assert dto.form_template_uid == "ft_1"
        assert dto.form_data == {"q1": "answer"}
        assert dto.processed_content == "q1: answer"

    def test_from_dto(self):
        dto = FormSubmissionDTO(
            uid="fs_from_dto",
            title="From DTO",
            user_uid="user_2",
            form_template_uid="ft_2",
            form_data={"q1": "val"},
        )
        fs = FormSubmission._from_dto(dto)
        assert fs.uid == "fs_from_dto"
        assert fs.entity_type == EntityType.FORM_SUBMISSION
        assert fs.user_uid == "user_2"
        assert fs.form_template_uid == "ft_2"


class TestFormSubmissionDTOSerialization:
    def test_to_dict(self):
        dto = FormSubmissionDTO(
            uid="fs_ser",
            title="Test",
            user_uid="user_1",
            form_data={"q1": "answer"},
        )
        d = dto.to_dict()
        assert d["uid"] == "fs_ser"
        assert d["user_uid"] == "user_1"
        # form_data should be JSON string for Neo4j
        assert isinstance(d["form_data"], str)
        parsed = json.loads(d["form_data"])
        assert parsed["q1"] == "answer"

    def test_from_dict_json_string(self):
        data = {
            "uid": "fs_deser",
            "title": "Test",
            "user_uid": "user_1",
            "form_data": json.dumps({"q1": "answer"}),
            "form_template_uid": "ft_1",
        }
        dto = FormSubmissionDTO.from_dict(data)
        assert dto.uid == "fs_deser"
        assert isinstance(dto.form_data, dict)
        assert dto.form_data["q1"] == "answer"


class TestFormSubmissionEntityType:
    """Test EntityType traits for FORM_SUBMISSION."""

    def test_user_owned(self):
        assert EntityType.FORM_SUBMISSION.requires_user_uid()

    def test_not_activity(self):
        assert not EntityType.FORM_SUBMISSION.is_activity()

    def test_is_derived(self):
        assert EntityType.FORM_SUBMISSION.is_derived()

    def test_content_origin(self):
        from core.models.enums.entity_enums import ContentOrigin

        assert EntityType.FORM_SUBMISSION.content_origin() == ContentOrigin.USER_CREATED

    def test_from_string(self):
        assert EntityType.from_string("form_submission") == EntityType.FORM_SUBMISSION
