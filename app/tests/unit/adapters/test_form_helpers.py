"""
Unit tests for shared form parsing utilities in form_helpers.py.

Tests cover:
- parse_enum_safe() — enum string parsing with fallback
- parse_date_safe() — ISO date parsing with None fallback
- parse_time_safe() — ISO time parsing with None fallback
- parse_datetime_safe() — ISO datetime parsing with None fallback
- ActivityFilters — shared 2-field filter dataclass
- parse_activity_filters() — request query param extraction
- TaskFilters — task-specific 5-field filter subclass
- parse_task_filters() — task filter param extraction
- PrincipleFilters — principle-specific 4-field filter subclass
- parse_principle_filters() — principle filter param extraction
"""

from datetime import date, datetime, time
from enum import Enum
from unittest.mock import Mock

from adapters.inbound.form_helpers import (
    ActivityFilters,
    PrincipleFilters,
    TaskFilters,
    parse_activity_filters,
    parse_date_safe,
    parse_datetime_safe,
    parse_enum_safe,
    parse_principle_filters,
    parse_task_filters,
    parse_time_safe,
)


# Test enum for parse_enum_safe tests
class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


# ============================================================================
# parse_enum_safe
# ============================================================================


class TestParseEnumSafe:
    def test_valid_value(self):
        assert parse_enum_safe(Color, "red", Color.BLUE) == Color.RED

    def test_invalid_value(self):
        assert parse_enum_safe(Color, "purple", Color.BLUE) == Color.BLUE

    def test_none_value(self):
        assert parse_enum_safe(Color, None, Color.GREEN) == Color.GREEN

    def test_empty_string(self):
        assert parse_enum_safe(Color, "", Color.RED) == Color.RED


# ============================================================================
# parse_date_safe
# ============================================================================


class TestParseDateSafe:
    def test_valid_date(self):
        assert parse_date_safe("2026-03-15") == date(2026, 3, 15)

    def test_invalid_date(self):
        assert parse_date_safe("not-a-date") is None

    def test_none(self):
        assert parse_date_safe(None) is None

    def test_empty_string(self):
        assert parse_date_safe("") is None


# ============================================================================
# parse_time_safe
# ============================================================================


class TestParseTimeSafe:
    def test_valid_time(self):
        assert parse_time_safe("14:30") == time(14, 30)

    def test_valid_time_with_seconds(self):
        assert parse_time_safe("14:30:45") == time(14, 30, 45)

    def test_invalid_time(self):
        assert parse_time_safe("not-a-time") is None

    def test_none(self):
        assert parse_time_safe(None) is None

    def test_empty_string(self):
        assert parse_time_safe("") is None


# ============================================================================
# parse_datetime_safe
# ============================================================================


class TestParseDatetimeSafe:
    def test_valid_datetime(self):
        assert parse_datetime_safe("2026-03-15T14:30:00") == datetime(2026, 3, 15, 14, 30, 0)

    def test_valid_date_only(self):
        """datetime.fromisoformat accepts date-only strings."""
        assert parse_datetime_safe("2026-03-15") == datetime(2026, 3, 15, 0, 0, 0)

    def test_invalid_datetime(self):
        assert parse_datetime_safe("not-a-datetime") is None

    def test_none(self):
        assert parse_datetime_safe(None) is None

    def test_empty_string(self):
        assert parse_datetime_safe("") is None


# ============================================================================
# ActivityFilters
# ============================================================================


class TestActivityFilters:
    def test_to_dict(self):
        filters = ActivityFilters(status="active", sort_by="created_at")
        result = filters.to_dict()
        assert result == {"status": "active", "sort_by": "created_at"}


# ============================================================================
# parse_activity_filters
# ============================================================================


