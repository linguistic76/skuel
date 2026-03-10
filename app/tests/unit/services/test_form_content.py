"""Tests for build_form_processed_content."""

from core.services.forms.form_content import (
    MAX_PROCESSED_CONTENT_LENGTH,
    build_form_processed_content,
)


class TestBuildFormProcessedContent:
    def test_header_format(self):
        result = build_form_processed_content(
            template_title="Feedback Form",
            template_uid="ft_abc",
            schema=({"name": "q1", "type": "text", "label": "Q1"},),
            form_data={"q1": "answer"},
        )
        assert result.startswith("Form: Feedback Form (ft_abc)")

    def test_schema_order(self):
        """Fields appear in schema order, not dict insertion order."""
        schema = (
            {"name": "z_field", "type": "text", "label": "Zebra"},
            {"name": "a_field", "type": "text", "label": "Apple"},
        )
        # Dict with reversed insertion order
        form_data = {"a_field": "second", "z_field": "first"}
        result = build_form_processed_content(
            template_title="T",
            template_uid="ft_1",
            schema=schema,
            form_data=form_data,
        )
        lines = result.split("\n")
        assert lines[1] == "Zebra: first"
        assert lines[2] == "Apple: second"

    def test_labels_used(self):
        """Uses label when available, falls back to name."""
        schema = (
            {"name": "q1", "type": "text", "label": "Full Question"},
            {"name": "q2", "type": "text"},  # no label
        )
        result = build_form_processed_content(
            template_title="T",
            template_uid="ft_1",
            schema=schema,
            form_data={"q1": "a", "q2": "b"},
        )
        assert "Full Question: a" in result
        assert "q2: b" in result

    def test_unknown_keys_ignored(self):
        """Keys not in schema are excluded from output."""
        schema = ({"name": "q1", "type": "text", "label": "Q1"},)
        result = build_form_processed_content(
            template_title="T",
            template_uid="ft_1",
            schema=schema,
            form_data={"q1": "valid", "hacker_field": "injected"},
        )
        assert "hacker_field" not in result
        assert "injected" not in result
        assert "Q1: valid" in result

    def test_booleans_normalized(self):
        """True -> 'Yes', False -> 'No'."""
        schema = (
            {"name": "agree", "type": "checkbox", "label": "Agree?"},
            {"name": "opt_out", "type": "checkbox", "label": "Opt out?"},
        )
        result = build_form_processed_content(
            template_title="T",
            template_uid="ft_1",
            schema=schema,
            form_data={"agree": True, "opt_out": False},
        )
        assert "Agree?: Yes" in result
        assert "Opt out?: No" in result

    def test_none_values_skipped(self):
        schema = (
            {"name": "q1", "type": "text", "label": "Q1"},
            {"name": "q2", "type": "text", "label": "Q2"},
        )
        result = build_form_processed_content(
            template_title="T",
            template_uid="ft_1",
            schema=schema,
            form_data={"q1": "answer", "q2": None},
        )
        assert "Q1: answer" in result
        assert "Q2" not in result

    def test_empty_string_skipped(self):
        schema = ({"name": "q1", "type": "text", "label": "Q1"},)
        result = build_form_processed_content(
            template_title="T",
            template_uid="ft_1",
            schema=schema,
            form_data={"q1": "   "},
        )
        assert "Q1" not in result.split("\n", 1)[-1]  # Not in body (may be in header)

    def test_no_schema_returns_header_only(self):
        result = build_form_processed_content(
            template_title="Empty",
            template_uid="ft_1",
            schema=None,
            form_data={"q1": "answer"},
        )
        assert result == "Form: Empty (ft_1)"

    def test_truncation(self):
        """Output is truncated at MAX_PROCESSED_CONTENT_LENGTH."""
        schema = ({"name": "q1", "type": "text", "label": "Q1"},)
        long_value = "x" * (MAX_PROCESSED_CONTENT_LENGTH + 1000)
        result = build_form_processed_content(
            template_title="T",
            template_uid="ft_1",
            schema=schema,
            form_data={"q1": long_value},
        )
        assert len(result) == MAX_PROCESSED_CONTENT_LENGTH
