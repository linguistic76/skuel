"""
DSL line → habit time-of-day slot
=================================

``activity_to_habit_request`` is the ingestion door for habits authored as DSL
lines (LLM-extracted from user entries). It used to write ``@energy()``'s first
state into ``preferred_time`` — which is how the live graph came to hold
``"medium"``, an ``EnergyLevel`` word, in a time field.

The slot now comes from ``@when()``, and only when the author actually wrote a
clock time: a bare date parses to midnight, and treating that as a stated time
would file the habit under LATE_NIGHT and schedule it at 02:00.
"""

import pytest

from core.models.enums.scheduling_enums import TimeOfDay
from core.services.dsl.activity_domain_converters import activity_to_habit_request
from core.services.dsl.activity_dsl_parser import parse_activity_line


def _habit_request(line: str):
    parsed = parse_activity_line(line)
    assert parsed.is_ok, f"line did not parse: {line}"
    converted = activity_to_habit_request(parsed.value)
    assert converted.is_ok, f"conversion failed: {converted}"
    return converted.value


DAY = "2099-03-04"  # far future — @when validation rejects the past


class TestSlotFromWhen:
    @pytest.mark.parametrize(
        ("clock", "expected"),
        [
            ("06:00", TimeOfDay.EARLY_MORNING),
            ("07:00", TimeOfDay.MORNING),
            ("09:30", TimeOfDay.MORNING),
            ("14:00", TimeOfDay.AFTERNOON),
            ("19:00", TimeOfDay.EVENING),
            ("22:00", TimeOfDay.NIGHT),
            ("00:00", TimeOfDay.LATE_NIGHT),
        ],
    )
    def test_a_written_clock_time_becomes_its_slot(self, clock, expected) -> None:
        request = _habit_request(f"- [ ] Sit @context(habit) @when({DAY}T{clock})")
        assert request.preferred_time is expected

    def test_a_date_only_when_states_no_slot(self) -> None:
        """The regression this guards: midnight-from-a-date is not late night."""
        request = _habit_request(f"- [ ] Sit @context(habit) @when({DAY})")
        assert request.preferred_time is None

    def test_no_when_at_all_states_no_slot(self) -> None:
        assert _habit_request("- [ ] Sit @context(habit)").preferred_time is None


class TestEnergyIsNotATime:
    @pytest.mark.parametrize("energy", ["focus", "rest", "creative"])
    def test_energy_never_reaches_preferred_time(self, energy) -> None:
        request = _habit_request(f"- [ ] Sit @context(habit) @energy({energy})")
        assert request.preferred_time is None

    def test_energy_still_reaches_the_habit_as_a_tag(self) -> None:
        request = _habit_request("- [ ] Sit @context(habit) @energy(focus)")
        assert "focus" in request.tags

    def test_energy_and_when_together_keep_their_own_fields(self) -> None:
        request = _habit_request(f"- [ ] Sit @context(habit) @energy(focus) @when({DAY}T19:00)")
        assert request.preferred_time is TimeOfDay.EVENING
        assert "focus" in request.tags
