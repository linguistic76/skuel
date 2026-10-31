"""
Unit tests for LifePathVisionService — no graph.

Covers theme extraction in both tiers: CORE's keyword matching, and FULL's LLM
extraction over a real ``LLMService`` whose provider is scripted
(``tests/fixtures/llm_doubles.py``) — every reply shape it can meet, and the
keyword fallback that any reply without a usable theme takes. Also the
vision-statement validation, and the word-action alignment computation that
bridges vision themes to UserContext.

The LP match search runs against a real LpService in
tests/integration/test_lifepath_vision_recommendations.py — not mocked here, per
the project's "mock-only unit tests hide phantom methods" rule.
"""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from core.models.enums.lifepath_enums import ThemeCategory
from core.prompts import PROMPT_REGISTRY
from core.services.lifepath.lifepath_vision_service import LifePathVisionService
from core.services.user.unified_user_context import UserContext
from core.utils.result_simplified import ErrorCategory
from tests.fixtures.llm_doubles import ScriptedChatCaller, failing_llm, scripted_llm

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

    async def test_a_word_repeated_without_a_known_keyword_is_one_theme(self, vision_service):
        result = await vision_service.capture_vision(
            _USER, "juggling, juggling, juggling and more juggling forever"
        )

        assert result.is_ok
        assert [t.theme for t in result.value.themes] == ["juggling", "forever"]


#: A vision whose keyword themes differ from the LLM's: the keyword pass finds
#: "matter" alone ("mindful" and "leader" are not the keywords "mindfulness" and
#: "leadership"), so a fallback is visible in the themes.
_VISION = "I want to become a mindful leader who builds things that matter"
_KEYWORD_THEMES = ["matter"]


async def _capture(reply: str) -> tuple[list[str], str | None, list[str]]:
    """Capture ``_VISION`` with an LLM that answers ``reply``: the saved themes,
    the model the capture names, and the warnings logged."""
    service = LifePathVisionService(llm_service=scripted_llm(reply))
    with capture_logs() as logs:
        result = await service.capture_vision(_USER, _VISION)
    assert result.is_ok
    warnings = [log["event"] for log in logs if log["log_level"] == "warning"]
    return result.value.theme_keywords, result.value.llm_model, warnings


class TestLlmExtraction:
    """FULL tier: the LLM's themes, or the keywords whenever its reply has none."""

    async def test_a_clean_reply_is_the_themes(self):
        themes, model, warnings = await _capture(
            '[{"theme": "Leadership", "context": "a leader"}, {"theme": " mindfulness "}]'
        )

        assert themes == ["leadership", "mindfulness"]
        assert model == "gpt-4o-mini"
        assert warnings == []

    async def test_the_themes_carry_their_category_and_context(self):
        service = LifePathVisionService(
            llm_service=scripted_llm(
                '[{"theme": "leadership", "context": "become a leader"},'
                ' {"theme": "woodworking", "context": 7}]'
            )
        )
        capture = (await service.capture_vision(_USER, _VISION)).value

        leadership, woodworking = capture.themes
        assert (leadership.category, leadership.context) == (
            ThemeCategory.CAREER,
            "become a leader",
        )
        assert leadership.confidence == pytest.approx(0.9)
        # A theme no keyword names is personal growth; a context that is not text is none.
        assert (woodworking.category, woodworking.context) == (ThemeCategory.PERSONAL_GROWTH, None)

    async def test_a_fenced_reply_is_read_inside_its_fence(self):
        themes, model, warnings = await _capture(
            'Here are the themes:\n```json\n[{"theme": "leadership"}, {"theme": "mindfulness"}]\n```'
        )

        assert themes == ["leadership", "mindfulness"]
        assert model == "gpt-4o-mini"
        assert warnings == []

    async def test_a_theme_named_twice_is_kept_once(self):
        themes, _, _ = await _capture(
            '[{"theme": "Leadership"}, {"theme": "mindfulness"}, {"theme": "leadership "}]'
        )

        assert themes == ["leadership", "mindfulness"]

    @pytest.mark.parametrize(
        "reply",
        [
            '[{"context": "a leader"}, {"theme": "mindfulness"}]',
            '[{"theme": null}, {"theme": "mindfulness"}]',
            '[{"theme": 7}, {"theme": "mindfulness"}]',
            '[{"theme": "   "}, {"theme": "mindfulness"}]',
            '["leadership", {"theme": "mindfulness"}]',
        ],
        ids=["missing", "null", "number", "blank", "bare-string"],
    )
    async def test_an_entry_without_a_theme_is_skipped(self, reply: str):
        themes, model, warnings = await _capture(reply)

        assert themes == ["mindfulness"]
        assert model == "gpt-4o-mini"
        assert warnings == []

    @pytest.mark.parametrize(
        ("reply", "reason"),
        [
            ("Here are the themes: leadership, mindfulness", "the reply is not JSON"),
            ('{"themes": [{"theme": "leadership"}]}', "the reply is a JSON dict, not an array"),
            ("42", "the reply is a JSON int, not an array"),
            ("[]", "the LLM's reply named no usable theme"),
            ('["leadership", "mindfulness"]', "the LLM's reply named no usable theme"),
            ('[{"theme": ""}, {"context": "a leader"}]', "the LLM's reply named no usable theme"),
        ],
        ids=["not-json", "object", "number", "empty", "strings", "no-usable-theme"],
    )
    async def test_a_reply_without_a_usable_theme_falls_back_to_keywords(
        self, reply: str, reason: str
    ):
        themes, model, warnings = await _capture(reply)

        assert themes == _KEYWORD_THEMES
        assert model is None  # the keywords produced these themes, not the LLM
        assert len(warnings) == 1
        assert warnings[0].startswith(f"Vision themes fell back to keywords: {reason}")

    async def test_a_provider_failure_falls_back_to_keywords(self):
        """A failed LLM never refuses the vision: it is saved with keyword themes."""
        service = LifePathVisionService(llm_service=failing_llm("rate limited"))
        with capture_logs() as logs:
            result = await service.capture_vision(_USER, _VISION)

        assert result.is_ok
        assert result.value.theme_keywords == _KEYWORD_THEMES
        assert result.value.llm_model is None
        [warning] = [log["event"] for log in logs if log["log_level"] == "warning"]
        assert warning.startswith("Vision themes fell back to keywords: the LLM failed")
        assert "rate limited" in warning

    async def test_the_prompt_is_the_registry_template_holding_the_vision(self):
        llm = scripted_llm('[{"theme": "leadership"}]')
        await LifePathVisionService(llm_service=llm).capture_vision(_USER, _VISION)

        assert isinstance(llm.caller, ScriptedChatCaller)
        [messages] = llm.caller.calls
        sent = messages[-1]["content"]
        assert sent == PROMPT_REGISTRY.render("lifepath_vision_themes", vision_statement=_VISION)
        assert "Respond with ONLY a JSON array" in sent

    async def test_a_short_statement_is_refused_before_the_llm_is_asked(self):
        llm = scripted_llm('[{"theme": "leadership"}]')
        result = await LifePathVisionService(llm_service=llm).capture_vision(_USER, "short")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.VALIDATION
        assert isinstance(llm.caller, ScriptedChatCaller)
        assert llm.caller.calls == []


class TestMatchLearningPaths:
    async def test_without_lp_service_is_system_error(self, vision_service):
        result = await vision_service.match_learning_paths(["mindfulness"])

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
