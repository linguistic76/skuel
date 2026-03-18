"""
Unit tests for UI form parser functions.

Tests import the actual module-level functions instead of copy-pasting definitions.

Tests cover:
- parse_task_filters() from form_helpers (TaskFilters subclass)
- parse_filters() in habits_ui, events_ui, choices_ui, goals_ui (shared ActivityFilters)
- parse_principle_filters() from form_helpers (PrincipleFilters subclass)
- parse_options_from_form() in choices_ui
- parse_calendar_params() in ui_helpers
"""

from datetime import date
from unittest.mock import Mock

# ============================================================================
# Tasks — TaskFilters subclass (5 fields, from form_helpers)
# ============================================================================


class TestTasksParseFilters:
    def test_all_params(self):
        from adapters.inbound.form_helpers import parse_task_filters

        request = Mock()
        request.query_params = {
            "filter_project": "ProjectX",
            "filter_assignee": "Alice",
            "filter_due": "overdue",
            "filter_status": "pending",
            "sort_by": "priority",
        }
        result = parse_task_filters(request)
        assert result.project == "ProjectX"
        assert result.assignee == "Alice"
        assert result.due_filter == "overdue"
        assert result.status == "pending"
        assert result.sort_by == "priority"

    def test_defaults(self):
        from adapters.inbound.form_helpers import parse_task_filters

        request = Mock()
        request.query_params = {}
        result = parse_task_filters(request)
        assert result.project == ""
        assert result.assignee == ""
        assert result.due_filter == ""
        assert result.status == "active"
        assert result.sort_by == "due_date"

    def test_partial_params(self):
        from adapters.inbound.form_helpers import parse_task_filters

        request = Mock()
        request.query_params = {
            "filter_project": "MyProject",
            "filter_status": "completed",
        }
        result = parse_task_filters(request)
        assert result.project == "MyProject"
        assert result.assignee == ""
        assert result.status == "completed"
        assert result.sort_by == "due_date"


# ============================================================================
# Goals — shared ActivityFilters with domain-specific defaults
# ============================================================================


class TestGoalsParseFilters:
    def test_all_params(self):
        from adapters.inbound.goals_ui import parse_filters

        request = Mock()
        request.query_params = {"filter_status": "completed", "sort_by": "name"}
        result = parse_filters(request)
        assert result.status == "completed"
        assert result.sort_by == "name"

    def test_defaults(self):
        from adapters.inbound.goals_ui import parse_filters

        request = Mock()
        request.query_params = {}
        result = parse_filters(request)
        assert result.status == "active"
        assert result.sort_by == "target_date"


# ============================================================================
# Habits — shared ActivityFilters with domain-specific defaults
# ============================================================================


class TestHabitsParseFilters:
    def test_all_params(self):
        from adapters.inbound.habits_ui import parse_filters

        request = Mock()
        request.query_params = {"filter_status": "completed", "sort_by": "name"}
        result = parse_filters(request)
        assert result.status == "completed"
        assert result.sort_by == "name"

    def test_defaults(self):
        from adapters.inbound.habits_ui import parse_filters

        request = Mock()
        request.query_params = {}
        result = parse_filters(request)
        assert result.status == "active"
        assert result.sort_by == "streak"


# ============================================================================
# Events — shared ActivityFilters with domain-specific defaults
# ============================================================================


class TestEventsParseFilters:
    def test_all_params(self):
        from adapters.inbound.events_ui import parse_filters

        request = Mock()
        request.query_params = {"filter_status": "completed", "sort_by": "title"}
        result = parse_filters(request)
        assert result.status == "completed"
        assert result.sort_by == "title"

    def test_defaults(self):
        from adapters.inbound.events_ui import parse_filters

        request = Mock()
        request.query_params = {}
        result = parse_filters(request)
        assert result.status == "scheduled"
        assert result.sort_by == "start_time"


# ============================================================================
# Choices — shared ActivityFilters with domain-specific defaults
# ============================================================================


