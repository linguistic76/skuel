"""Unit tests for the Neo4j property-bag typed extractors (arg-type PR D).

These helpers are the single narrowing seam between the loosely-typed
``Neo4jProperties`` mapping the driver returns and the concrete types service
consumers expect. The contract under test: narrow on a correctly-typed value,
fall back to the default on missing/None, and raise ``TypeError`` (a member of
``DATA_CONVERSION_EXCEPTIONS``) on a present-but-wrong-type value so schema
drift fails fast at the read boundary.
"""

import pytest

from core.models.type_hints import UserUID
from core.utils.neo4j_props import neo4j_str, neo4j_str_list, neo4j_user_uid


class TestNeo4jStr:
    def test_returns_string_value(self) -> None:
        assert neo4j_str({"k": "hello"}, "k") == "hello"

    def test_default_on_missing(self) -> None:
        assert neo4j_str({}, "k", "fallback") == "fallback"

    def test_default_on_none(self) -> None:
        assert neo4j_str({"k": None}, "k", "fallback") == "fallback"

    def test_raises_on_missing_without_default(self) -> None:
        with pytest.raises(TypeError):
            neo4j_str({}, "k")

    def test_raises_on_wrong_type(self) -> None:
        with pytest.raises(TypeError):
            neo4j_str({"k": 123}, "k", "")


class TestNeo4jUserUid:
    def test_wraps_canonical_uid(self) -> None:
        result = neo4j_user_uid({"k": "user_alice"}, "k")
        assert result == UserUID("user_alice")

    def test_raises_on_non_canonical_uid(self) -> None:
        with pytest.raises(ValueError):
            neo4j_user_uid({"k": "alice"}, "k")

    def test_raises_on_wrong_type(self) -> None:
        with pytest.raises(TypeError):
            neo4j_user_uid({"k": 5}, "k")


class TestNeo4jStrList:
    def test_returns_list_of_strings(self) -> None:
        assert neo4j_str_list({"k": ["a", "b"]}, "k") == ["a", "b"]

    def test_empty_on_missing(self) -> None:
        assert neo4j_str_list({}, "k") == []

    def test_empty_on_none(self) -> None:
        assert neo4j_str_list({"k": None}, "k") == []

    def test_raises_on_non_list(self) -> None:
        with pytest.raises(TypeError):
            neo4j_str_list({"k": "scalar"}, "k")

    def test_raises_on_non_string_element(self) -> None:
        with pytest.raises(TypeError):
            neo4j_str_list({"k": ["a", 2]}, "k")
