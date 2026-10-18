"""The query-param readers in ``route_helpers``: one rule at every door.

Missing or blank is the default (required when no default is given); present but
malformed, or outside the domain bounds, is a validation error; only a cap clamps.
"""

from datetime import date
from enum import StrEnum

import pytest

from adapters.inbound.route_factories.route_helpers import (
    PaginationParams,
    parse_bool_param_strict,
    parse_csv_query_param,
    parse_date_param_strict,
    parse_enum_param_strict,
    parse_float_param_strict,
    parse_int_param_strict,
    parse_pagination_params,
    refuse_malformed,
    split_csv,
)
from core.utils.result_simplified import ErrorCategory, Result


def _refused(result: Result[object], field: str) -> None:
    assert result.is_error
    error = result.expect_error()
    assert error.category is ErrorCategory.VALIDATION
    assert error.details["field"] == field


class TestParseIntParamStrict:
    def test_reads_text_and_numbers(self) -> None:
        assert parse_int_param_strict("50", "limit", default=10).value == 50
        assert parse_int_param_strict(42, "limit", default=10).value == 42

    @pytest.mark.parametrize("missing", [None, "", "   "])
    def test_missing_or_blank_is_the_default(self, missing: object) -> None:
        assert parse_int_param_strict(missing, "limit", default=10).value == 10

    @pytest.mark.parametrize("missing", [None, ""])
    def test_missing_with_no_default_is_required(self, missing: object) -> None:
        result = parse_int_param_strict(missing, "month", 1, 12)
        _refused(result, "month")
        assert "required" in result.expect_error().message

    def test_a_none_default_reads_as_absent(self) -> None:
        assert parse_int_param_strict(None, "year", default=None).value is None

    @pytest.mark.parametrize("bad", ["abc", "3.14", "1e3", True, 2.5])
    def test_malformed_is_refused(self, bad: object) -> None:
        _refused(parse_int_param_strict(bad, "limit", default=10), "limit")

    @pytest.mark.parametrize(
        ("sent", "low", "high"), [("0", 1, 12), ("13", 1, 12), ("-1", 0, None)]
    )
    def test_outside_the_bounds_is_refused(self, sent: str, low: int, high: int | None) -> None:
        _refused(parse_int_param_strict(sent, "n", low, high, default=1), "n")

    @pytest.mark.parametrize("edge", ["1", "12"])
    def test_the_bounds_are_inclusive(self, edge: str) -> None:
        assert parse_int_param_strict(edge, "month", 1, 12).value == int(edge)

    def test_above_the_cap_is_the_cap(self) -> None:
        assert parse_int_param_strict("10000", "limit", 1, default=50, cap=500).value == 500
        assert parse_int_param_strict("500", "limit", 1, default=50, cap=500).value == 500
        assert parse_int_param_strict("7", "limit", 1, default=50, cap=500).value == 7

    def test_the_cap_does_not_rescue_a_value_below_the_minimum(self) -> None:
        _refused(parse_int_param_strict("0", "limit", 1, default=50, cap=500), "limit")


class TestParseFloatParamStrict:
    def test_reads_text_and_numbers(self) -> None:
        assert parse_float_param_strict("0.25", "s", default=0.5).value == 0.25
        assert parse_float_param_strict(1, "s", default=0.5).value == 1.0

    @pytest.mark.parametrize("missing", [None, "", "  "])
    def test_missing_or_blank_is_the_default(self, missing: object) -> None:
        assert parse_float_param_strict(missing, "s", default=0.5).value == 0.5

    @pytest.mark.parametrize("bad", ["high", "nan", "inf", "-inf", True, [0.5]])
    def test_malformed_or_non_finite_is_refused(self, bad: object) -> None:
        _refused(parse_float_param_strict(bad, "s", default=0.5), "s")

    @pytest.mark.parametrize("bad", ["-0.1", "1.5"])
    def test_outside_the_bounds_is_refused(self, bad: str) -> None:
        _refused(parse_float_param_strict(bad, "s", default=0.5, min_val=0.0, max_val=1.0), "s")


