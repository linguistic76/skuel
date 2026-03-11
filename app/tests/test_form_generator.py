"""
Tests for FormGenerator — pre-fill, sections, help text, hidden fields, fragments.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

from ui.patterns.form_generator import FormGenerator

# ============================================================================
# Test fixtures — minimal Pydantic models
# ============================================================================


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SampleCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="Title")
    description: str | None = Field(None, description="Description")
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority")
    due_date: date | None = Field(None, description="Due date")
    duration_minutes: int = Field(default=30, ge=5, le=480, description="Duration")
    is_active: bool = Field(default=True, description="Active")


class SampleUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    priority: Priority | None = None
    due_date: date | None = None
    duration_minutes: int | None = Field(None, ge=5, le=480)
    is_active: bool | None = None


@dataclass(frozen=True)
class SampleEntity:
    uid: str
    title: str
    description: str | None = None
    priority: Priority = Priority.MEDIUM
    due_date: date | None = None
    duration_minutes: int = 30
    is_active: bool = True


# ============================================================================
# Helper to extract HTML attributes from FT components
# ============================================================================


def get_form_html(form) -> str:
    """Render an FT component to HTML string for assertion."""
    from fasthtml.common import to_xml

    return to_xml(form)


# ============================================================================
# Tests: from_model with values
# ============================================================================


class TestFromModelWithValues:
    """Test pre-filling via the values parameter."""

    def test_no_values_produces_empty_form(self):
        form = FormGenerator.from_model(
            SampleCreateRequest, action="/test", include_fields=["title"]
        )
        html = get_form_html(form)
        assert 'name="title"' in html
        assert 'value="My Task"' not in html

    def test_text_input_prefilled(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["title"],
            values={"title": "My Task"},
        )
        html = get_form_html(form)
        assert 'value="My Task"' in html

    def test_textarea_prefilled(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["description"],
            values={"description": "Some details"},
        )
        html = get_form_html(form)
        assert "Some details" in html

    def test_number_input_prefilled(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["duration_minutes"],
            values={"duration_minutes": 60},
        )
        html = get_form_html(form)
        assert 'value="60"' in html

    def test_enum_select_prefilled(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["priority"],
            values={"priority": Priority.HIGH},
        )
        html = get_form_html(form)
        assert 'value="high" selected' in html
        assert 'value="low" selected' not in html
        assert 'value="medium" selected' not in html

    def test_enum_select_no_value_nothing_selected(self):
        form = FormGenerator.from_model(
            SampleUpdateRequest,
            action="/test",
            include_fields=["priority"],
        )
        html = get_form_html(form)
        assert "-- Select --" in html

    def test_date_input_prefilled(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["due_date"],
            values={"due_date": date(2026, 6, 15)},
        )
        html = get_form_html(form)
        assert 'value="2026-06-15"' in html

    def test_date_string_value_works(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["due_date"],
            values={"due_date": "2026-06-15"},
        )
        html = get_form_html(form)
        assert 'value="2026-06-15"' in html

    def test_checkbox_prefilled_true(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["is_active"],
            values={"is_active": True},
        )
        html = get_form_html(form)
        assert "checked" in html

    def test_checkbox_prefilled_false(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["is_active"],
            values={"is_active": False},
        )
        html = get_form_html(form)
        assert "checked" not in html

    def test_none_value_leaves_field_empty(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["title"],
            values={"title": None},
        )
        html = get_form_html(form)
        assert 'value="' not in html or 'value=""' not in html

    def test_values_dict_does_not_affect_other_params(self):
        """Ensure values parameter doesn't break existing behavior."""
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            method="POST",
            submit_label="Save",
            include_fields=["title", "priority"],
            values={"title": "Hello"},
            form_attrs={"hx_post": "/test"},
        )
        html = get_form_html(form)
        assert 'hx-post="/test"' in html
        assert 'value="Hello"' in html
        assert "Save" in html


# ============================================================================
# Tests: from_instance
# ============================================================================


