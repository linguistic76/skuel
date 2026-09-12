"""Lateral relationship writes accept only the three Priority values."""

from __future__ import annotations

import pytest

from adapters.inbound.route_factories.lateral_route_factory import _lateral_priority
from core.utils.result_simplified import ErrorCategory


@pytest.mark.parametrize("raw,expected", [("high", "high"), ("Medium", "medium"), (" LOW ", "low")])
def test_member_values_are_canonicalised(raw: str, expected: str) -> None:
    result = _lateral_priority(raw)
    assert result.is_ok
    assert result.value == expected


@pytest.mark.parametrize("raw", ["critical", "urgent", "", "P1"])
def test_values_outside_the_vocabulary_are_refused(raw: str) -> None:
    result = _lateral_priority(raw)
    assert result.is_error
    assert result.expect_error().category == ErrorCategory.VALIDATION
