"""Tests for FormTemplate + FormSubmission request model validation."""

import pytest
from pydantic import ValidationError

from core.models.forms.form_submission_request import FormSubmissionCreateRequest
from core.models.forms.form_template_request import (
    FormTemplateCreateRequest,
    FormTemplateUpdateRequest,
)


class TestFormTemplateCreateRequest:
    def test_valid_request(self):
        req = FormTemplateCreateRequest(
            title="Feedback Form",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
        )
        assert req.title == "Feedback Form"
        assert len(req.form_schema) == 1

    def test_missing_title(self):
        with pytest.raises(ValidationError):
            FormTemplateCreateRequest(
                form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
            )

    def test_empty_title(self):
        with pytest.raises(ValidationError):
            FormTemplateCreateRequest(
                title="",
                form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
            )

    def test_missing_form_schema(self):
        with pytest.raises(ValidationError):
            FormTemplateCreateRequest(title="Test")

    def test_empty_form_schema(self):
        with pytest.raises(ValidationError):
            FormTemplateCreateRequest(title="Test", form_schema=[])

    def test_invalid_field_type(self):
        with pytest.raises(ValidationError, match="invalid type"):
            FormTemplateCreateRequest(
                title="Test",
                form_schema=[{"name": "q1", "type": "invalid_type", "label": "Q1"}],
            )

    def test_missing_field_name(self):
        with pytest.raises(ValidationError, match="missing required key 'name'"):
            FormTemplateCreateRequest(
                title="Test",
                form_schema=[{"type": "text", "label": "Q1"}],
            )

    def test_missing_field_label(self):
        with pytest.raises(ValidationError, match="missing required key 'label'"):
            FormTemplateCreateRequest(
                title="Test",
                form_schema=[{"name": "q1", "type": "text"}],
            )

    def test_select_without_options(self):
        with pytest.raises(ValidationError, match="requires 'options'"):
            FormTemplateCreateRequest(
                title="Test",
                form_schema=[{"name": "q1", "type": "select", "label": "Q1"}],
            )

    def test_select_with_options(self):
        req = FormTemplateCreateRequest(
            title="Test",
            form_schema=[{"name": "q1", "type": "select", "label": "Q1", "options": ["a", "b"]}],
        )
        assert req.form_schema[0]["options"] == ["a", "b"]

    def test_all_field_types(self):
        """All 6 field types are accepted."""
        req = FormTemplateCreateRequest(
            title="Test",
            form_schema=[
                {"name": "q1", "type": "text", "label": "Q1"},
                {"name": "q2", "type": "textarea", "label": "Q2"},
                {"name": "q3", "type": "select", "label": "Q3", "options": ["a"]},
                {"name": "q4", "type": "checkbox", "label": "Q4"},
                {"name": "q5", "type": "number", "label": "Q5"},
                {"name": "q6", "type": "date", "label": "Q6"},
            ],
        )
        assert len(req.form_schema) == 6


class TestFormTemplateUpdateRequest:
    def test_all_optional(self):
        req = FormTemplateUpdateRequest()
        assert req.title is None
        assert req.form_schema is None

    def test_partial_update(self):
        req = FormTemplateUpdateRequest(title="New Title")
        assert req.title == "New Title"
        assert req.form_schema is None

    def test_schema_validation_on_update(self):
        with pytest.raises(ValidationError, match="invalid type"):
            FormTemplateUpdateRequest(
                form_schema=[{"name": "q1", "type": "bad", "label": "Q1"}],
            )


class TestFormSubmissionCreateRequest:
    def test_valid_request(self):
        req = FormSubmissionCreateRequest(
            form_template_uid="ft_123",
            form_data={"q1": "answer"},
        )
        assert req.form_template_uid == "ft_123"

    def test_missing_template_uid(self):
        with pytest.raises(ValidationError):
            FormSubmissionCreateRequest(form_data={"q1": "answer"})

    def test_missing_form_data(self):
        with pytest.raises(ValidationError):
            FormSubmissionCreateRequest(form_template_uid="ft_123")

    def test_with_sharing_options(self):
        req = FormSubmissionCreateRequest(
            form_template_uid="ft_123",
            form_data={"q1": "answer"},
            group_uid="group_1",
            share_with_admin=True,
            recipient_uids=["user_2"],
        )
        assert req.group_uid == "group_1"
        assert req.share_with_admin is True
        assert req.recipient_uids == ["user_2"]