class TestFromInstance:
    """Test the from_instance convenience method."""

    def test_from_dataclass_instance(self):
        entity = SampleEntity(
            uid="task_123",
            title="Fix bug",
            description="Important fix",
            priority=Priority.HIGH,
            due_date=date(2026, 7, 1),
            duration_minutes=45,
            is_active=True,
        )
        form = FormGenerator.from_instance(
            SampleUpdateRequest,
            entity,
            action="/test",
            include_fields=["title", "description", "priority", "due_date"],
        )
        html = get_form_html(form)
        assert 'value="Fix bug"' in html
        assert "Important fix" in html
        assert 'value="high" selected' in html
        assert 'value="2026-07-01"' in html

    def test_from_dict_instance(self):
        data = {"title": "My Goal", "description": "Achieve it", "priority": "high"}
        form = FormGenerator.from_instance(
            SampleUpdateRequest,
            data,
            action="/test",
            include_fields=["title", "description"],
        )
        html = get_form_html(form)
        assert 'value="My Goal"' in html
        assert "Achieve it" in html

    def test_missing_fields_on_instance_are_none(self):
        """Fields in model but not on instance should be treated as None."""

        @dataclass(frozen=True)
        class PartialEntity:
            title: str

        entity = PartialEntity(title="Only title")
        form = FormGenerator.from_instance(
            SampleUpdateRequest,
            entity,
            action="/test",
            include_fields=["title", "description"],
        )
        html = get_form_html(form)
        assert 'value="Only title"' in html

    def test_kwargs_passed_through(self):
        entity = SampleEntity(uid="t1", title="Test")
        form = FormGenerator.from_instance(
            SampleUpdateRequest,
            entity,
            action="/test",
            submit_label="Update",
            form_attrs={"hx_post": "/api/update"},
            include_fields=["title"],
        )
        html = get_form_html(form)
        assert "Update" in html
        assert 'hx-post="/api/update"' in html


# ============================================================================
# Tests: sections
# ============================================================================


class TestSections:
    """Test sectioned form generation."""

    def test_sections_creates_grouped_fields(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            sections={
                "Basic Info": ["title", "description"],
                "Settings": ["priority", "due_date"],
            },
        )
        html = get_form_html(form)
        assert "Basic Info" in html
        assert "Settings" in html
        assert 'name="title"' in html
        assert 'name="priority"' in html

    def test_sections_have_dividers_except_last(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            sections={
                "First": ["title"],
                "Second": ["description"],
                "Last": ["priority"],
            },
        )
        html = get_form_html(form)
        # First and second sections should have border-b divider
        # Last section should not
        assert "border-b" in html
        # Count occurrences: 2 sections with border, 1 without
        assert html.count("border-b border-base-200") == 2

    def test_sections_with_exclude_fields(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            sections={
                "Info": ["title", "description", "priority"],
            },
            exclude_fields=["description"],
        )
        html = get_form_html(form)
        assert 'name="title"' in html
        assert 'name="description"' not in html
        assert 'name="priority"' in html

    def test_sections_skip_nonexistent_fields(self):
        """Fields in sections that don't exist on the model are silently skipped."""
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            sections={
                "Info": ["title", "nonexistent_field"],
            },
        )
        html = get_form_html(form)
        assert 'name="title"' in html
        assert "nonexistent_field" not in html

    def test_sections_with_values(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            sections={
                "Info": ["title", "priority"],
            },
            values={"title": "Prefilled", "priority": Priority.HIGH},
        )
        html = get_form_html(form)
        assert 'value="Prefilled"' in html
        assert 'value="high" selected' in html

    def test_sections_ignore_include_fields(self):
        """When sections is provided, include_fields is ignored."""
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            sections={"Info": ["title", "description"]},
            include_fields=["priority"],  # Should be ignored
        )
        html = get_form_html(form)
        assert 'name="title"' in html
        assert 'name="description"' in html


# ============================================================================
# Tests: help_texts
# ============================================================================


class TestHelpTexts:
    """Test per-field help text."""

    def test_help_text_rendered(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["title"],
            help_texts={"title": "Enter a clear, actionable title"},
        )
        html = get_form_html(form)
        assert "Enter a clear, actionable title" in html

    def test_no_help_text_by_default(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["title"],
        )
        html = get_form_html(form)
        assert "text-base-content/70" not in html or "Enter a clear" not in html

    def test_help_text_in_sections(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            sections={"Info": ["title", "description"]},
            help_texts={"description": "Be as detailed as possible"},
        )
        html = get_form_html(form)
        assert "Be as detailed as possible" in html


# ============================================================================
# Tests: hidden_fields
# ============================================================================


class TestHiddenFields:
    """Test hidden input generation."""

    def test_hidden_field_rendered(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["title"],
            hidden_fields={"entity_uid": "task_abc123"},
        )
        html = get_form_html(form)
        assert 'type="hidden"' in html
        assert 'name="entity_uid"' in html
        assert 'value="task_abc123"' in html

    def test_multiple_hidden_fields(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["title"],
            hidden_fields={"uid": "task_1", "version": "2"},
        )
        html = get_form_html(form)
        assert 'name="uid"' in html
        assert 'name="version"' in html


