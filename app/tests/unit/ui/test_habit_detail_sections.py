"""
Unit tests for the habit detail page's new HTMX-loaded sections.

Covers:
- HabitChoicesSection: Habit ↔ Choice lens (informed + impacting), with and
  without data, links to choice detail pages.
- HabitInsightsSection: pattern insight rendering + empty state.
- HabitDetailView: detail page includes the HTMX placeholders for both
  fragments (/habits/choices-fragment, /habits/insights-fragment).
"""

from fasthtml.common import to_xml

from core.models.habit.habit import Habit
from core.services.habits.habits_pattern_service import PatternAnalysis
from ui.activities.habits_views import (
    HabitChoicesSection,
    HabitDetailView,
    HabitInsightsSection,
)

INFORMED = [{"uid": "choice_career", "title": "Take the new role", "edge": {}}]
IMPACTING = [{"uid": "choice_move", "title": "Move closer to the gym", "edge": {}}]


# ---------------------------------------------------------------------------
# HabitChoicesSection
# ---------------------------------------------------------------------------


def test_choices_section_renders_both_directions() -> None:
    html = to_xml(HabitChoicesSection(INFORMED, IMPACTING))
    assert "Choices" in html
    assert "Choices this habit informed" in html
    assert "Choices impacting this habit" in html
    assert "Take the new role" in html
    assert "Move closer to the gym" in html
    assert "/choices/detail?uid=choice_career" in html
    assert "/choices/detail?uid=choice_move" in html


def test_choices_section_renders_one_direction_only() -> None:
    html = to_xml(HabitChoicesSection(INFORMED, []))
    assert "Choices this habit informed" in html
    assert "Choices impacting this habit" not in html


def test_choices_section_empty_renders_nothing_visible() -> None:
    html = to_xml(HabitChoicesSection([], []))
    # Keeps the swap target id but no section content.
    assert 'id="habit-choices"' in html
    assert "Choices" not in html


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


def test_detail_view_includes_fragment_placeholders() -> None:
    habit = Habit(uid="habit_detail_test", title="Morning Reading", user_uid="user_test")
    html = to_xml(HabitDetailView(habit, connections=[]))
    assert "/habits/choices-fragment?uid=habit_detail_test" in html
    assert "/habits/insights-fragment?uid=habit_detail_test" in html
    # HTMX lazy-load placeholders carry the swap target ids.
    assert 'id="habit-choices"' in html
    assert 'id="habit-insights"' in html
