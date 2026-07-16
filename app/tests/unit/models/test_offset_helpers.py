"""Tests for the shared RelativeOffset JSON helpers (used by all template DTOs)."""

from __future__ import annotations

import json

from core.models.templates import RelativeOffset
from core.models.templates.offset_helpers import jsonable_to_offset, offset_to_jsonable


class TestOffsetToJsonable:
    def test_none_passes_through(self):
        assert offset_to_jsonable(None) is None

    def test_renders_all_components(self):
        assert offset_to_jsonable(RelativeOffset(days=7, hours=2, minutes=30)) == {
            "days": 7,
            "hours": 2,
            "minutes": 30,
        }


class TestJsonableToOffset:
    def test_none_passes_through(self):
        assert jsonable_to_offset(None) is None

    def test_relative_offset_passes_through(self):
        offset = RelativeOffset(days=3)
        assert jsonable_to_offset(offset) is offset

    def test_dict_round_trip(self):
        offset = RelativeOffset(days=7, hours=2, minutes=30)
        assert jsonable_to_offset(offset_to_jsonable(offset)) == offset

    def test_json_string_round_trip(self):
        offset = RelativeOffset(days=1, hours=4)
        assert jsonable_to_offset(json.dumps(offset_to_jsonable(offset))) == offset

    def test_missing_keys_default_to_zero(self):
        assert jsonable_to_offset({"days": 5}) == RelativeOffset(days=5)

    def test_null_components_default_to_zero(self):
        assert jsonable_to_offset({"days": None, "hours": 2}) == RelativeOffset(hours=2)

    def test_garbage_string_returns_none(self):
        assert jsonable_to_offset("not json at all") is None

    def test_non_dict_json_returns_none(self):
        assert jsonable_to_offset("[1, 2, 3]") is None

    def test_non_dict_object_returns_none(self):
        assert jsonable_to_offset(42) is None
