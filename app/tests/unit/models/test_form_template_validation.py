"""Tests for FormTemplate.validate_response() — schema-based form data validation."""

from core.models.forms.form_template import FormTemplate


def _make_template(**kwargs):
    """Helper to create a FormTemplate with sensible defaults."""
    defaults = {"uid": "ft_test_1", "title": "Test Form"}
    defaults.update(kwargs)
    return FormTemplate(**defaults)


class TestValidateResponseBasic:
    """Test basic required/optional field validation."""

    def test_valid_response(self):
        ft = _make_template(
            form_schema=[
                {"name": "q1", "type": "text", "label": "Q1", "required": True},
                {"name": "q2", "type": "textarea", "label": "Q2"},
            ]
        )
        errors = ft.validate_response({"q1": "answer", "q2": "long text"})
        assert errors == []

    def test_missing_required_field(self):
        ft = _make_template(
            form_schema=[
                {"name": "q1", "type": "text", "label": "Q1", "required": True},
            ]
        )
        errors = ft.validate_response({})
        assert len(errors) == 1
        assert "Required field 'q1'" in errors[0]

    def test_empty_required_field(self):
        ft = _make_template(
            form_schema=[
                {"name": "q1", "type": "text", "label": "Q1", "required": True},
            ]
        )
        errors = ft.validate_response({"q1": ""})
        assert len(errors) == 1
        assert "Required field 'q1'" in errors[0]

    def test_whitespace_only_required_field(self):
        ft = _make_template(
            form_schema=[
                {"name": "q1", "type": "text", "label": "Q1", "required": True},
            ]
        )
        errors = ft.validate_response({"q1": "   "})
        assert len(errors) == 1

    def test_optional_field_can_be_missing(self):
        ft = _make_template(
            form_schema=[
                {"name": "q1", "type": "text", "label": "Q1"},
            ]
        )
        errors = ft.validate_response({})
        assert errors == []

    def test_optional_field_can_be_empty(self):
        ft = _make_template(
            form_schema=[
                {"name": "q1", "type": "text", "label": "Q1"},
            ]
        )
        errors = ft.validate_response({"q1": ""})
        assert errors == []

    def test_unknown_field_rejected(self):
        ft = _make_template(
            form_schema=[
                {"name": "q1", "type": "text", "label": "Q1"},
            ]
        )
        errors = ft.validate_response({"q1": "ok", "unknown_field": "value"})
        assert len(errors) == 1
        assert "Unknown field 'unknown_field'" in errors[0]


class TestValidateResponseSelectField:
    """Test select field validation (value must be in options)."""

    def test_valid_select_value(self):
        ft = _make_template(
            form_schema=[
                {"name": "color", "type": "select", "label": "Color", "options": ["red", "blue"]},
            ]
        )
        errors = ft.validate_response({"color": "red"})
        assert errors == []

    def test_invalid_select_value(self):
        ft = _make_template(
            form_schema=[
                {"name": "color", "type": "select", "label": "Color", "options": ["red", "blue"]},
            ]
        )
        errors = ft.validate_response({"color": "green"})
        assert len(errors) == 1
        assert "not in allowed options" in errors[0]

    def test_select_without_options_accepts_any(self):
        """Select field with no options list accepts any value."""
        ft = _make_template(
            form_schema=[
                {"name": "q1", "type": "select", "label": "Q1"},
            ]
        )
        errors = ft.validate_response({"q1": "anything"})
        assert errors == []


class TestValidateResponseNumberField:
    """Test number field validation."""

    def test_valid_number(self):
        ft = _make_template(
            form_schema=[
                {"name": "age", "type": "number", "label": "Age"},
            ]
        )
        errors = ft.validate_response({"age": 25})
        assert errors == []

    def test_valid_number_string(self):
        """Numbers as strings (from HTML forms) are accepted."""
        ft = _make_template(
            form_schema=[
                {"name": "age", "type": "number", "label": "Age"},
            ]
        )
        errors = ft.validate_response({"age": "25"})
        assert errors == []

    def test_invalid_number_string(self):
        ft = _make_template(
            form_schema=[
                {"name": "age", "type": "number", "label": "Age"},
            ]
        )
        errors = ft.validate_response({"age": "not-a-number"})
        assert len(errors) == 1
        assert "must be a number" in errors[0]

    def test_number_min_max(self):
        ft = _make_template(
            form_schema=[
                {"name": "rating", "type": "number", "label": "Rating", "min": 1, "max": 5},
            ]
        )
        assert ft.validate_response({"rating": 3}) == []
        assert ft.validate_response({"rating": 0}) != []
        assert ft.validate_response({"rating": 6}) != []

    def test_number_below_min(self):
        ft = _make_template(
            form_schema=[
                {"name": "score", "type": "number", "label": "Score", "min": 0},
            ]
        )
        errors = ft.validate_response({"score": -1})
        assert len(errors) == 1
        assert ">= 0" in errors[0]

    def test_number_above_max(self):
        ft = _make_template(
            form_schema=[
                {"name": "score", "type": "number", "label": "Score", "max": 100},
            ]
        )
        errors = ft.validate_response({"score": 101})
        assert len(errors) == 1
        assert "<= 100" in errors[0]


class TestValidateResponseCheckboxField:
    """Test checkbox field validation."""

    def test_checkbox_boolean(self):
        ft = _make_template(
            form_schema=[
                {"name": "agree", "type": "checkbox", "label": "Agree"},
            ]
        )
        assert ft.validate_response({"agree": True}) == []
        assert ft.validate_response({"agree": False}) == []


class TestValidateResponseEdgeCases:
    """Test edge cases in validation."""

    def test_no_form_schema(self):
        ft = _make_template()
        errors = ft.validate_response({"q1": "answer"})
        assert len(errors) == 1
        assert "no form_schema" in errors[0]

    def test_empty_response(self):
        ft = _make_template(
            form_schema=[
                {"name": "q1", "type": "text", "label": "Q1"},
            ]
        )
        errors = ft.validate_response({})
        assert errors == []

    def test_multiple_errors_reported(self):
        ft = _make_template(
            form_schema=[
                {"name": "q1", "type": "text", "label": "Q1", "required": True},
                {"name": "q2", "type": "text", "label": "Q2", "required": True},
            ]
        )
        errors = ft.validate_response({})
        assert len(errors) == 2

    def test_mixed_valid_and_invalid(self):
        ft = _make_template(
            form_schema=[
                {"name": "name", "type": "text", "label": "Name", "required": True},
                {"name": "age", "type": "number", "label": "Age"},
            ]
        )
        errors = ft.validate_response({"name": "Alice", "age": "not-a-number"})
        assert len(errors) == 1
        assert "must be a number" in errors[0]
