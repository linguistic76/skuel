"""
Unit tests for the habit detail page's new HTMX-loaded sections.

Covers:
- HabitInsightsSection: pattern insight rendering + empty state.
- HabitDetailView: the insights fragment's HTMX placeholder; a habit's links to
  choices are in its Connections section, not a section of their own.
"""

from fasthtml.common import to_xml

from core.models.habit.habit import Habit
from core.ports.query_types import EntityConnection
from core.services.habits.habits_pattern_service import PatternAnalysis
from ui.activities.habits_views import (
    HabitDetailView,
    HabitInsightsSection,
)

# ---------------------------------------------------------------------------
# HabitInsightsSection
# ---------------------------------------------------------------------------


def _analysis(success: list[dict], failure: list[dict]) -> PatternAnalysis:
    return PatternAnalysis(
        name="Morning Reading",
        total_completions=40,
        success_patterns=success,
        failure_patterns=failure,
    )


def test_insights_section_renders_patterns() -> None:
    analysis = _analysis(
        success=[
            {
                "pattern": "Part of goal system (2 goals)",
                "confidence": 0.85,
                "recommendation": "Systems-based approach is effective",
            }
        ],
        failure=[
            {
                "pattern": "Low success rate: 30%",
                "confidence": 0.7,
                "recommendation": "Consider making habit easier",
            }
        ],
    )
    html = to_xml(HabitInsightsSection(analysis))
    assert "Pattern Insights" in html
    assert "Part of goal system (2 goals)" in html
    assert "85% confidence" in html
    assert "Systems-based approach is effective" in html
    assert "Low success rate: 30%" in html
    assert "What's working" in html
    assert "What needs attention" in html


def test_insights_section_empty_state() -> None:
    html = to_xml(HabitInsightsSection(_analysis([], [])))
    assert "No patterns detected yet" in html


# ---------------------------------------------------------------------------
# HabitDetailView placeholders
# ---------------------------------------------------------------------------


def test_detail_view_includes_the_insights_placeholder() -> None:
    habit = Habit(uid="habit_detail_test", title="Morning Reading", user_uid="user_test")
    html = to_xml(HabitDetailView(habit, connections=[]))
    assert "/habits/insights-fragment?uid=habit_detail_test" in html
    # The HTMX lazy-load placeholder carries the swap target id.
    assert 'id="habit-insights"' in html


def test_the_habits_choices_are_in_its_connections_not_a_section_of_their_own() -> None:
    habit = Habit(uid="habit_detail_test", title="Morning Reading", user_uid="user_test")
    informed: EntityConnection = {
        "heading": "Choices this habit informs",
        "rel_type": "INFORMS_CHOICE",
        "connected_uid": "choice_career",
        "title": "Take the new role",
        "connected_type": "choice",
    }
    html = to_xml(HabitDetailView(habit, connections=[informed]))
    assert "Choices this habit informs" in html
    assert "/choices/detail?uid=choice_career" in html
    assert "choices-fragment" not in html
    assert 'id="habit-choices"' not in html