class TestChoicesParseFilters:
    def test_all_params(self):
        from adapters.inbound.choices_ui import parse_filters

        request = Mock()
        request.query_params = {"filter_status": "decided", "sort_by": "title"}
        result = parse_filters(request)
        assert result.status == "decided"
        assert result.sort_by == "title"

    def test_defaults(self):
        from adapters.inbound.choices_ui import parse_filters

        request = Mock()
        request.query_params = {}
        result = parse_filters(request)
        assert result.status == "pending"
        assert result.sort_by == "deadline"


# ============================================================================
# Principles — PrincipleFilters subclass (4 fields, from form_helpers)
# ============================================================================


class TestPrinciplesParseFilters:
    def test_all_params(self):
        from adapters.inbound.form_helpers import parse_principle_filters

        request = Mock()
        request.query_params = {
            "filter_category": "health",
            "filter_strength": "core",
            "filter_status": "active",
            "sort_by": "name",
        }
        result = parse_principle_filters(request)
        assert result.category == "health"
        assert result.strength == "core"
        assert result.status == "active"
        assert result.sort_by == "name"

    def test_defaults(self):
        from adapters.inbound.form_helpers import parse_principle_filters

        request = Mock()
        request.query_params = {}
        result = parse_principle_filters(request)
        assert result.category == "all"
        assert result.strength == "all"
        assert result.status == "all"
        assert result.sort_by == "strength"


# ============================================================================
# Choice options parsing
# ============================================================================


class TestChoiceOptionsParser:
    def test_multiple_options(self):
        from adapters.inbound.choices_ui import parse_options_from_form

        form_data = {
            "options[0].title": "Option A",
            "options[0].description": "First option",
            "options[1].title": "Option B",
            "options[1].description": "Second option",
            "options[2].title": "Option C",
            "options[2].description": "Third option",
        }
        result = parse_options_from_form(form_data)
        assert len(result) == 3
        assert result[0] == {"title": "Option A", "description": "First option"}
        assert result[1] == {"title": "Option B", "description": "Second option"}
        assert result[2] == {"title": "Option C", "description": "Third option"}

    def test_empty(self):
        from adapters.inbound.choices_ui import parse_options_from_form

        assert parse_options_from_form({}) == []

    def test_skips_incomplete(self):
        from adapters.inbound.choices_ui import parse_options_from_form

        form_data = {
            "options[0].title": "Option A",
            "options[0].description": "First option",
            "options[1].title": "Option B",
            "options[1].description": "",  # Empty description
            "options[2].title": "",  # Empty title
            "options[2].description": "Third option",
            "options[3].title": "Option D",
            "options[3].description": "Fourth option",
        }
        result = parse_options_from_form(form_data)
        assert len(result) == 2
        assert result[0] == {"title": "Option A", "description": "First option"}
        assert result[1] == {"title": "Option D", "description": "Fourth option"}

    def test_stops_at_missing_index(self):
        from adapters.inbound.choices_ui import parse_options_from_form

        form_data = {
            "options[0].title": "Option A",
            "options[0].description": "First option",
            # Missing index 1
            "options[2].title": "Option C",
            "options[2].description": "Third option",
        }
        result = parse_options_from_form(form_data)
        assert len(result) == 1
        assert result[0] == {"title": "Option A", "description": "First option"}


# ============================================================================
# Calendar params parsing
# ============================================================================


class TestCalendarParams:
    def test_valid_date(self):
        from adapters.inbound.ui_helpers import parse_calendar_params

        request = Mock()
        request.query_params = {"calendar_view": "week", "date": "2026-03-15"}
        result = parse_calendar_params(request)
        assert result.calendar_view == "week"
        assert result.current_date == date(2026, 3, 15)

    def test_invalid_date(self):
        from adapters.inbound.ui_helpers import parse_calendar_params

        request = Mock()
        request.query_params = {"date": "not-a-date"}
        result = parse_calendar_params(request)
        assert result.calendar_view == "month"
        assert result.current_date == date.today()

    def test_missing_date(self):
        from adapters.inbound.ui_helpers import parse_calendar_params

        request = Mock()
        request.query_params = {}
        result = parse_calendar_params(request)
        assert result.calendar_view == "month"
        assert result.current_date == date.today()