class TestParseBoolParamStrict:
    @pytest.mark.parametrize("word", ["true", "TRUE", "1", "yes", "on", True])
    def test_true_words(self, word: object) -> None:
        assert parse_bool_param_strict(word, "flag", default=False).value is True

    @pytest.mark.parametrize("word", ["false", "False", "0", "no", "off", False])
    def test_false_words(self, word: object) -> None:
        assert parse_bool_param_strict(word, "flag", default=True).value is False

    @pytest.mark.parametrize("missing", [None, ""])
    def test_missing_or_blank_is_the_default(self, missing: object) -> None:
        assert parse_bool_param_strict(missing, "flag", default=True).value is True

    @pytest.mark.parametrize("bad", ["maybe", "2", "garbage"])
    def test_malformed_is_refused(self, bad: str) -> None:
        _refused(parse_bool_param_strict(bad, "flag", default=True), "flag")


class TestParseDateParamStrict:
    def test_reads_an_iso_date(self) -> None:
        assert parse_date_param_strict("2026-03-18", "d").value == date(2026, 3, 18)

    def test_missing_with_no_default_is_required(self) -> None:
        _refused(parse_date_param_strict(None, "d"), "d")
        _refused(parse_date_param_strict("", "d"), "d")

    def test_missing_with_a_default_is_the_default(self) -> None:
        fallback = date(2026, 1, 1)
        assert parse_date_param_strict(None, "d", default=fallback).value == fallback
        assert parse_date_param_strict("", "d", default=None).value is None

    @pytest.mark.parametrize("bad", ["not-a-date", "2026-13-01"])
    def test_malformed_is_refused_even_with_a_default(self, bad: str) -> None:
        _refused(parse_date_param_strict(bad, "d", default=None), "d")


class _Shade(StrEnum):
    LIGHT = "light"
    DARK = "dark"


class TestParseEnumParamStrict:
    def test_reads_a_member_by_its_value(self) -> None:
        assert parse_enum_param_strict("dark", "shade", _Shade).value is _Shade.DARK

    @pytest.mark.parametrize("missing", [None, "", "  "])
    def test_missing_or_blank_is_no_choice(self, missing: object) -> None:
        assert parse_enum_param_strict(missing, "shade", _Shade).value is None

    @pytest.mark.parametrize("bad", ["DARK", "dim", "LIGHT "])
    def test_a_word_outside_the_vocabulary_is_refused(self, bad: str) -> None:
        result = parse_enum_param_strict(bad, "shade", _Shade)
        _refused(result, "shade")
        assert result.expect_error().message == "shade must be one of: light, dark"


class TestParsePagination:
    def test_reads_both(self) -> None:
        result = parse_pagination_params({"limit": "25", "offset": "10"})
        assert result.value == PaginationParams(limit=25, offset=10)

    def test_missing_is_the_defaults(self) -> None:
        assert parse_pagination_params({}).value == PaginationParams(limit=50, offset=0)
        assert parse_pagination_params({}, default_limit=100).value.limit == 100

    def test_a_limit_above_the_cap_is_the_cap(self) -> None:
        assert parse_pagination_params({"limit": "9999"}, max_limit=500).value.limit == 500

    @pytest.mark.parametrize(
        ("params", "field"),
        [({"limit": "0"}, "limit"), ({"limit": "x"}, "limit"), ({"offset": "-5"}, "offset")],
    )
    def test_malformed_or_out_of_range_is_refused(self, params: dict[str, str], field: str) -> None:
        _refused(parse_pagination_params(params), field)


class TestCsv:
    def test_parse_csv_query_param(self) -> None:
        assert parse_csv_query_param({"tags": " a , b ,,c "}, "tags") == ["a", "b", "c"]
        assert parse_csv_query_param({}, "tags") == []
        assert parse_csv_query_param({"tags": ""}, "tags") == []

    def test_split_csv(self) -> None:
        assert split_csv("a,b,c") == ["a", "b", "c"]
        assert split_csv(" , , ") == []


def test_refuse_malformed_is_a_bare_plain_text_400() -> None:
    error = parse_int_param_strict("x", "offset", default=0).expect_error()

    response = refuse_malformed(error)

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/plain")
    assert "X-SKUEL-Refusal" not in response.headers
    assert b"offset" in response.body
