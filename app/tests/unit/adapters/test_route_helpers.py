"""Tests for route_helpers.parse_int_query_param."""

from adapters.inbound.route_factories.route_helpers import parse_int_query_param


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
