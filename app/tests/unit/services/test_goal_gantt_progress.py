"""Value pins for the goal bar emitted by ``VisualizationService.format_goal_gantt``.

``format_goal_gantt`` read ``getattr(goal, "progress", 0) or 0`` — and ``Goal`` has no
``progress`` field. The default therefore won on every call, so **every** goal bar on
``GET /api/visualizations/gantt/goal/{goal_uid}`` rendered 0%. The normalisation beside it,
``int(goal_progress * 100) if goal_progress <= 1 else int(goal_progress)``, then took its
``<= 1`` arm every time (``0 <= 1``) and faithfully scaled the wrong number; the arm that
no input could reach was the ``else int(goal_progress)``.

Why the bug survived: nothing asserted the *value*. No test in the repo's history ever
referenced ``format_goal_gantt``; the one path that reached it,
``tests/integration/test_gantt_aggregation_roundtrip.py``, builds a real ``Goal`` through
Neo4j and asserts only which UIDs appear. ``test_visualization_wire_shape.py`` pins the key
set and passes either way. Shape was covered from both ends and value from neither, which
is the gap this file fills.

The goals below are real :class:`~core.models.goal.goal.Goal` objects rather than
duck-typed stand-ins for a forward-looking reason, not a historical one: a stand-in
carrying a ``progress`` attribute would make the buggy code pass and silently re-admit the
regression.

Two tests here also pin the *choice of reader*. ``Goal`` exposes both
``progress_percentage`` (0-100) and ``calculate_progress()`` (0.0-1.0), and the latter is
wrong for this bar — see ``TestGoalBarReaderChoice``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.services.visualization_service import VisualizationService


@pytest.fixture
def service() -> VisualizationService:
    return VisualizationService()


def _goal(**overrides: object) -> Goal:
    """A real Goal. ``uid`` and ``title`` are read by the formatter, ``user_uid`` is a
    required constructor argument it never touches, and ``measurement_type`` is here
    because the reader-choice tests below turn on it."""
    fields: dict[str, object] = {
        "uid": "goal_1",
        "user_uid": "user_1",
        "title": "Ship the feature",
        "measurement_type": MeasurementType.PERCENTAGE,
        "start_date": date(2026, 3, 1),
        "target_date": date(2026, 6, 1),
    }
    fields.update(overrides)
    return Goal(**fields)  # type: ignore[arg-type]


def _goal_bar(service: VisualizationService, goal: Goal) -> dict:
    """The first Gantt task is the goal's own bar (custom_class ``goal-bar``)."""
    result = service.format_goal_gantt(goal, [])
    assert result.is_ok, f"format_goal_gantt failed: {result}"
    bar = result.value["tasks"][0]
    assert bar["custom_class"] == "goal-bar"
    return bar


class TestGoalBarProgress:
    def test_partial_progress_is_not_zero(self, service: VisualizationService) -> None:
        """The regression itself: a 40%-complete goal must not render as an empty bar."""
        bar = _goal_bar(service, _goal(progress_percentage=40.0))

        assert bar["progress"] == 40

    def test_zero_progress_stays_zero(self, service: VisualizationService) -> None:
        bar = _goal_bar(service, _goal(progress_percentage=0.0))

        assert bar["progress"] == 0

    def test_complete_goal_reads_one_hundred(self, service: VisualizationService) -> None:
        """Pins the scale at the top of the range: 100 in, 100 out — catching a stray
        ``/ 100``, which would emit 1. Note this test cannot catch the opposite slip: a
        doubly-scaled 10000 clips back to exactly 100 through the clamp, so
        ``test_partial_progress_is_not_zero`` is what covers that direction."""
        bar = _goal_bar(service, _goal(progress_percentage=100.0))

        assert bar["progress"] == 100

    def test_sub_one_percent_is_not_inflated_to_half(self, service: VisualizationService) -> None:
        """The case that keeps the deleted ``<= 1`` normalisation deleted.

        Against a 0-100 reader, ``int(value * 100) if value <= 1`` turns 0.5% into 50% —
        a barely-started goal rendered as half done.
        """
        bar = _goal_bar(service, _goal(progress_percentage=0.5))

        assert bar["progress"] == 0

    def test_repeating_percentage_rounds_rather_than_truncates(
        self, service: VisualizationService
    ) -> None:
        """``complete_milestone`` stores ``(completed / total) * 100``, so 2 of 3
        milestones is 66.666… — which ``int()`` would render as 66."""
        bar = _goal_bar(service, _goal(progress_percentage=200.0 / 3.0))

        assert bar["progress"] == 67

    def test_above_range_progress_is_clamped_to_one_hundred(
        self, service: VisualizationService
    ) -> None:
        """Vault ingestion copies goal frontmatter into node properties unchecked, so
        ``progress_percentage: 150`` reaches the formatter. Frappe Gantt takes 0-100."""
        bar = _goal_bar(service, _goal(progress_percentage=150.0))

        assert bar["progress"] == 100

    def test_below_range_progress_is_clamped_to_zero(self, service: VisualizationService) -> None:
        """Same unvalidated door as above, other end: ``progress_percentage: -40``."""
        bar = _goal_bar(service, _goal(progress_percentage=-40.0))

        assert bar["progress"] == 0