class TestParseActivityFilters:
    def test_all_params(self):
        request = Mock()
        request.query_params = {"filter_status": "completed", "sort_by": "name"}
        result = parse_activity_filters(request)
        assert result.status == "completed"
        assert result.sort_by == "name"

    def test_defaults(self):
        request = Mock()
        request.query_params = {}
        result = parse_activity_filters(
            request, default_status="pending", default_sort_by="deadline"
        )
        assert result.status == "pending"
        assert result.sort_by == "deadline"

    def test_partial_params(self):
        request = Mock()
        request.query_params = {"filter_status": "archived"}
        result = parse_activity_filters(request, default_sort_by="updated_at")
        assert result.status == "archived"
        assert result.sort_by == "updated_at"

    def test_default_defaults(self):
        """Without explicit defaults, uses 'active' and 'created_at'."""
        request = Mock()
        request.query_params = {}
        result = parse_activity_filters(request)
        assert result.status == "active"
        assert result.sort_by == "created_at"


# ============================================================================
# TaskFilters
# ============================================================================


class TestTaskFilters:
    def test_inherits_activity_filters(self):
        assert issubclass(TaskFilters, ActivityFilters)

    def test_to_dict_includes_all_fields(self):
        filters = TaskFilters(
            status="active",
            sort_by="due_date",
            project="backend",
            assignee="mike",
            due_filter="overdue",
        )
        result = filters.to_dict()
        assert result == {
            "status": "active",
            "sort_by": "due_date",
            "project": "backend",
            "assignee": "mike",
            "due": "overdue",
        }

    def test_defaults(self):
        filters = TaskFilters(status="active", sort_by="due_date")
        assert filters.project == ""
        assert filters.assignee == ""
        assert filters.due_filter == ""

    def test_to_dict_empty_defaults(self):
        filters = TaskFilters(status="active", sort_by="due_date")
        result = filters.to_dict()
        assert result["project"] == ""
        assert result["assignee"] == ""
        assert result["due"] == ""


# ============================================================================
# parse_task_filters
# ============================================================================


class TestParseTaskFilters:
    def test_all_params(self):
        request = Mock()
        request.query_params = {
            "filter_status": "completed",
            "sort_by": "title",
            "filter_project": "api",
            "filter_assignee": "alice",
            "filter_due": "this_week",
        }
        result = parse_task_filters(request)
        assert result.status == "completed"
        assert result.sort_by == "title"
        assert result.project == "api"
        assert result.assignee == "alice"
        assert result.due_filter == "this_week"

    def test_defaults(self):
        request = Mock()
        request.query_params = {}
        result = parse_task_filters(request)
        assert result.status == "active"
        assert result.sort_by == "due_date"
        assert result.project == ""
        assert result.assignee == ""
        assert result.due_filter == ""

    def test_returns_task_filters_type(self):
        request = Mock()
        request.query_params = {}
        result = parse_task_filters(request)
        assert isinstance(result, TaskFilters)
        assert isinstance(result, ActivityFilters)


# ============================================================================
# PrincipleFilters
# ============================================================================


class TestPrincipleFilters:
    def test_inherits_activity_filters(self):
        assert issubclass(PrincipleFilters, ActivityFilters)

    def test_to_dict_includes_all_fields(self):
        filters = PrincipleFilters(
            status="active",
            sort_by="strength",
            category="spiritual",
            strength="core",
        )
        result = filters.to_dict()
        assert result == {
            "status": "active",
            "sort_by": "strength",
            "category": "spiritual",
            "strength": "core",
        }

    def test_defaults(self):
        filters = PrincipleFilters(status="all", sort_by="strength")
        assert filters.category == "all"
        assert filters.strength == "all"


# ============================================================================
# parse_principle_filters
# ============================================================================


class TestParsePrincipleFilters:
    def test_all_params(self):
        request = Mock()
        request.query_params = {
            "filter_status": "active",
            "sort_by": "title",
            "filter_category": "ethical",
            "filter_strength": "core",
        }
        result = parse_principle_filters(request)
        assert result.status == "active"
        assert result.sort_by == "title"
        assert result.category == "ethical"
        assert result.strength == "core"

    def test_defaults(self):
        request = Mock()
        request.query_params = {}
        result = parse_principle_filters(request)
        assert result.status == "all"
        assert result.sort_by == "strength"
        assert result.category == "all"
        assert result.strength == "all"

    def test_returns_principle_filters_type(self):
        request = Mock()
        request.query_params = {}
        result = parse_principle_filters(request)
        assert isinstance(result, PrincipleFilters)
        assert isinstance(result, ActivityFilters)
