"""Tests for route_helpers query param parsing utilities."""

from datetime import date

from adapters.inbound.route_factories.route_helpers import (
    DateRangeParams,
    PaginationParams,
    parse_bool_query_param,
    parse_csv_query_param,
    parse_date_param_strict,
    parse_date_query_param,
    parse_date_range_params,
    parse_int_param_strict,
    parse_int_query_param,
    parse_pagination_params,
    split_csv,
)


class TestParseIntQueryParam:
    """parse_int_query_param: safe integer parsing with fallback and clamping."""

    # --- Happy path ---

    def test_normal_int_string(self):
        assert parse_int_query_param({"limit": "50"}, "limit", 10) == 50

    def test_numeric_int(self):
        """Value already an int (e.g. from Starlette query_params)."""
        assert parse_int_query_param({"limit": 42}, "limit", 10) == 42

    # --- Missing / blank ---

    def test_missing_key_returns_default(self):
        assert parse_int_query_param({}, "limit", 10) == 10

    def test_empty_string_returns_default(self):
        assert parse_int_query_param({"limit": ""}, "limit", 10) == 10

    def test_none_value_returns_default(self):
        assert parse_int_query_param({"limit": None}, "limit", 10) == 10

    # --- Invalid values ---

    def test_non_numeric_returns_default(self):
        assert parse_int_query_param({"limit": "abc"}, "limit", 10) == 10

    def test_float_string_returns_default(self):
        assert parse_int_query_param({"limit": "3.14"}, "limit", 10) == 10

    # --- Bounds clamping ---

    def test_minimum_clamps_up(self):
        assert parse_int_query_param({"limit": "0"}, "limit", 10, minimum=1) == 1

    def test_maximum_clamps_down(self):
        assert parse_int_query_param({"limit": "999"}, "limit", 10, maximum=100) == 100

    def test_within_bounds_unchanged(self):
        assert parse_int_query_param({"limit": "50"}, "limit", 10, minimum=1, maximum=100) == 50

    def test_both_bounds_clamp_low(self):
        assert parse_int_query_param({"limit": "-5"}, "limit", 10, minimum=0, maximum=100) == 0

    def test_both_bounds_clamp_high(self):
        assert parse_int_query_param({"limit": "200"}, "limit", 10, minimum=0, maximum=100) == 100

    # --- Edge cases ---

    def test_negative_value_allowed_without_minimum(self):
        assert parse_int_query_param({"offset": "-1"}, "offset", 0) == -1

    def test_zero_value(self):
        assert parse_int_query_param({"offset": "0"}, "offset", 5) == 0

    def test_mapping_protocol_starlette_query_params(self):
        """Works with Starlette QueryParams (implements Mapping)."""
        from starlette.datastructures import QueryParams

        params = QueryParams("limit=25&offset=5")
        assert parse_int_query_param(params, "limit", 10) == 25
        assert parse_int_query_param(params, "offset", 0) == 5
        assert parse_int_query_param(params, "missing", 99) == 99


class TestParseBoolQueryParam:
    """parse_bool_query_param: safe boolean parsing."""

    def test_true_variants(self):
        for val in ("true", "True", "TRUE", "1", "yes", "on"):
            assert parse_bool_query_param({"flag": val}, "flag") is True

    def test_false_variants(self):
        for val in ("false", "False", "0", "no", "off", "anything"):
            assert parse_bool_query_param({"flag": val}, "flag") is False

    def test_missing_returns_default_false(self):
        assert parse_bool_query_param({}, "flag") is False

    def test_missing_returns_default_true(self):
        assert parse_bool_query_param({}, "flag", default=True) is True

    def test_empty_string_returns_default(self):
        assert parse_bool_query_param({"flag": ""}, "flag", default=True) is True

    def test_none_returns_default(self):
        assert parse_bool_query_param({"flag": None}, "flag", default=True) is True


class TestParseDateQueryParam:
    """parse_date_query_param: safe ISO date parsing."""

    def test_valid_date(self):
        assert parse_date_query_param({"d": "2026-03-18"}, "d") == date(2026, 3, 18)

    def test_missing_returns_default(self):
        assert parse_date_query_param({}, "d") is None

    def test_missing_returns_custom_default(self):
        fallback = date(2026, 1, 1)
        assert parse_date_query_param({}, "d", fallback) == fallback

    def test_empty_string_returns_default(self):
        assert parse_date_query_param({"d": ""}, "d") is None

    def test_invalid_format_returns_default(self):
        assert parse_date_query_param({"d": "not-a-date"}, "d") is None

    def test_partial_date_returns_default(self):
        assert parse_date_query_param({"d": "2026-13-01"}, "d") is None


