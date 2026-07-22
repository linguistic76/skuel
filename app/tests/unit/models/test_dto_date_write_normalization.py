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

from core.models.dto_helpers import coerce_date_fields, convert_dates_to_iso, dto_to_dict
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.models.task.task_update_intent import TaskUpdateIntent


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


class TestCoerceDateFields:
    """The update-path chokepoint (intent.to_changes bypasses convert_dates_to_iso)."""

    def test_datetime_downcast_to_date(self):
        changes = {"due_date": datetime(2026, 6, 17, 9, 30)}
        coerce_date_fields(changes, "due_date")
        assert changes["due_date"] == date(2026, 6, 17)
        assert not isinstance(changes["due_date"], datetime)

    def test_plain_date_untouched(self):
        changes = {"due_date": date(2026, 6, 17)}
        coerce_date_fields(changes, "due_date")
        assert changes["due_date"] == date(2026, 6, 17)

    def test_absent_and_none_are_noops(self):
        changes = {"due_date": None}
        coerce_date_fields(changes, "due_date", "scheduled_date")
        assert changes["due_date"] is None
        assert "scheduled_date" not in changes

    def test_non_listed_datetime_field_untouched(self):
        # A genuine datetime field (not passed as a date field) keeps its time.
        changes = {"decision_deadline": datetime(2026, 6, 17, 9, 30)}
        coerce_date_fields(changes, "due_date")
        assert changes["decision_deadline"] == datetime(2026, 6, 17, 9, 30)


class TestUpdateIntentDateNormalization:
    """intent.to_changes() must never emit a datetime in a date field (#766)."""

    def test_task_intent_downcasts_datetime_due_date(self):
        changes = TaskUpdateIntent(due_date=datetime(2026, 6, 17, 9, 30)).to_changes()
        assert changes["due_date"] == date(2026, 6, 17)
        assert not isinstance(changes["due_date"], datetime)

    def test_task_intent_keeps_plain_date(self):
        changes = TaskUpdateIntent(scheduled_date=date(2026, 6, 17)).to_changes()
        assert changes["scheduled_date"] == date(2026, 6, 17)

    def test_event_intent_downcasts_datetime_event_date(self):
        changes = EventUpdateIntent(event_date=datetime(2026, 6, 17, 9, 30)).to_changes()
        assert changes["event_date"] == date(2026, 6, 17)

    def test_goal_intent_downcasts_datetime_target_date(self):
        changes = GoalUpdateIntent(target_date=datetime(2026, 6, 17, 9, 30)).to_changes()
        assert changes["target_date"] == date(2026, 6, 17)

    def test_unset_fields_stay_absent(self):
        # Only the set field appears; the coercion must not resurrect UNSET fields.
        changes = TaskUpdateIntent(due_date=datetime(2026, 6, 17, 9, 30)).to_changes()
        assert set(changes) == {"due_date"}