class TestGoalBarUntypedStoredValue:
    """Neo4j properties carry no type, and nothing coerces on either leg of the trip.

    Vault ingestion copies goal frontmatter into node properties verbatim
    (``prepare_entity_data`` is ``dict(data)``), and the DTO -> domain conversion does not
    narrow scalars, so a quoted ``progress_percentage: "40"`` arrives here as ``str``.
    Measured: ``to_domain_model({... 'progress_percentage': '40'}, GoalDTO, Goal)
    .progress_percentage`` is ``'40'``, not ``40.0``.
    """

    def test_numeric_string_is_narrowed_not_crashed_on(self, service: VisualizationService) -> None:
        """``round('40')`` raises ``TypeError``; the float() narrowing keeps the route
        returning a Result, and the bar reads what the author meant."""
        bar = _goal_bar(service, _goal(progress_percentage="40"))

        assert bar["progress"] == 40

    def test_none_is_treated_as_no_progress_not_as_a_data_defect(
        self, service: VisualizationService
    ) -> None:
        """Scope, stated rather than implied: ``None`` does **not** arrive by this
        route. ``_CrudMixin.get`` does ``RETURN n`` then ``dict(record["n"])``, and a
        Neo4j node's property map omits absent properties, so a goal with no stored
        ``progress_percentage`` reaches the DTO default 0.0 — measured.

        The branch is kept because ``to_domain_model`` passes a present-but-``None``
        value through unchanged (also measured), which any property-projecting reader
        would produce; and because ``None`` means "no progress recorded", so 0 is the
        right answer rather than the validation failure the bare ``float()`` would give.
        """
        bar = _goal_bar(service, _goal(progress_percentage=None))

        assert bar["progress"] == 0

    @pytest.mark.parametrize(
        ("stored", "why"),
        [
            ("lots", "a string no cast can rescue -> float() raises ValueError"),
            ([1, 2], "a list -> float() raises TypeError"),
            (float("nan"), "YAML `.nan` -> float() succeeds, round() raises ValueError"),
            (float("inf"), "YAML `.inf` -> float() succeeds, round() raises OverflowError"),
            (float("-inf"), "YAML `-.inf` -> same, and the clamp would not save it either"),
        ],
    )
    def test_unusable_value_fails_the_result_rather_than_raising(
        self, service: VisualizationService, stored: object, why: str
    ) -> None:
        """Every value that is not a finite number must come back as a ``Result`` failure.

        These are five *instances* of one class, and the guard is written to close the
        class: ``float()`` either raises or yields a float, and a float is finite, ±inf or
        nan. The two non-finite cases matter because they get *past* ``float()`` — and
        past the clamp too: ``max(0, nan)`` is 0 and ``min(100, nan)`` is 100, so a clamp
        alone silently invents a plausible-looking bar.

        Failing beats rendering a silent 0 — a silent 0 on this very bar is what hid the
        original bug.
        """
        result = service.format_goal_gantt(_goal(progress_percentage=stored), [])

        assert result.is_error, why
        assert "progress_percentage" in str(result.expect_error().message)


class TestGoalBarReaderChoice:
    """``Goal`` offers two progress readers and only one of them is right here.

    ``calculate_progress()`` returns 0.0-1.0 while this bar wants 0-100, so switching the
    formatter to it would need back the ``* 100`` that was deleted alongside the reader —
    and ``round()`` collapses what arrives instead. Both tests below fail on that switch;
    they exist so it cannot be made silently.

    They no longer turn on the unit mismatch they were written for (``current_value``
    holding a percent against a ``target_value`` in domain units): that is fixed, and
    ``calculate_progress()`` now agrees with ``progress_percentage`` on both goals here —
    on the *0.0-1.0* scale, which is exactly the trap.
    """

    def test_completed_value_measured_goal_reads_full(self, service: VisualizationService) -> None:
        """``goals_core_service.complete_goal`` writes ``progress_percentage=100.0`` and
        never touches ``current_value``. ``calculate_progress()`` reads that as 1.0, which
        ``round()`` would put on the bar as 1% — a finished goal all but empty, the same
        symptom in a smaller size."""
        bar = _goal_bar(
            service,
            _goal(
                measurement_type=MeasurementType.NUMERIC,
                target_value=10.0,
                current_value=0.0,
                progress_percentage=100.0,
            ),
        )

        assert bar["progress"] == 100

    def test_task_based_goal_one_fifth_in_does_not_read_complete(
        self, service: VisualizationService
    ) -> None:
        """A 5-task goal one task in. ``calculate_progress()`` reads 0.2, which ``round()``
        would put on the bar as 0 — the original empty-bar symptom, restored by a reader
        swap rather than by a missing field."""
        bar = _goal_bar(
            service,
            _goal(
                measurement_type=MeasurementType.TASK_BASED,
                target_value=5.0,
                current_value=20.0,
                progress_percentage=20.0,
            ),
        )

        assert bar["progress"] == 20


class TestGoalBarDates:
    """``start_date`` / ``target_date`` were read through ``getattr`` defaults too. Both
    are real ``Goal`` fields, so those reads worked — these pin the fallbacks that the
    ``or`` half of those expressions provided, which the direct reads must keep."""

    def test_declared_dates_are_used(self, service: VisualizationService) -> None:
        bar = _goal_bar(service, _goal(progress_percentage=10.0))

        assert bar["start"] == "2026-03-01"
        assert bar["end"] == "2026-06-01"

    def test_missing_dates_fall_back_to_today_plus_ninety_days(
        self, service: VisualizationService
    ) -> None:
        bar = _goal_bar(service, _goal(start_date=None, target_date=None))

        assert bar["start"] == date.today().isoformat()
        assert bar["end"] == (date.today() + timedelta(days=90)).isoformat()
