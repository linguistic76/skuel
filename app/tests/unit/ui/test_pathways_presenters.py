"""Pathways dashboard presenters — every display decision the core service used to make.

``LpService.get_dashboard_summary`` returned ``ActivePathData``/``LearningStatsData``
directly, formatting "12h total", the difficulty label and the current-step text inside
a ``core/`` service (the last ``core/ → ui/`` runtime edge in the tree, now guarded by
SKUEL032). Those strings moved here, so this is the file that pins them.

These assertions could not be proven red against ``main`` — the functions do not exist
there. What WAS proven is behaviour preservation: a 360-path differential ran ``main``'s
``calculate_path_progress``/``get_dashboard_summary`` against the new pipeline and the
rendered ``pages.dashboard_content`` fragment was byte-identical (550,591 bytes), with
six injected faults confirming the comparison can fail.
"""

from __future__ import annotations

from typing import Any

from core.ports.query_types import LpActivePathProgress, LpDashboardSummary
from ui.pathways.components import difficulty_label, to_active_path_data, to_learning_stats


def _row(**overrides: Any) -> LpActivePathProgress:
    base: dict[str, Any] = {
        "uid": "lp.demo.path",
        "title": "Demo Path",
        "difficulty_rating": 0.5,
        "estimated_hours": 12.0,
        "progress_percent": 40.0,
        "is_complete": False,
        "next_step_title": "Second Step",
    }
    base.update(overrides)
    return LpActivePathProgress(**base)  # type: ignore[typeddict-item]


def _summary(**overrides: Any) -> LpDashboardSummary:
    base: dict[str, Any] = {
        "paths": [],
        "total_hours": 30.0,
        "concepts_mastered": 4,
        "completion_rate": 0.25,
    }
    base.update(overrides)
    return LpDashboardSummary(**base)  # type: ignore[typeddict-item]


class TestCurrentStepText:
    """Three outcomes, and they need BOTH `is_complete` and `next_step_title`:
    a single nullable field would conflate "every step mastered" with
    "the next step has no title"."""

    def test_complete_when_no_unmastered_step(self) -> None:
        assert to_active_path_data(_row(is_complete=True, next_step_title=None)).current_step == (
            "Complete"
        )

    def test_next_step_title_when_present(self) -> None:
        row = _row(is_complete=False, next_step_title="Second Step")
        assert to_active_path_data(row).current_step == "Second Step"

    def test_placeholder_when_next_step_is_untitled(self) -> None:
        row = _row(is_complete=False, next_step_title=None)
        assert to_active_path_data(row).current_step == "Next step"

    def test_complete_wins_even_if_a_title_leaks_through(self) -> None:
        """`is_complete` is the discriminator, not the presence of a title."""
        row = _row(is_complete=True, next_step_title="Should Not Show")
        assert to_active_path_data(row).current_step == "Complete"


class TestHoursStrings:
    def test_both_hour_strings_are_the_same_truncated_number(self) -> None:
        """`estimated_completion` and `time_invested` are the SAME datum with
        different suffixes — there is no time-invested measurement anywhere. The
        card renders "12h est. invested"; preserved verbatim, reported not fixed."""
        data = to_active_path_data(_row(estimated_hours=12.7))
        assert data.estimated_completion == "12h total"
        assert data.time_invested == "12h est."

    def test_zero_hours_renders_zero_not_blank(self) -> None:
        data = to_active_path_data(_row(estimated_hours=0.0))
        assert data.estimated_completion == "0h total"
        assert data.time_invested == "0h est."


class TestTitleFallback:
    def test_untitled_path_placeholder(self) -> None:
        assert to_active_path_data(_row(title="")).title == "Untitled Path"

    def test_real_title_passes_through(self) -> None:
        assert to_active_path_data(_row(title="Real Title")).title == "Real Title"


class TestDifficultyLabel:
    """The three strings are a query contract, not a caption: the filter form's
    `<option value=...>` set (`render_filter_form`) and `LpService.filter_paths`'s
    `p["difficulty"] == difficulty` comparison both key on them."""

    def test_boundaries(self) -> None:
        assert difficulty_label(0.0) == "beginner"
        assert difficulty_label(0.35) == "beginner"
        assert difficulty_label(0.350001) == "intermediate"
        assert difficulty_label(0.65) == "intermediate"
        assert difficulty_label(0.650001) == "advanced"
        assert difficulty_label(1.0) == "advanced"

    def test_card_difficulty_comes_from_the_rating(self) -> None:
        assert to_active_path_data(_row(difficulty_rating=0.2)).difficulty == "beginner"
        assert to_active_path_data(_row(difficulty_rating=0.9)).difficulty == "advanced"

    def test_label_vocabulary_matches_the_filter_form_options(self) -> None:
        """If these drift apart the filter silently returns nothing — and no test
        below this one would notice, because `filter_paths` has zero cover."""
        from fasthtml.common import to_xml

        from ui.pathways.components import PathwaysUIComponents

        rendered = to_xml(PathwaysUIComponents.render_filter_form())
        for label in ("beginner", "intermediate", "advanced"):
            assert f'value="{label}"' in rendered


class TestLearningStats:
    def test_carries_summary_values_through(self) -> None:
        stats = to_learning_stats(_summary(total_hours=30.0, concepts_mastered=4))
        assert stats.total_hours == 30.0
        assert stats.concepts_mastered == 4
        assert stats.completion_rate == 0.25

    def test_active_streak_is_a_ui_placeholder(self) -> None:
        """Nothing computes a streak — the route rendered a hardcoded 0 before this
        converter existed. Pinned so a future producer is a deliberate change."""
        assert to_learning_stats(_summary()).active_streak == 0