class TestParseCsvQueryParam:
    """parse_csv_query_param: comma-separated list from params."""

    def test_normal(self):
        assert parse_csv_query_param({"tags": "a,b,c"}, "tags") == ["a", "b", "c"]

    def test_whitespace_stripped(self):
        assert parse_csv_query_param({"tags": " a , b , c "}, "tags") == ["a", "b", "c"]

    def test_empty_segments_filtered(self):
        assert parse_csv_query_param({"tags": "a,,b,,"}, "tags") == ["a", "b"]

    def test_missing_key_returns_empty(self):
        assert parse_csv_query_param({}, "tags") == []

    def test_empty_string_returns_empty(self):
        assert parse_csv_query_param({"tags": ""}, "tags") == []

    def test_single_value(self):
        assert parse_csv_query_param({"tags": "solo"}, "tags") == ["solo"]


class TestSplitCsv:
    """split_csv: comma-separated string to list."""

    def test_normal(self):
        assert split_csv("a,b,c") == ["a", "b", "c"]

    def test_empty_string(self):
        assert split_csv("") == []

    def test_whitespace_only_segments(self):
        assert split_csv(" , , ") == []


class TestDateRangeParams:
    """parse_date_range_params: start/end date pair."""

    def test_both_present(self):
        result = parse_date_range_params(
            {"start_date": "2026-01-01", "end_date": "2026-01-31"}
        )
        assert result == DateRangeParams(date(2026, 1, 1), date(2026, 1, 31))

    def test_missing_both_returns_defaults(self):
        result = parse_date_range_params({})
        assert result == DateRangeParams(None, None)

    def test_custom_defaults(self):
        d = date(2026, 6, 1)
        result = parse_date_range_params({}, default_start=d, default_end=d)
        assert result == DateRangeParams(d, d)

    def test_invalid_date_returns_default(self):
        result = parse_date_range_params({"start_date": "bad", "end_date": "2026-01-31"})
        assert result.start_date is None
        assert result.end_date == date(2026, 1, 31)

    def test_custom_keys(self):
        result = parse_date_range_params(
            {"from": "2026-01-01", "to": "2026-12-31"},
            start_key="from",
            end_key="to",
        )
        assert result == DateRangeParams(date(2026, 1, 1), date(2026, 12, 31))


class TestPaginationParams:
    """parse_pagination_params: limit/offset pair."""

    def test_both_present(self):
        result = parse_pagination_params({"limit": "25", "offset": "10"})
        assert result == PaginationParams(25, 10)

    def test_defaults(self):
        result = parse_pagination_params({})
        assert result == PaginationParams(50, 0)

    def test_custom_defaults(self):
        result = parse_pagination_params({}, default_limit=100, default_offset=0)
        assert result == PaginationParams(100, 0)

    def test_limit_clamped_to_max(self):
        result = parse_pagination_params({"limit": "9999"}, max_limit=500)
        assert result.limit == 500

    def test_limit_clamped_to_min_1(self):
        result = parse_pagination_params({"limit": "0"})
        assert result.limit == 1

    def test_offset_clamped_to_min_0(self):
        result = parse_pagination_params({"offset": "-5"})
        assert result.offset == 0


class TestParseDateParamStrict:
    """parse_date_param_strict: Result-wrapped date parsing."""

    def test_valid(self):
        result = parse_date_param_strict("2026-03-18", "start_date")
        assert result.is_ok
        assert result.value == date(2026, 3, 18)

    def test_none_returns_error(self):
        result = parse_date_param_strict(None, "start_date")
        assert result.is_error

    def test_empty_returns_error(self):
        result = parse_date_param_strict("", "start_date")
        assert result.is_error

    def test_invalid_format_returns_error(self):
        result = parse_date_param_strict("not-a-date", "start_date")
        assert result.is_error


class TestParseIntParamStrict:
    """parse_int_param_strict: Result-wrapped integer parsing with range check."""

    def test_valid_in_range(self):
        result = parse_int_param_strict("6", "month", 1, 12)
        assert result.is_ok
        assert result.value == 6

    def test_none_returns_error(self):
        result = parse_int_param_strict(None, "month", 1, 12)
        assert result.is_error

    def test_empty_returns_error(self):
        result = parse_int_param_strict("", "month", 1, 12)
        assert result.is_error

    def test_non_numeric_returns_error(self):
        result = parse_int_param_strict("abc", "month", 1, 12)
        assert result.is_error

    def test_below_min_returns_error(self):
        result = parse_int_param_strict("0", "month", 1, 12)
        assert result.is_error

    def test_above_max_returns_error(self):
        result = parse_int_param_strict("13", "month", 1, 12)
        assert result.is_error

    def test_boundary_min(self):
        result = parse_int_param_strict("1", "month", 1, 12)
        assert result.is_ok
        assert result.value == 1

    def test_boundary_max(self):
        result = parse_int_param_strict("12", "month", 1, 12)
        assert result.is_ok
        assert result.value == 12
