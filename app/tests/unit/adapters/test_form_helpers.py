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
- parse_body() — the Content-Type dispatch between the JSON and form readers
"""

from datetime import date, datetime, time
from enum import Enum
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import BaseModel

from adapters.inbound.form_helpers import (
    ActivityFilters,
    PrincipleFilters,
    TaskFilters,
    _list_field_names,
    _split_list_input,
    parse_activity_filters,
    parse_body,
    parse_date_safe,
    parse_datetime_safe,
    parse_enum_safe,
    parse_form_body,
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


# ============================================================================
# _list_field_names / _split_list_input / parse_form_body list handling
# ============================================================================


class _SchemaWithLists(BaseModel):
    title: str
    tags: list[str] = []
    aliases: list[str] | None = None
    count: int = 0


class TestListFieldNames:
    def test_detects_plain_and_optional_lists(self):
        assert _list_field_names(_SchemaWithLists) == {"tags", "aliases"}

    def test_ignores_non_list_fields(self):
        names = _list_field_names(_SchemaWithLists)
        assert "title" not in names and "count" not in names


class TestSplitListInput:
    def test_splits_on_newlines(self):
        assert _split_list_input("a\nb\n c ") == ["a", "b", "c"]

    def test_a_single_line_with_commas_is_one_item(self):
        """The textarea renders a stored list one item per line, so a comma inside
        an item is content — it must round-trip through an unrelated save intact."""
        assert _split_list_input("Use warm, supportive language") == [
            "Use warm, supportive language"
        ]

    def test_empty_returns_empty_list(self):
        assert _split_list_input("") == []

    def test_whitespace_only_items_dropped(self):
        assert _split_list_input("a\n\n  \nb") == ["a", "b"]


@pytest.mark.asyncio
class TestParseFormBodyListFields:
    async def _post(self, fields: dict[str, str]) -> _SchemaWithLists:
        request = Mock()
        request.form = AsyncMock(return_value=fields)
        result = await parse_form_body(request, _SchemaWithLists)
        assert not result.is_error, result.expect_error()
        return result.value

    async def test_textarea_newlines_become_list(self):
        model = await self._post({"title": "T", "tags": "a\nb\nc"})
        assert model.tags == ["a", "b", "c"]

    async def test_optional_list_splits_on_lines_only(self):
        model = await self._post({"title": "T", "aliases": "x, y\nz"})
        assert model.aliases == ["x, y", "z"]

    async def test_empty_list_field_yields_empty_list(self):
        model = await self._post({"title": "T", "tags": ""})
        assert model.tags == []

    async def test_non_list_field_unchanged(self):
        model = await self._post({"title": "Hello", "count": "5"})
        assert model.title == "Hello"
        assert model.count == 5


# ============================================================================
# parse_body — one door, both encodings
# ============================================================================


class _WriteSchema(BaseModel):
    name: str
    notes: list[str] | None = None
    domain: str | None = None


class _OptionalSchema(BaseModel):
    reason: str = ""


def _request(content_type: str | None, *, body: bytes = b"x", form=None, json=None) -> Mock:
    """A request whose readers answer what a real one would for that Content-Type."""
    request = Mock()
    request.headers = {"content-type": content_type} if content_type is not None else {}
    request.body = AsyncMock(return_value=body)
    request.form = AsyncMock(return_value=form if form is not None else {})
    request.json = AsyncMock(return_value=json)
    return request


@pytest.mark.asyncio
class TestParseBody:
    async def test_json_media_type_reads_json(self):
        request = _request("application/json", json={"name": "T", "notes": ["a", "b"]})
        result = await parse_body(request, _WriteSchema)
        assert result.value.notes == ["a", "b"]
        request.form.assert_not_awaited()

    async def test_charset_suffix_is_still_json(self):
        request = _request("application/json; charset=utf-8", json={"name": "T"})
        result = await parse_body(request, _WriteSchema)
        assert result.value.name == "T"

    @pytest.mark.parametrize(
        "content_type",
        ["application/x-www-form-urlencoded", "multipart/form-data; boundary=xyz"],
    )
    async def test_form_media_types_read_the_form(self, content_type: str):
        """The form reader's conventions come with it: textarea → list, "" → None."""
        request = _request(content_type, form={"name": "T", "notes": "a\nb", "domain": ""})
        result = await parse_body(request, _WriteSchema)
        assert result.value.notes == ["a", "b"]
        assert result.value.domain is None
        request.json.assert_not_awaited()

    async def test_no_content_type_reads_json(self):
        """An API client that sends JSON without naming it is still a JSON client."""
        request = _request(None, json={"name": "T"})
        result = await parse_body(request, _WriteSchema)
        assert result.value.name == "T"

    @pytest.mark.parametrize("content_type", [None, "application/json"])
    async def test_empty_body_is_the_empty_field_set(self, content_type: str | None):
        """A POST with nothing to say, typed or not; the schema decides whether nothing
        is enough — an optional body is optional for a client whose default type is JSON."""
        request = _request(content_type, body=b"")
        assert (await parse_body(request, _OptionalSchema)).value.reason == ""
        rejected = await parse_body(request, _WriteSchema)
        assert rejected.is_error and "name" in rejected.expect_error().message
        request.json.assert_not_awaited()

    async def test_empty_urlencoded_body_is_the_empty_form(self):
        """What a bare htmx button posts — Content-Type set, nothing in it."""
        request = _request("application/x-www-form-urlencoded", body=b"", form={})
        assert (await parse_body(request, _OptionalSchema)).value.reason == ""

    async def test_form_rejection_names_the_field(self):
        request = _request("application/x-www-form-urlencoded", form={"notes": "a"})
        result = await parse_body(request, _WriteSchema)
        assert result.is_error and "name" in result.expect_error().message
