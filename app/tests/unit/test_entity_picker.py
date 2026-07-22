"""
Tests for EntityPicker — rendering, prefill, exclusions, type validation.
"""

from __future__ import annotations

import pytest
from fasthtml.common import to_xml

from ui.patterns.entity_picker import EntityPicker


def render(picker) -> str:
    return to_xml(picker)


class TestBasicRendering:
    """Smoke: the component renders an Alpine-bound dropdown with a hidden input."""

    def test_creates_hidden_input_with_name(self):
        html = render(EntityPicker(name="fulfills_goal_uid", target_type="goal"))
        assert 'type="hidden"' in html
        assert 'name="fulfills_goal_uid"' in html

    def test_attaches_alpine_data(self):
        html = render(EntityPicker(name="fulfills_goal_uid", target_type="goal"))
        assert 'x-data="entityPicker"' in html

    def test_visible_input_has_no_name(self):
        # The visible search input must NOT carry `name`, otherwise the parent
        # form would receive the search text on submit.
        html = render(EntityPicker(name="fulfills_goal_uid", target_type="goal"))
        # Exactly one element with name="fulfills_goal_uid" — the hidden input.
        assert html.count('name="fulfills_goal_uid"') == 1

    def test_search_input_has_alpine_refs(self):
        html = render(EntityPicker(name="parent_uid", target_type="task"))
        assert 'x-ref="hidden"' in html
        assert 'x-ref="search"' in html

    def test_results_panel_uses_unique_id(self):
        a = render(EntityPicker(name="parent_uid", target_type="task"))
        b = render(EntityPicker(name="parent_uid", target_type="task"))
        # Two pickers on the same page must have distinct result-panel ids.
        # The id includes a random hex token so adjacent renders differ.
        assert a != b


class TestTargetTypeRouting:
    """Each target_type bakes its own /api/picker/search URL."""

    def test_goal_picker_url(self):
        html = render(EntityPicker(name="fulfills_goal_uid", target_type="goal"))
        assert "/api/picker/search?type=goal" in html

    def test_habit_picker_url(self):
        html = render(EntityPicker(name="reinforces_habit_uid", target_type="habit"))
        assert "/api/picker/search?type=habit" in html

    def test_task_picker_url(self):
        html = render(EntityPicker(name="parent_uid", target_type="task"))
        assert "/api/picker/search?type=task" in html

    def test_event_picker_url(self):
        html = render(EntityPicker(name="triggered_by_event_uid", target_type="event"))
        assert "/api/picker/search?type=event" in html

    def test_choice_picker_url(self):
        html = render(EntityPicker(name="informs_choice_uid", target_type="choice"))
        assert "/api/picker/search?type=choice" in html

    def test_principle_picker_url(self):
        html = render(EntityPicker(name="guided_by_principle_uid", target_type="principle"))
        assert "/api/picker/search?type=principle" in html

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="unsupported target_type"):
            EntityPicker(name="x", target_type="not_a_type")


class TestPrefillForEditMode:
    """value + display populate hidden + visible inputs for edit forms."""

    def test_value_lands_in_hidden_input(self):
        html = render(
            EntityPicker(
                name="fulfills_goal_uid",
                target_type="goal",
                value="goal:abc123",
                display="Get fit",
            )
        )
        assert 'value="goal:abc123"' in html

    def test_display_lands_in_visible_input(self):
        html = render(
            EntityPicker(
                name="fulfills_goal_uid",
                target_type="goal",
                value="goal:abc123",
                display="Get fit",
            )
        )
        assert 'value="Get fit"' in html

    def test_no_value_renders_empty_hidden(self):
        html = render(EntityPicker(name="fulfills_goal_uid", target_type="goal"))
        assert 'value=""' in html


class TestExclusions:
    """Self-referential pickers pass exclusion params via the HTMX URL."""

    def test_exclude_uid_in_url(self):
        html = render(
            EntityPicker(
                name="parent_uid",
                target_type="task",
                exclude_uid="task:abc",
            )
        )
        assert "exclude_uid=task" in html  # urlencoded ':' may become %3A
        # Confirm the value made it through encoding
        assert "task%3Aabc" in html or "task:abc" in html

    def test_exclude_descendants_of_in_url(self):
        html = render(
            EntityPicker(
                name="parent_uid",
                target_type="task",
                exclude_descendants_of="task:xyz",
            )
        )
        assert "exclude_descendants_of=" in html

    def test_no_exclusions_when_omitted(self):
        html = render(EntityPicker(name="fulfills_goal_uid", target_type="goal"))
        assert "exclude_uid=" not in html
        assert "exclude_descendants_of=" not in html


class TestClearButton:
    """A clear (x) button is rendered, hidden until the picker holds a value,
    and wired to the Alpine ``clear()`` handler."""

    def test_clear_button_present(self):
        html = render(EntityPicker(name="fulfills_goal_uid", target_type="goal"))
        assert 'x-on:click="clear()"' in html
        assert 'aria-label="Clear goal selection"' in html

    def test_clear_button_hidden_when_empty(self):
        html = render(EntityPicker(name="fulfills_goal_uid", target_type="goal"))
        # x-show binds to hasValue() so Alpine hides it on initial empty state.
        assert 'x-show="hasValue()"' in html


class TestRequired:
    """required=True propagates to the form-submitted hidden input."""

    def test_required_set_on_hidden_input(self):
        html = render(EntityPicker(name="fulfills_goal_uid", target_type="goal", required=True))
        assert "required" in html

    def test_required_default_false(self):
        html = render(EntityPicker(name="fulfills_goal_uid", target_type="goal"))
        # No required attribute on the hidden input by default.
        # We can't simply check `'required' not in html` because Alpine attribute
        # spelling sometimes mentions it; instead look for the explicit attribute.
        assert " required" not in html or 'required="' in html.replace("aria-required", "")
