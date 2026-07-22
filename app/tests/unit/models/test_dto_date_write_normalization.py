"""Unit guards for date-field write normalization (#766, write side).

A date field must persist as ``"YYYY-MM-DD"`` — never with a time component —
even if an upstream path mis-assigns a ``datetime`` (``datetime`` subclasses
``date``, so a naive ``.isoformat()`` would leak ``"...T09:00:00"``). That leaked
time then makes Cypher's ``date()`` throw on read and blanks the whole range.

``convert_dates_to_iso`` is the single serialization chokepoint every DTO's
``to_dict`` routes through, so normalizing ``datetime -> .date()`` there is the
write-side root-cause fix.
"""

from dataclasses import dataclass
from datetime import date, datetime

from core.models.dto_helpers import convert_dates_to_iso, dto_to_dict


class TestConvertDatesToIso:
    """The chokepoint: a declared date field never serializes a time component."""

    def test_date_value_serializes_date_only(self):
        data = {"due_date": date(2026, 6, 17)}
        convert_dates_to_iso(data, ["due_date"])
        assert data["due_date"] == "2026-06-17"

    def test_datetime_value_strips_time_component(self):
        # The #766 write-side case: a datetime mis-assigned to a date field must
        # persist only its date part, so read-side date() never sees a time.
        data = {"due_date": datetime(2026, 6, 17, 9, 30, 15, 123456)}
        convert_dates_to_iso(data, ["due_date"])
        assert data["due_date"] == "2026-06-17"

    def test_absent_field_is_noop(self):
        data = {"other": 1}
        convert_dates_to_iso(data, ["due_date"])
        assert "due_date" not in data

    def test_none_value_is_noop(self):
        data = {"due_date": None}
        convert_dates_to_iso(data, ["due_date"])
        assert data["due_date"] is None

    def test_already_string_left_untouched(self):
        data = {"due_date": "2026-06-17"}
        convert_dates_to_iso(data, ["due_date"])
        assert data["due_date"] == "2026-06-17"


@dataclass
class _DateOnlyDTO:
    due_date: date | None = None


class TestDtoToDictDateNormalization:
    """End-to-end through the real serialization path a DTO.to_dict uses."""

    def test_dto_to_dict_strips_time_from_date_field(self):
        dto = _DateOnlyDTO(due_date=datetime(2026, 6, 17, 9, 30))
        out = dto_to_dict(dto, enum_fields=[], date_fields=["due_date"])
        assert out["due_date"] == "2026-06-17"

    def test_dto_to_dict_keeps_plain_date(self):
        dto = _DateOnlyDTO(due_date=date(2026, 6, 17))
        out = dto_to_dict(dto, enum_fields=[], date_fields=["due_date"])
        assert out["due_date"] == "2026-06-17"
