"""
Unit tests for LifePathVisionService — pure-Python paths (no LLM, no graph).

Covers the CORE-tier behavior: keyword theme extraction (the fallback that
runs whenever llm_service is None), vision-statement validation, and the
word-action alignment computation that bridges vision themes to UserContext.

The LLM extraction path and LP recommendation search are exercised at the
integration level (real LpService) — not mocked here, per the project's
"mock-only unit tests hide phantom methods" rule.
"""

from __future__ import annotations

import pytest

from core.models.enums.lifepath_enums import ThemeCategory
from core.services.lifepath.lifepath_vision_service import LifePathVisionService
from core.services.user.unified_user_context import UserContext
from core.utils.result_simplified import ErrorCategory

pytestmark = pytest.mark.asyncio

_USER = "user_test_vision_unit"


@pytest.fixture
def vision_service() -> LifePathVisionService:
    """CORE-tier service: no LLM, no LP service."""
    return LifePathVisionService(llm_service=None, lp_service=None)


class TestCaptureVision:
    async def test_too_short_statement_is_validation_error(self, vision_service):
        result = await vision_service.capture_vision(_USER, "short")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.VALIDATION

    async def test_whitespace_padding_does_not_pass_validation(self, vision_service):
        result = await vision_service.capture_vision(_USER, "   hi    \n   ")

        assert result.is_error

    async def test_keyword_extraction_maps_known_themes(self, vision_service):
        result = await vision_service.capture_vision(
            _USER, "I want to become a mindful leader focused on mindfulness and leadership"
        )

        assert result.is_ok
        capture = result.value
        assert capture.user_uid == _USER
        assert capture.llm_model is None  # CORE tier: no LLM involved

        themes = {t.theme: t for t in capture.themes}
        assert "mindfulness" in themes
        assert "leadership" in themes
        assert themes["mindfulness"].category == ThemeCategory.PERSONAL_GROWTH
        assert themes["leadership"].category == ThemeCategory.CAREER
        # Keyword matches carry the reduced-confidence stamp
        assert all(t.confidence == pytest.approx(0.7) for t in capture.themes)

    async def test_repeated_keyword_extracted_once(self, vision_service):
        result = await vision_service.capture_vision(
            _USER, "health health health is my priority, health above all"
        )

        assert result.is_ok
        assert [t.theme for t in result.value.themes] == ["health"]

    async def test_unknown_words_fall_back_to_noun_extraction(self, vision_service):
        result = await vision_service.capture_vision(
            _USER, "I would like to conquer chess and juggling someday"
        )

        assert result.is_ok
        themes = [t.theme for t in result.value.themes]
        # Stopwords and short words are excluded; >4-char words survive
        assert "would" not in themes
        assert "conquer" in themes
        assert "juggling" in themes
        assert len(themes) <= 5
        assert all(t.confidence == pytest.approx(0.5) for t in result.value.themes)
        assert all(t.category == ThemeCategory.PERSONAL_GROWTH for t in result.value.themes)

    async def test_theme_keywords_property_flattens_themes(self, vision_service):
        result = await vision_service.capture_vision(_USER, "learning and fitness matter to me")

        assert result.is_ok
        assert set(result.value.theme_keywords) >= {"learning", "fitness"}


class TestRecommendLearningPaths:
    async def test_without_lp_service_is_system_error(self, vision_service):
        result = await vision_service.recommend_learning_paths(["mindfulness"])

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.SYSTEM


class TestWordActionAlignment:
    async def test_full_overlap_scores_one(self, vision_service):
        # habit_streaks keys are matched by substring — "meditat" → mindfulness,
        # "workout" → health
        ctx = UserContext(
            user_uid=_USER,
            habit_streaks={"habit_daily_meditation": 5, "habit_morning_workout": 3},
        )

        result = await vision_service.calculate_word_action_alignment(
            ["mindfulness", "health"], ctx
        )

        assert result.is_ok
        alignment = result.value
        assert alignment.alignment_score == pytest.approx(1.0)
        assert set(alignment.matched_themes) == {"mindfulness", "health"}
        assert alignment.missing_in_actions == ()
        assert not alignment.has_gap
        assert "align" in alignment.get_gap_summary().lower()

    async def test_missing_themes_produce_insights_and_recommendations(self, vision_service):
        ctx = UserContext(user_uid=_USER)  # no activity at all

        result = await vision_service.calculate_word_action_alignment(["mindfulness"], ctx)

        assert result.is_ok
        alignment = result.value
        assert alignment.alignment_score == pytest.approx(0.0)
        assert alignment.missing_in_actions == ("mindfulness",)
        assert alignment.has_gap
        assert alignment.biggest_gap == "mindfulness"
        assert any("mindfulness" in i for i in alignment.insights)
        assert any("mindfulness" in r for r in alignment.recommendations)
        assert "mindfulness" in alignment.get_gap_summary()

    async def test_empty_vision_scores_zero(self, vision_service):
        ctx = UserContext(user_uid=_USER, habit_streaks={"habit_daily_meditation": 2})

        result = await vision_service.calculate_word_action_alignment([], ctx)

        assert result.is_ok
        assert result.value.alignment_score == pytest.approx(0.0)

    async def test_unexpected_actions_surface_vision_update_hint(self, vision_service):
        # Actions produce many themes (mindfulness, health, learning, technical,
        # knowledge, mastery, values) while the vision names only one of them —
        # unexpected > matched triggers the "update your vision" insight.
        ctx = UserContext(
            user_uid=_USER,
            habit_streaks={
                "habit_meditation": 1,
                "habit_workout": 1,
                "habit_reading": 1,
                "habit_code_practice": 1,
            },
            mastered_knowledge_uids={"ku_something"},
            core_principle_uids=["principle_x"],
        )

        result = await vision_service.calculate_word_action_alignment(["mindfulness"], ctx)

        assert result.is_ok
        alignment = result.value
        assert "mindfulness" in alignment.matched_themes
        assert len(alignment.unexpected_actions) > len(alignment.matched_themes)
        assert any("not mentioned in your vision" in i for i in alignment.insights)

    async def test_action_theme_extraction_covers_context_signals(self, vision_service):
        ctx = UserContext(
            user_uid=_USER,
            habit_streaks={"habit_meditation": 1, "habit_exercise": 1},
            active_goal_uids=["goal_x"],
            mastered_knowledge_uids={"ku_x"},
            core_principle_uids=["principle_x"],
        )

        themes = set(vision_service._extract_action_themes(ctx))

        assert {
            "mindfulness",
            "health",
            "goal-driven",
            "knowledge",
            "mastery",
            "values",
        } <= themes
