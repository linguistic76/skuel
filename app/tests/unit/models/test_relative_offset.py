"""Tests for RelativeOffset value type and its Pydantic DTO companion."""

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from core.models.templates import RelativeOffset, RelativeOffsetDTO


class TestRelativeOffsetConstruction:
    """Construction defaults, equality, and immutability."""

    def test_default_is_zero(self):
        assert RelativeOffset() == RelativeOffset(0, 0, 0)
        assert RelativeOffset().is_zero()

    def test_keyword_construction(self):
        o = RelativeOffset(days=7, hours=12, minutes=30)
        assert (o.days, o.hours, o.minutes) == (7, 12, 30)

    def test_frozen(self):
        o = RelativeOffset(days=1)
        with pytest.raises((AttributeError, Exception)):
            o.days = 2  # type: ignore[misc]

    def test_equality_by_value(self):
        assert RelativeOffset(1, 2, 3) == RelativeOffset(1, 2, 3)
        assert RelativeOffset(1) != RelativeOffset(2)

    def test_hashable(self):
        # frozen dataclasses are hashable; matters for use in sets / as dict keys
        assert {RelativeOffset(1), RelativeOffset(1), RelativeOffset(2)} == {
            RelativeOffset(1),
            RelativeOffset(2),
        }


class TestRelativeOffsetValidation:
    """Negative components are rejected at construction."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"days": -1},
            {"hours": -1},
            {"minutes": -1},
            {"days": -1, "hours": 5},
        ],
    )
    def test_rejects_negative_components(self, kwargs):
        with pytest.raises(ValueError, match="non-negative"):
            RelativeOffset(**kwargs)


class TestRelativeOffsetResolution:
    """Resolution to concrete date/datetime against an engagement anchor."""

    def test_as_timedelta(self):
        o = RelativeOffset(days=2, hours=3, minutes=15)
        assert o.as_timedelta() == timedelta(days=2, hours=3, minutes=15)

    def test_resolve_to_datetime_naive(self):
        anchor = datetime(2026, 5, 9, 9, 0)
        o = RelativeOffset(days=7, hours=2)
        assert o.resolve_to_datetime(anchor) == datetime(2026, 5, 16, 11, 0)

    def test_resolve_to_datetime_preserves_tz(self):
        # Spawn orchestrator passes the engagement instant in user-local tz; the
        # value type must not strip or rewrite tzinfo.
        anchor = datetime(2026, 5, 9, 9, 0, tzinfo=UTC)
        o = RelativeOffset(days=1)
        result = o.resolve_to_datetime(anchor)
        assert result.tzinfo is UTC
        assert result == datetime(2026, 5, 10, 9, 0, tzinfo=UTC)

    def test_resolve_to_date_from_date(self):
        anchor = date(2026, 5, 9)
        assert RelativeOffset(days=7).resolve_to_date(anchor) == date(2026, 5, 16)

    def test_resolve_to_date_from_datetime_truncates(self):
        # Time portion participates in arithmetic but is dropped at the end.
        anchor = datetime(2026, 5, 9, 23, 30)
        assert RelativeOffset(hours=1).resolve_to_date(anchor) == date(2026, 5, 10)

    def test_resolve_to_date_overflow_into_days(self):
        # 36h on top of a date(treated as midnight) lands 1.5 days later.
        anchor = date(2026, 5, 9)
        assert RelativeOffset(days=2, hours=36).resolve_to_date(anchor) == date(2026, 5, 12)

    def test_zero_offset_resolves_to_anchor(self):
        anchor = datetime(2026, 5, 9, 9, 0)
        assert RelativeOffset().resolve_to_datetime(anchor) == anchor
        assert RelativeOffset().resolve_to_date(anchor) == date(2026, 5, 9)


class TestRelativeOffsetDTO:
    """Pydantic DTO mirrors and validates the value type for API boundaries."""

    def test_default_is_zero(self):
        dto = RelativeOffsetDTO()
        assert dto.days == 0 and dto.hours == 0 and dto.minutes == 0

    def test_serialization(self):
        dto = RelativeOffsetDTO(days=7, hours=12, minutes=30)
        assert dto.model_dump() == {"days": 7, "hours": 12, "minutes": 30}

    def test_deserialization_from_dict(self):
        dto = RelativeOffsetDTO.model_validate({"days": 3, "hours": 4, "minutes": 5})
        assert (dto.days, dto.hours, dto.minutes) == (3, 4, 5)

    def test_rejects_negative(self):
        with pytest.raises(ValidationError):
            RelativeOffsetDTO(days=-1)

    def test_value_roundtrip(self):
        original = RelativeOffset(days=7, hours=12, minutes=30)
        dto = RelativeOffsetDTO.from_value(original)
        assert dto.to_value() == original

    def test_dto_to_value_to_dto(self):
        dto = RelativeOffsetDTO(days=2, hours=4)
        assert RelativeOffsetDTO.from_value(dto.to_value()) == dto