# ============================================================================
# Tests: as_fragment
# ============================================================================


class TestAsFragment:
    """Test fragment mode for article embedding."""

    def test_fragment_returns_div_not_form(self):
        result = FormGenerator.from_model(
            SampleCreateRequest,
            include_fields=["title", "description"],
            as_fragment=True,
        )
        html = get_form_html(result)
        # Should be a div, not a form
        assert html.startswith("<div")
        assert "<form" not in html

    def test_fragment_has_no_submit_button(self):
        result = FormGenerator.from_model(
            SampleCreateRequest,
            include_fields=["title"],
            as_fragment=True,
        )
        html = get_form_html(result)
        assert 'type="submit"' not in html

    def test_fragment_still_has_fields(self):
        result = FormGenerator.from_model(
            SampleCreateRequest,
            include_fields=["title", "priority"],
            as_fragment=True,
        )
        html = get_form_html(result)
        assert 'name="title"' in html
        assert 'name="priority"' in html

    def test_fragment_with_values(self):
        result = FormGenerator.from_model(
            SampleCreateRequest,
            include_fields=["title"],
            values={"title": "Embedded"},
            as_fragment=True,
        )
        html = get_form_html(result)
        assert 'value="Embedded"' in html

    def test_fragment_with_hidden_fields(self):
        result = FormGenerator.from_model(
            SampleCreateRequest,
            include_fields=["title"],
            hidden_fields={"exercise_uid": "ex_123"},
            as_fragment=True,
        )
        html = get_form_html(result)
        assert 'type="hidden"' in html
        assert 'value="ex_123"' in html

    def test_fragment_with_form_attrs(self):
        result = FormGenerator.from_model(
            SampleCreateRequest,
            include_fields=["title"],
            form_attrs={"id": "exercise-fields"},
            as_fragment=True,
        )
        html = get_form_html(result)
        assert 'id="exercise-fields"' in html


# ============================================================================
# Tests: custom_widgets wrapping
# ============================================================================


class TestCustomWidgets:
    """Test that custom widgets are wrapped with label and error display."""

    def test_custom_widget_gets_label(self):
        from ui.forms import Textarea

        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["description"],
            custom_widgets={
                "description": Textarea(name="description", rows=8, placeholder="Custom..."),
            },
        )
        html = get_form_html(form)
        # Should have the label from the model's field description
        assert "Description" in html
        # Should have the custom textarea
        assert 'rows="8"' in html
        assert "Custom..." in html
        # Should have error display div
        assert 'id="description-error"' in html

    def test_custom_widget_with_help_text(self):
        from ui.forms import Input

        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["title"],
            custom_widgets={"title": Input(type="text", name="title")},
            help_texts={"title": "Custom help for title"},
        )
        html = get_form_html(form)
        assert "Custom help for title" in html


# ============================================================================
# Tests: DaisyUI wrapper integration
# ============================================================================


class TestDaisyUIIntegration:
    """Test that generated widgets use DaisyUI variant classes."""

    def test_text_input_has_daisyui_classes(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["title"],
        )
        html = get_form_html(form)
        assert "input-bordered" in html

    def test_select_has_daisyui_classes(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["priority"],
        )
        html = get_form_html(form)
        assert "select-bordered" in html

    def test_checkbox_has_daisyui_classes(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["is_active"],
        )
        html = get_form_html(form)
        assert "checkbox" in html

    def test_textarea_has_daisyui_classes(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["description"],
        )
        html = get_form_html(form)
        assert "textarea-bordered" in html


# ============================================================================
# Tests: Alpine.js integration
# ============================================================================


class TestAlpineIntegration:
    """Test Alpine.js formValidator defaults and overrides."""

    def test_default_alpine_validator(self):
        form = FormGenerator.from_model(
            SampleCreateRequest, action="/test", include_fields=["title"]
        )
        html = get_form_html(form)
        assert 'x-data="formValidator"' in html

    def test_alpine_override_via_form_attrs(self):
        form = FormGenerator.from_model(
            SampleCreateRequest,
            action="/test",
            include_fields=["title"],
            form_attrs={"x-data": "customComponent"},
        )
        html = get_form_html(form)
        assert 'x-data="customComponent"' in html
        assert "formValidator" not in html

    def test_fragment_mode_no_alpine(self):
        result = FormGenerator.from_model(
            SampleCreateRequest,
            include_fields=["title"],
            as_fragment=True,
        )
        html = get_form_html(result)
        assert "formValidator" not in html
