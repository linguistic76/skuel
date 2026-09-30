"""
Unit tests for the form data helpers in form_helpers.py.

Tests cover:
- safe_form_string() / safe_form_int() / safe_form_bool() — one raw form field,
  typed ``str | UploadFile | None``, read with a default
- _list_field_names() / _split_list_input() — the textarea-to-list mapping
- parse_form_body() — list fields split from the textarea string
- parse_body() — the Content-Type dispatch between the JSON and form readers
"""

import io
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from adapters.inbound.form_helpers import (
    _list_field_names,
    _split_list_input,
    parse_body,
    parse_form_body,
    safe_form_bool,
    safe_form_int,
    safe_form_string,
)


def _upload() -> UploadFile:
    return UploadFile(file=io.BytesIO(b"content"), filename="notes.md")


# ============================================================================
# safe_form_string / safe_form_int / safe_form_bool — one raw field
# ============================================================================


class TestSafeFormString:
    def test_valid_string_is_returned(self):
        assert safe_form_string("mike") == "mike"

    def test_surrounding_whitespace_is_stripped(self):
        assert safe_form_string("  mike@example.com\n") == "mike@example.com"

    def test_whitespace_only_is_the_empty_string_not_the_default(self):
        assert safe_form_string("   ", default="fallback") == ""

    def test_none_is_the_default(self):
        assert safe_form_string(None) == ""
        assert safe_form_string(None, default="personal") == "personal"

    def test_an_upload_is_the_default(self):
        assert safe_form_string(_upload(), default="personal") == "personal"


class TestSafeFormInt:
    def test_integer_string_is_parsed_after_stripping(self):
        assert safe_form_int(" 45 ") == 45

    def test_unparseable_string_is_the_default(self):
        assert safe_form_int("forty", default=60) == 60
        assert safe_form_int("", default=60) == 60

    def test_none_and_upload_are_the_default(self):
        assert safe_form_int(None, default=15) == 15
        assert safe_form_int(_upload(), default=15) == 15


class TestSafeFormBool:
    @pytest.mark.parametrize("value", ["true", "1", "yes", "on", " ON ", "True"])
    def test_truthy_spellings_are_true(self, value: str):
        assert safe_form_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", ""])
    def test_any_other_string_is_false_even_with_a_true_default(self, value: str):
        assert safe_form_bool(value, default=True) is False

    def test_none_and_upload_are_the_default(self):
        assert safe_form_bool(None, default=True) is True
        assert safe_form_bool(_upload()) is False


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
