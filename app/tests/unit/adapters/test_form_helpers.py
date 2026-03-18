"""
Unit tests for shared form parsing utilities in form_helpers.py.

Tests cover:
- parse_enum_safe() — enum string parsing with fallback
- parse_date_safe() — ISO date parsing with None fallback
- parse_time_safe() — ISO time parsing with None fallback
- parse_datetime_safe() — ISO datetime parsing with None fallback
- ActivityFilters — shared 2-field filter dataclass
- parse_activity_filters() — request query param extraction
"""

from datetime import date, datetime, time
from enum import Enum
from unittest.mock import Mock

from adapters.inbound.form_helpers import (
    ActivityFilters,
    parse_activity_filters,
    parse_date_safe,
    parse_datetime_safe,
    parse_enum_safe,
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
